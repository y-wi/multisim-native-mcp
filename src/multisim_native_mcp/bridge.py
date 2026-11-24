"""Own a hidden Multisim process and call its private native C++ object model."""
from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

import frida

from .paths import RESOURCE_DIR as ROOT, DATA_DIR


def _default_install_dir() -> Path:
    return Path(os.environ.get('MULTISIM_NATIVE_INSTALL', str(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'National Instruments' / 'Circuit Design Suite 14.3')))


_INITIAL_INSTALL = _default_install_dir()
INSTALL = _INITIAL_INSTALL
_MODAL_WATCHDOG_DELAY = 5.0
_MODAL_WATCHDOG_INTERVAL = 1.0


def install_dir() -> Path:
    if INSTALL is not _INITIAL_INSTALL:
        return Path(INSTALL)
    return _default_install_dir()


def _window_text(user, hwnd) -> str:
    length = user.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ''
    buf = ctypes.create_unicode_buffer(length + 2)
    count = user.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value[:count].strip() if count > 0 else ''


def _window_class(user, hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    count = user.GetClassNameW(hwnd, buf, len(buf))
    return buf.value[:count] if count > 0 else ''


def detect_modal_dialogs(pid: int) -> list[dict]:
    """Find visible #32770 modal dialogs belonging to pid without blocking on its UI thread."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or os.name != 'nt':
        return []
    user = ctypes.WinDLL('user32', use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.IsWindowVisible.argtypes, user.IsWindowVisible.restype = [w.HWND], w.BOOL
    user.GetWindowThreadProcessId.argtypes, user.GetWindowThreadProcessId.restype = [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD
    user.GetClassNameW.argtypes, user.GetClassNameW.restype = [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int
    user.GetWindowTextLengthW.argtypes, user.GetWindowTextLengthW.restype = [w.HWND], ctypes.c_int
    user.GetWindowTextW.argtypes, user.GetWindowTextW.restype = [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int
    user.EnumWindows.argtypes, user.EnumWindows.restype = [enum_proc, w.LPARAM], w.BOOL
    user.EnumChildWindows.argtypes, user.EnumChildWindows.restype = [w.HWND, enum_proc, w.LPARAM], w.BOOL

    dialogs: list[dict] = []

    @enum_proc
    def on_top_window(hwnd, _lparam):
        if not user.IsWindowVisible(hwnd):
            return True
        owner_pid = w.DWORD(0)
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid:
            return True
        if _window_class(user, hwnd) != '#32770':
            return True
        title = _window_text(user, hwnd)
        messages: list[str] = []
        buttons: list[str] = []

        @enum_proc
        def on_child(child_hwnd, _child_lparam):
            text = _window_text(user, child_hwnd)
            if _window_class(user, child_hwnd).lower() == 'button':
                if user.IsWindowVisible(child_hwnd):
                    buttons.append(text)
                return True
            if text and text not in messages:
                messages.append(text)
            return True

        user.EnumChildWindows(hwnd, on_child, 0)
        # Splash/progress windows are #32770 too but have no buttons; only a
        # dialog awaiting user input (message box, duplicate-net prompt) has one.
        if buttons:
            dialogs.append({'title': title, 'messages': messages, 'buttons': [b for b in buttons if b]})
        return True

    user.EnumWindows(on_top_window, 0)
    return dialogs


def _format_modal_dialogs(dialogs: list[dict]) -> str:
    parts = []
    for dialog in dialogs:
        title = dialog.get('title') or '<untitled dialog>'
        messages = [m for m in dialog.get('messages', []) if m]
        parts.append(f'{title}: {" | ".join(messages)}' if messages else title)
    return '; '.join(parts)


def _wait_process(proc, timeout: float) -> None:
    try:
        proc.wait(timeout=timeout)
    except TypeError:
        proc.wait()


def editor_script():
    return '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in
                     ('host_agent.js', 'editor_agent.js', 'simulation_settings.js', 'instruments_agent.js'))


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
        self.session_dir=None
        self.isolated=False
        self.working_hash=None
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
        install = install_dir()
        manifest = json.loads((ROOT / 'native-profile.json').read_text(encoding='utf-8'))
        checks = []
        for name, digest in manifest['modules'].items():
            path = install / name
            check = {'module': name, 'present': path.is_file(), 'match': False}
            try:
                check['match'] = sha256(path) == digest if check['present'] else False
            except OSError as error:
                check['error'] = str(error)
            checks.append(check)
        attached=bool(self.process and self.process.poll() is None)
        processes=[{'pid':p.pid,'name':p.name} for p in frida.get_local_device().enumerate_processes() if p.name.lower() in ('multisim','multisim.exe')]
        return {'available': (install / 'multisim.exe').is_file(),
                'compatible': all(c['match'] for c in checks), 'profile_enforced': False,
                'tested_version': manifest['version'],
                'install': str(install), 'checks': checks, 'backend': 'private-native-cpp/frida',
                'official_com': False, 'screenshot_or_mouse': False,
                'running':bool(processes) or attached,'session_attached':attached,'processes':processes,
                'pid':self.process.pid if attached else processes[0]['pid'] if len(processes)==1 else None}

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

    def recovery_folder(self):
        if self.session_dir is None:
            self.session_dir=DATA_DIR/'sessions'/uuid.uuid4().hex
            self.session_dir.mkdir(parents=True,exist_ok=True)
        return self.session_dir

    def backup_file(self,path):
        backup=self.recovery_folder()/('backup-'+uuid.uuid4().hex+'-'+path.name)
        shutil.copy2(path,backup)
        return backup

    def open_circuit(self,source_path):
        return self._open(source_path)

    def open_copy(self,source_path,output_path=None):
        """Explicit comparison copy, saved beside the source unless a file is supplied."""
        return self._open(source_path,True,output_path)

    def _open(self, source_path: str, isolated=False,output_path=None,_startup_attempt=0) -> dict:
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError('A copy is already open. Save and close it before opening another.')
            install = install_dir()
            source = Path(source_path)
            if not source.is_absolute() or source.suffix.lower() != '.ms14' or not source.is_file():
                raise ValueError('source_path must be an absolute path to an existing .ms14 file')
            if not (install / 'multisim.exe').is_file():
                raise FileNotFoundError('Multisim executable not found: ' + str(install / 'multisim.exe'))
            if not isolated and source.resolve()==(ROOT/'assets'/'blank14.3.ms14').resolve():
                raise ValueError('Use native_create_circuit to create a workspace document from the packaged template')
            target=Path(output_path).expanduser() if output_path else source.with_name(source.stem+'.copy-'+uuid.uuid4().hex[:8]+'.ms14')
            if isolated and (not target.is_absolute() or target.suffix.lower()!='.ms14' or not target.parent.is_dir()):
                raise ValueError('output_path must be an absolute .ms14 path in an existing directory')
            if isolated and target.exists():raise FileExistsError('Comparison output already exists')
            if any(p.name.lower() in ('multisim', 'multisim.exe') for p in frida.get_local_device().enumerate_processes()):
                raise RuntimeError('Choose native_open_circuit to reuse an existing Multisim window, or native_attach to select a process; isolated copy startup requires other windows to be closed.')
            startup_timeout = float(os.environ.get('MULTISIM_NATIVE_STARTUP_TIMEOUT', '90'))
            if not math.isfinite(startup_timeout) or startup_timeout <= 0:
                raise ValueError('MULTISIM_NATIVE_STARTUP_TIMEOUT must be finite and positive')
            self.close()
            self.owned = True
            self.undo_stack, self.redo_stack = [], []
            self.topology_dirty = False
            folder = DATA_DIR / 'sessions' / uuid.uuid4().hex
            folder.mkdir(parents=True)
            self.session_dir=folder;self.isolated=isolated
            self.source = source.resolve()
            self.source_hash = sha256(self.source)
            self.working = target.resolve() if isolated else self.source
            if isolated:shutil.copy2(self.source, self.working)
            else:self.backup_file(self.source)
            self.working_hash=sha256(self.working)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # SW_HIDE prevents this Multisim build from initializing schematic extensions.
            # Initialize minimized without activation, then hide after the native sheet is ready.
            startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            # Multisim's legacy command parser expects a quoted document argument, even without spaces.
            command = f'"{install / "multisim.exe"}" "{self.working}"'
            self.process = subprocess.Popen(command,
                                            cwd=install, startupinfo=startup,
                                            env=native_environment(),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            readiness = None
            try:
                self._own_job()
                # Let the ordinary startup message loop initialize DAO and the schematic extension
                # before querying/materializing documents from a message-pump callback.
                # DLL presence alone does not mean CLR/license/DAO startup is complete.
                started_at = time.monotonic()
                ready_after = started_at + 8
                startup_deadline = started_at + startup_timeout
                wait_idle = ctypes.WinDLL('user32').WaitForInputIdle
                wait_idle.argtypes, wait_idle.restype = [w.HANDLE,w.DWORD],w.DWORD
                last_error = None
                candidate = None
                while True:
                    if self.process.poll() is not None:
                        raise RuntimeError(f'Multisim exited during startup with code {self.process.returncode}')
                    if time.monotonic() >= ready_after and isinstance(getattr(self.process, 'pid', None), int):
                        dialogs = detect_modal_dialogs(self.process.pid)
                        if dialogs:
                            raise RuntimeError('Multisim blocked on modal dialog during startup: ' + _format_modal_dialogs(dialogs))
                    if time.monotonic() >= startup_deadline:
                        suffix = f' (last error: {last_error})' if last_error else ''
                        raise RuntimeError(f'Multisim startup timed out after {startup_timeout:g}s{suffix}')
                    if time.monotonic() < ready_after or wait_idle(w.HANDLE(int(self.process._handle)),0) != 0:
                        time.sleep(0.25)
                        continue
                    try:
                        if self.session is None:
                            self.session = frida.attach(self.process.pid)
                            readiness = self.session.create_script((ROOT / 'startup_agent.js').read_text(encoding='utf-8'),runtime='v8')
                            readiness.load()
                        if not readiness.exports_sync.ready():
                            report=readiness.exports_sync.report()
                            if report.get('startup_errors'):raise RuntimeError('Multisim startup error: '+json.dumps(report['startup_errors'],ensure_ascii=False))
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
                        components = self.call('openedSheetComponents')
                        (folder / 'dao-trace.json').write_text(json.dumps(readiness.exports_sync.report(), indent=2), encoding='utf-8')
                        hwnd = int(self.agent.exports_sync.identity()['hwnd'], 16)
                        if hwnd:
                            user = ctypes.WinDLL('user32')
                            user.ShowWindow.argtypes, user.ShowWindow.restype = [w.HWND, ctypes.c_int], w.BOOL
                            user.ShowWindow(hwnd, 0)
                        self.handle_generation += 1
                        return {'session_id': folder.name, 'source_path': str(self.source),
                                'working_copy':str(self.working) if isolated else None,'working_path':str(self.working),
                                'recovery_directory':str(folder),'mode':'copy' if isolated else 'direct',
                                'source_sha256': sha256(self.source),
                                'component_count': len(components['components']), **info}
                    except (frida.ProcessNotFoundError, frida.InvalidOperationError):
                        raise
                    except Exception as error:
                        last_error = str(error)
                        if 'Multisim startup error:' in last_error:raise RuntimeError(last_error) from error
                        if 'SyntaxError:' in last_error: raise RuntimeError('Native agent syntax error: '+last_error) from error
                        if 'Isolated process opened an unexpected project' in last_error:
                            raise RuntimeError(last_error) from error
                        if 'Multisim blocked on modal dialog' in last_error:
                            raise RuntimeError(last_error) from error
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
            except BaseException as error:
                if readiness is not None:
                    try:
                        readiness.unload()
                    except Exception:
                        pass
                    readiness = None
                transient_startup=(_startup_attempt==0 and self.agent is None and
                    ('Multisim startup error:' in str(error) or
                     self.process and self.process.poll()==0xE0434352))
                failed_copy=self.working if isolated else None
                initial_hash=self.working_hash
                self.close()
                if transient_startup:
                    if failed_copy:
                        if not failed_copy.is_file() or sha256(failed_copy)!=initial_hash:raise
                        failed_copy.unlink()
                        output_path=str(failed_copy)
                    return self._open(source_path,isolated,output_path,1)
                raise
            finally:
                if readiness is not None:
                    try:
                        readiness.unload()
                    except Exception:
                        pass

    def call(self, operation: str, args: dict | None = None) -> dict:
        with self.lock:
            if not self.agent or not self.process or self.process.poll() is not None:
                raise RuntimeError('No native project is open. Call native_open_circuit, native_create_circuit or native_attach first.')
            # Long numeric runs remain cancellable through the native analysis
            # controls; a fixed edit watchdog must not kill valid simulations.
            owned = self.process
            pid = getattr(owned, 'pid', None)
            started = time.monotonic()
            self.native_call_count += 1
            done_event = threading.Event()
            modal_detected: list[dict] = []
            session_dir = self.session_dir
            if (self.owned and isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and
                    operation not in ('simulate', 'interactiveCommand', 'exportInteractiveImage')):
                def _watch_modal():
                    if done_event.wait(_MODAL_WATCHDOG_DELAY):
                        return
                    while not done_event.is_set():
                        if owned.poll() is not None:
                            return
                        dialogs = detect_modal_dialogs(pid)
                        if dialogs:
                            modal_detected.extend(dialogs)
                            if session_dir:
                                try:
                                    with (session_dir / 'native-diagnostics.jsonl').open('a', encoding='utf-8') as file:
                                        file.write(json.dumps({'type': 'modal_dialog_detected', 'operation': operation, 'dialogs': dialogs}) + '\n')
                                except Exception:
                                    pass
                            try:
                                owned.terminate()
                            except Exception:
                                pass
                            return
                        if done_event.wait(_MODAL_WATCHDOG_INTERVAL):
                            return

                threading.Thread(target=_watch_modal, daemon=True).start()
            frida_errors = tuple({frida.InvalidOperationError, frida.ProcessNotFoundError, getattr(frida, 'TransportError', frida.InvalidOperationError)})
            try:
                response = json.loads(self.agent.exports_sync.dispatch(operation, args or {}))
                if modal_detected:
                    raise RuntimeError(f'Native {operation} blocked on modal dialog after {time.monotonic()-started:.1f}s ({_format_modal_dialogs(modal_detected)}); owned process terminated')
                return response
            except frida_errors as error:
                if modal_detected:
                    raise RuntimeError(f'Native {operation} blocked on modal dialog after {time.monotonic()-started:.1f}s ({_format_modal_dialogs(modal_detected)}); owned process terminated') from error
                raise RuntimeError(f'Native {operation} interrupted after {time.monotonic()-started:.1f}s; owned process exit={owned.poll()}: {error}') from error
            except Exception as error:
                if modal_detected and 'blocked on modal dialog' not in str(error):
                    raise RuntimeError(f'Native {operation} blocked on modal dialog after {time.monotonic()-started:.1f}s ({_format_modal_dialogs(modal_detected)}); owned process terminated') from error
                raise
            finally:
                done_event.set()
                self.native_call_seconds += time.monotonic()-started

    def _message(self,message,data):
        payload = message.get('payload') if isinstance(message, dict) else None
        if isinstance(payload, dict) and payload.get('analysis_started'):
            self.analysis_started.set()
        if self.session_dir:
            with (self.session_dir/'native-diagnostics.jsonl').open('a',encoding='utf-8') as file:
                file.write(json.dumps(message)+'\n')

    def reload_agent(self) -> dict:
        """Development harness only: replace the RPC agent without restarting Multisim."""
        with self.lock:
            self.agent.exports_sync.close()
            self.agent.unload()
            code = editor_script()
            self.agent = self.session.create_script(code,runtime='v8')
            self.agent.on('message', self._message)
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
                backup = self.backup_file(path)
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
                wm_closed = False
                try:
                    if self.agent:
                        self.call('prepareClose')
                        hwnd = int(self.agent.exports_sync.identity()['hwnd'], 16)
                        user = ctypes.WinDLL('user32')
                        user.PostMessageW.argtypes, user.PostMessageW.restype = [w.HWND,w.UINT,w.WPARAM,w.LPARAM],w.BOOL
                        user.PostMessageW(hwnd,0x0010,0,0)  # WM_CLOSE: let DAO and extensions release normally.
                        wm_closed = True
                    else:
                        self.process.terminate()
                except Exception:
                    self.process.terminate()
                try:
                    _wait_process(self.process, 10 if wm_closed else 5)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        _wait_process(self.process, 5)
                    except subprocess.TimeoutExpired:
                        if hasattr(self.process, 'kill'):
                            self.process.kill()
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
            return {'closed': self.owned, 'detached': not self.owned, 'pid': pid,
                    'working_path':str(self.working) if self.working else None,
                    'working_copy': str(self.working) if self.isolated and self.working else None}
