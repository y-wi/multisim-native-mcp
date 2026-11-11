"""Own a hidden Multisim process and call its private native C++ object model."""
from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

import frida

from .paths import RESOURCE_DIR as ROOT, DATA_DIR
INSTALL = Path(os.environ.get('MULTISIM_NATIVE_INSTALL', str(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'National Instruments' / 'Circuit Design Suite 14.3')))


def editor_script():
    return '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in
                     ('host_agent.js', 'editor_agent.js', 'simulation_settings.js'))


def native_environment() -> dict[str, str]:
    """MCP clients filter inherited variables; DAO's REG_EXPAND_SZ needs CommonProgramFiles."""
    result = os.environ.copy()
    shell = ctypes.WinDLL('shell32')
    get_folder = shell.SHGetFolderPathW
    get_folder.argtypes = [w.HWND, ctypes.c_int, w.HANDLE, w.DWORD, w.LPWSTR]
    get_folder.restype = ctypes.c_long

    def folder(identifier):
        target = ctypes.create_unicode_buffer(1024)
        hr = get_folder(None, identifier, None, 0, target)
        if hr < 0:
            raise OSError(f'Windows folder lookup failed: {identifier}, HRESULT={hr:#x}')
        return target.value

    # This service runs under Python x86, so these CSIDLs resolve to the x86 directories.
    program_files, common_files, program_data = folder(0x26), folder(0x2b), folder(0x23)
    result.update({'ProgramFiles': program_files, 'ProgramFiles(x86)': program_files,
                   'CommonProgramFiles': common_files, 'CommonProgramFiles(x86)': common_files,
                   'PROGRAMDATA': program_data, 'ALLUSERSPROFILE': program_data})
    windows = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetWindowsDirectoryW(windows, 1024)
    result.setdefault('SystemRoot', windows.value)
    result.setdefault('windir', windows.value)
    result.setdefault('COMSPEC', str(Path(windows.value) / 'System32' / 'cmd.exe'))
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BasicLimit(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', w.DWORD), ('min_working', ctypes.c_size_t),
                ('max_working', ctypes.c_size_t), ('active', w.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [('basic', BasicLimit), ('io', IoCounters), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


class NativeHost:
    def __init__(self):
        if ctypes.sizeof(ctypes.c_void_p) != 4:
            raise RuntimeError('Use Python 3.12 x86 for the tested Multisim native profile')
        self.lock = threading.RLock()
        self.process = self.session = self.agent = self.job = None
        self.source = self.working = None
        self.source_hash = None
        self.owned = True
        self.undo_stack, self.redo_stack = [], []
        self.topology_dirty = False
        self.analysis_started = threading.Event()
        self.native_call_count = 0
        self.native_call_seconds = 0.
        self.handle_generation = 0
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in [
            ('CreateJobObjectW', [w.LPVOID, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
            ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL),
        ]:
            method = getattr(self.kernel, name)
            method.argtypes, method.restype = args, result
        atexit.register(self.close)

    def runtime_status(self) -> dict:
        manifest = json.loads((ROOT / 'native-profile.json').read_text(encoding='utf-8'))
        checks = []
        for name, digest in manifest['modules'].items():
            path = INSTALL / name
            check = {'module': name, 'present': path.is_file(), 'match': False}
            try:
                check['match'] = sha256(path) == digest if check['present'] else False
            except OSError as error:
                check['error'] = str(error)
            checks.append(check)
        return {'available': (INSTALL / 'multisim.exe').is_file(),
                'compatible': all(c['match'] for c in checks), 'profile_enforced': False,
                'tested_version': manifest['version'],
                'install': str(INSTALL), 'checks': checks, 'backend': 'private-native-cpp/frida',
                'official_com': False, 'screenshot_or_mouse': False,
                'running': bool(self.process and self.process.poll() is None),
                'pid': self.process.pid if self.process else None}

    def _own_job(self):
        handle = self.kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.job = handle
        info = ExtendedLimit()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.AssignProcessToJobObject(handle, int(self.process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def open_copy(self, source_path: str) -> dict:
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError('A copy is already open. Save and close it before opening another.')
            source = Path(source_path)
            if not source.is_absolute() or source.suffix.lower() != '.ms14' or not source.is_file():
                raise ValueError('source_path must be an absolute path to an existing .ms14 file')
            if not (INSTALL / 'multisim.exe').is_file():
                raise FileNotFoundError('Multisim executable not found: ' + str(INSTALL / 'multisim.exe'))
            if any(p.name.lower() in ('multisim', 'multisim.exe') for p in frida.get_local_device().enumerate_processes()):
                raise RuntimeError('Close other Multisim windows first. This build redirects new launches to an existing process; the service only operates its own isolated host.')
            self.close()
            self.owned = True
            self.undo_stack, self.redo_stack = [], []
            self.topology_dirty = False
            folder = DATA_DIR / 'sessions' / uuid.uuid4().hex
            folder.mkdir(parents=True)
            self.source = source.resolve()
            self.source_hash = sha256(self.source)
            self.working = folder / source.name
            shutil.copy2(self.source, self.working)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # SW_HIDE prevents this Multisim build from initializing schematic extensions.
            # Initialize minimized without activation, then hide after the native sheet is ready.
            startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            # Multisim's legacy command parser expects a quoted document argument, even without spaces.
            command = f'"{INSTALL / "multisim.exe"}" "{self.working}"'
            self.process = subprocess.Popen(command,
                                            cwd=INSTALL, startupinfo=startup,
                                            env=native_environment(),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                self._own_job()
                # Let the ordinary startup message loop initialize DAO and the schematic extension
                # before querying/materializing documents from a message-pump callback.
                # DLL presence alone does not mean CLR/license/DAO startup is complete.
                ready_after = time.monotonic() + 8
                wait_idle = ctypes.WinDLL('user32').WaitForInputIdle
                wait_idle.argtypes, wait_idle.restype = [w.HANDLE,w.DWORD],w.DWORD
                deadline = time.monotonic() + 45
                last_error = None
                candidate = None
                readiness = None
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise RuntimeError(f'Isolated Multisim exited with code {self.process.returncode}')
                    if time.monotonic() < ready_after or wait_idle(w.HANDLE(int(self.process._handle)),0) != 0:
                        time.sleep(0.25)
                        continue
                    try:
                        if self.session is None:
                            self.session = frida.attach(self.process.pid)
                            readiness = self.session.create_script((ROOT / 'startup_agent.js').read_text(encoding='utf-8'),runtime='v8')
                            readiness.load()
                        if not readiness.exports_sync.ready():
                            time.sleep(0.25)
                            continue
                        if time.monotonic() < ready_after:
                            time.sleep(0.25)
                            continue
                        if self.agent is None:
                            candidate = self.session.create_script(editor_script(),runtime='v8')
                            candidate.on('message', self._message)
                            candidate.load()
                            candidate.exports_sync.identity()
                            self.agent = candidate
                        info = self.call('inspect')
                        if Path(info['projectPath']).resolve() != self.working.resolve():
                            raise RuntimeError('Isolated process opened an unexpected project')
                        components = self.call('components')
                        (folder / 'dao-trace.json').write_text(json.dumps(readiness.exports_sync.report(), indent=2), encoding='utf-8')
                        hwnd = int(self.agent.exports_sync.identity()['hwnd'], 16)
                        if hwnd:
                            user = ctypes.WinDLL('user32')
                            user.ShowWindow.argtypes, user.ShowWindow.restype = [w.HWND, ctypes.c_int], w.BOOL
                            user.ShowWindow(hwnd, 0)
                        self.handle_generation += 1
                        return {'session_id': folder.name, 'source_path': str(self.source),
                                'working_copy': str(self.working), 'source_sha256': sha256(self.source),
                                'component_count': len(components['components']), **info}
                    except (frida.ProcessNotFoundError, frida.InvalidOperationError):
                        raise
                    except Exception as error:
                        last_error = str(error)
                        if 'SyntaxError:' in last_error: raise RuntimeError('Native agent syntax error: '+last_error) from error
                        if readiness:
                            try:
                                (folder / 'dao-trace.json').write_text(json.dumps(readiness.exports_sync.report(), indent=2), encoding='utf-8')
                            except Exception:
                                pass
                        if self.agent is None and candidate:
                            try:
                                candidate.unload()
                            except Exception:
                                pass
                        time.sleep(0.4)
                raise TimeoutError('Multisim did not become ready: ' + str(last_error))
            except BaseException:
                self.close()
                raise

    def call(self, operation: str, args: dict | None = None) -> dict:
        with self.lock:
            if not self.agent or not self.process or self.process.poll() is not None:
                raise RuntimeError('No native project is open. Call native_open_copy, native_create_circuit or native_attach first.')
            # Only terminate the child owned by this server if a native call stops responding.
            owned = self.process
            timer = threading.Timer(25, lambda: owned.kill() if self.owned and owned.poll() is None else None)
            timer.daemon = True
            timer.start()
            started = time.monotonic()
            self.native_call_count += 1
            try:
                return json.loads(self.agent.exports_sync.dispatch(operation, args or {}))
            except (frida.InvalidOperationError, frida.ProcessNotFoundError) as error:
                raise RuntimeError(f'Native {operation} interrupted after {time.monotonic()-started:.1f}s; owned process exit={owned.poll()}: {error}') from error
            finally:
                self.native_call_seconds += time.monotonic()-started
                timer.cancel()

    def _message(self,message,data):
        if message.get('payload',{}).get('analysis_started'): self.analysis_started.set()
        if self.working:
            with (self.working.parent/'native-diagnostics.jsonl').open('a',encoding='utf-8') as file:
                file.write(json.dumps(message)+'\n')

    def reload_agent(self) -> dict:
        """Development harness only: replace the RPC agent without restarting Multisim."""
        with self.lock:
            self.agent.exports_sync.close()
            self.agent.unload()
            code = editor_script()
            self.agent = self.session.create_script(code,runtime='v8')
            self.agent.load()
            return self.agent.exports_sync.identity()

    def save_copy(self, output_path: str, overwrite: bool = False) -> dict:
        with self.lock:
            path = Path(output_path)
            if not path.is_absolute() or path.suffix.lower() != '.ms14':
                raise ValueError('output_path must be an absolute .ms14 path')
            path = path.resolve()
            if path == self.source or path == self.working or (path.exists() and any(p and p.exists() and os.path.samefile(path, p) for p in (self.source, self.working))):
                raise ValueError('Choose a separate output path; source and working copy are protected')
            if not path.parent.is_dir():
                raise ValueError('Output directory does not exist')
            backup = None
            if path.exists():
                if not overwrite:
                    raise FileExistsError('Output already exists; choose another path or explicitly set overwrite=true')
                backup = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.bak')
                shutil.copy2(path, backup)
            native_target=path.with_name('save-'+uuid.uuid4().hex+'.ms14') if backup else path
            original_path=self.call('inspect')['projectPath'] if backup else None
            try:
                result = self.call('save', {'path': str(native_target)})
                if result['nativeResult'] != 1 or result['errorCode'] != 0 or not native_target.is_file() or native_target.stat().st_size < 32:
                    raise RuntimeError('Native SaveProjectDocument failed: ' + json.dumps(result))
                if backup:
                    native_target.replace(path)
                    if not self.call('setProjectPath',{'path':str(path)}):raise RuntimeError('Saved file is ready but the native document path could not be updated')
                    result['path']=str(path)
            except Exception:
                if backup:
                    shutil.copy2(backup, path)
                    try:self.call('setProjectPath',{'path':original_path})
                    except Exception:pass
                raise
            finally:
                if backup:native_target.unlink(missing_ok=True)
            return {**result, 'sha256': sha256(path), 'bytes': path.stat().st_size,
                    'backup': str(backup) if backup else None, 'source_unchanged': sha256(self.source) == self.source_hash if self.source else None}

    def close(self) -> dict:
        with self.lock:
            pid = self.process.pid if self.process else None
            if self.process and self.process.poll() is None and self.owned:
                try:
                    if self.agent:
                        self.call('prepareClose')
                        hwnd = int(self.agent.exports_sync.identity()['hwnd'], 16)
                        user = ctypes.WinDLL('user32')
                        user.PostMessageW.argtypes, user.PostMessageW.restype = [w.HWND,w.UINT,w.WPARAM,w.LPARAM],w.BOOL
                        user.PostMessageW(hwnd,0x0010,0,0)  # WM_CLOSE: let DAO and extensions release normally.
                    else:
                        self.process.terminate()
                except Exception:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            if self.agent and not self.owned:
                try:
                    self.agent.exports_sync.close()
                    self.agent.unload()
                except Exception:
                    pass
            if self.session:
                try:
                    self.session.detach()
                except Exception:
                    pass
            if self.job:
                self.kernel.CloseHandle(self.job)
            self.process = self.session = self.agent = self.job = None
            return {'closed': self.owned, 'detached': not self.owned, 'pid': pid, 'working_copy': str(self.working) if self.working else None}
