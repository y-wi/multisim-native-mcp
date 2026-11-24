"""Validated native editor transactions and analysis artifacts; no circuit file rewriting."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import csv
import hashlib
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import tempfile
import time
import uuid

import frida
from PIL import Image

from .bridge import NativeHost, ROOT, INSTALL, sha256, editor_script, install_dir
from .paths import DATA_DIR
from .edit_contracts import normalize_edit
from .identity import identity_changes
from .instruments import (
    compile_instrument_settings,
    filter_persistent_instrument_props,
    format_instrument_settings,
    lookup_by_native,
    resolve_instrument,
    search_instruments,
)

# Native exports use their actual bitmap format and allocator bounds.
Image.MAX_IMAGE_PIXELS = None

MUTATIONS = {'wire','move','moveLabel','place','placeInstrument','setInstrumentSettings','copy','remove','transform','route','setParameter','setModelText',
             'rename','addText','updateText','deleteText','updateSheet','moveJunction','updatePort','labelWire','splitWire','connectEndpoint','reconnect',
             'replace','createSheet','createSubcircuit','createPort','sheetTitle','sheetSize','repairWireGeometry',
             'autoWire','connectTouching','fitSheet','translateSheet'}
TOPOLOGY_MUTATIONS={'wire','place','placeInstrument','copy','remove','connectEndpoint','reconnect','replace','splitWire',
                    'createSheet','createSubcircuit','createPort','updatePort','rename','connectTouching','labelWire'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def changes_topology(operation,result):
    if isinstance(result,dict) and 'topology_changed' in result:return bool(result['topology_changed'])
    repeated=operation in ('wire','connectEndpoint') and isinstance(result,dict) and result.get('alreadyConnected')
    return operation in TOPOLOGY_MUTATIONS and not repeated


class NativeSaveError(RuntimeError):
    def __init__(self,message,details):
        super().__init__(message);self.details={'error':message,**details}


class NativeEditError(RuntimeError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = {'error': message, **details}


class ExistingProcess:
    """Read-only process lifetime handle. Deliberately has no terminate/kill methods."""
    def __init__(self, pid):
        self.pid = pid
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())

    def poll(self):
        code = w.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)): return -1
        return None if code.value == 259 else code.value

    def __del__(self):
        if getattr(self, 'handle', None): self.kernel.CloseHandle(self.handle)


from .waveforms import parse_raw, export_csv, summarize


class EditorService(NativeHost):
    def __init__(self):
        super().__init__()
        self.analysis_job=None
        self.numeric_session_used=False
        self._active_edit_sequence=None

    def folder(self):
        if self.session_dir:return self.session_dir
        if not self.working: raise RuntimeError('Open or create a circuit first')
        return self.working.parent

    def open_circuit(self,source_path):
        source=Path(source_path).expanduser()
        if not source.is_absolute():raise ValueError('source_path must be an absolute .ms14 file path')
        source=source.resolve()
        if not source.is_file() or source.suffix.lower()!='.ms14':raise ValueError('Choose an existing .ms14 circuit')
        if self.process and self.process.poll() is None:
            if not self.isolated and self.working and self.working.resolve()==source and self.source and self.source.resolve()==source:
                selected=self.call('inspect')
                if selected.get('projectPath') and Path(selected['projectPath']).resolve()==source:
                    return {**selected,'source_path':str(source),'working_path':str(source),'mode':'direct','reused':True,'handles_invalidated':False}
            raise RuntimeError('Save and close the current circuit first')
        running=[p for p in frida.get_local_device().enumerate_processes() if p.name.lower() in ('multisim','multisim.exe')]
        if len(running)==1:
            try:
                self.attach(running[0].pid)
                matches=[p for p in self.call('projects')['projects'] if Path(p['path']).resolve()==source]
                if len(matches)>1:raise RuntimeError('This source is open more than once; select a specific project with native_attach')
                if matches:self.call('selectProject',{'index':matches[0]['index']})
                else:self.call('openDocument',{'path':str(source)})
                self.source=self.working=source;self.source_hash=sha256(source)
                self.isolated=False
                checkpoint=self.checkpoint()
                return {**self.call('inspect'),'source_path':str(source),'working_path':str(source),'working_copy':None,
                        'recovery_directory':str(self.folder()),
                        'backup':checkpoint['path'],'mode':'direct','owned':False,'attached_existing':True}
            except Exception:
                self.close();raise
        return NativeHost.open_circuit(self,str(source))

    @contextmanager
    def analysis_transport(self,stem):
        """Keep the legacy SPICE shell's filenames ASCII; publish artifacts at their requested path."""
        if str(stem).isascii():
            yield stem
            return
        root=Path(os.environ.get('MULTISIM_NATIVE_IO_DIR',tempfile.gettempdir())).resolve()
        root.mkdir(parents=True,exist_ok=True)
        if not str(root).isascii():
            short=ctypes.create_unicode_buffer(32768)
            get_short=ctypes.WinDLL('kernel32').GetShortPathNameW
            get_short.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD];get_short.restype=w.DWORD
            count=get_short(str(root),short,len(short))
            if not count or count>=len(short) or not short.value.isascii():
                raise ValueError('The SPICE file transport requires an ASCII directory. Set MULTISIM_NATIVE_IO_DIR to an existing writable ASCII path; circuit and result paths may use Unicode.')
            root=Path(short.value)
        with tempfile.TemporaryDirectory(prefix='multisim-native-io-',dir=root) as temporary:
            native_stem=Path(temporary)/stem.name
            try:yield native_stem
            finally:
                for suffix in ('.cir','.raw'):
                    source=native_stem.with_suffix(suffix)
                    if source.is_file():shutil.copy2(source,stem.with_suffix(suffix))

    @staticmethod
    def saved_signature(sheets):
        """Compare saved content without process-local object IDs."""
        def clean(value):
            if isinstance(value,float):return round(value,6)
            if isinstance(value,list):return [clean(v) for v in value]
            if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
            return value
        def endpoint(value):return {k:value[k] for k in ('ref','pin','x','y') if k in value}
        def order(values):return sorted(values,key=lambda v:json.dumps(v,sort_keys=True))
        return clean([{'sheet_index':s['sheet_index'],
                      'page_name':s['sheets'][s['sheet_index']].get('page'),
                      'page':{k:s['page'][k] for k in ('width','height')},
                      'components':order([{'ref':c['ref'],'transform':c['transform'],
                          'pins':order([{'name':p['name'],'x':p['x'],'y':p['y']} for p in c['pins']]),
                          'labels':[{k:l[k] for k in ('kind','text', 'transform' if 'transform' in l else 'center')} for l in c.get('labels',[])],
                          'parameters':c.get('parameters',[]),
                          'model_text':None if c.get('is_instrument') else c.get('model_text'),
                          **({'is_instrument':True,'instrument_type':c.get('instrument_type'),
                              'instrument_settings':filter_persistent_instrument_props(c.get('instrument_properties'))}
                             if c.get('is_instrument') else {})} for c in s['components']]),
                      'wires':order([{'source':endpoint(w['source']),'target':endpoint(w['target']),'points':w['points']} for w in s['wires']]),
                      'annotations':order(s.get('annotations',[])),
                      'wire_labels':order(s.get('wire_labels',[])),
                      'sheet_display':s.get('sheet_display')} for s in sheets])

    def save_copy(self,output_path,overwrite=False,allow_off_page=False,verify=True):
        if not isinstance(allow_off_page,bool) or not isinstance(verify,bool):raise ValueError('allow_off_page and verify must be boolean')
        raw_path=Path(output_path)
        if not raw_path.is_absolute() or raw_path.suffix.lower()!='.ms14':
            raise ValueError('output_path must be an absolute .ms14 path')
        with self.lock:
            if self.source and not self.isolated and raw_path.resolve()==self.source:
                return self.save_source(allow_off_page,**({'verify':False} if not verify else {}))
            job=self.analysis_job
            if job and job['status'] in ('running','pause_requested','stop_requested'):
                raise RuntimeError('Stop numeric analysis before saving the circuit')
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before saving the circuit')
            self.call('synchronizeGraphics')
            simulation_settings=self.call('simulationSettingsText') if verify else None
            sheets=self.call('projectCircuitState',{'include_parameters':verify,'include_persistence':verify})['states']
            outside=[]
            for state in sheets:
                b=state['content_bounds'];p=state['page']['bounds']
                if b and (b['left']<p['left'] or b['top']<p['top'] or b['right']>p['right'] or b['bottom']>p['bottom']):
                    outside.append({'sheet':state['sheets'][state['sheet_index']]['title'],'page_bounds':p,'content_bounds':b})
            result=super().save_copy(output_path,overwrite)
            result.update(page_check={'passed':not outside,'outside_sheets':outside},handles_invalidated=False)
            if verify:
                verification=self.folder()/('verify-'+uuid.uuid4().hex+'.ms14')
                try:
                    shutil.copy2(result['path'],verification)
                    reopened=self.call('verifySavedCopy',{'path':str(verification),'include_parameters':True,'include_persistence':True,'include_simulation_settings':True})
                    expected=self.saved_signature(sheets);actual=self.saved_signature(reopened['states'])
                    from .save_differences import saved_differences,difference_summary
                    settings_differences=[]
                    if simulation_settings!=reopened['simulation_settings']:
                        try:settings_differences=self.call('simulationPropertyDiff',{'expected':simulation_settings,'actual':reopened['simulation_settings']})['differences']
                        except Exception:pass
                        if not settings_differences:settings_differences=saved_differences(simulation_settings,reopened['simulation_settings'],'simulation_settings.serialized')
                    if expected!=actual or settings_differences:
                        diagnostic=verification.with_suffix('.json')
                        differences=saved_differences(expected,actual)+settings_differences
                        diagnostic.write_text(json.dumps({'expected':expected,'actual':actual,'differences':differences,
                            'simulation_settings':{'expected':simulation_settings,'actual':reopened['simulation_settings']}},ensure_ascii=False,indent=2),encoding='utf-8')
                        prefix='Saved simulation settings differ after native reopen' if settings_differences else 'Saved circuit differs after native reopen'
                        raise NativeSaveError(prefix+': '+difference_summary(differences)+'; diagnostics: '+str(diagnostic),
                            {'differences':differences,'diagnostic_path':str(diagnostic),'verification':{'passed':False,'reopened':True}})
                    result['verification']={'passed':True,'reopened':True,'simulation_settings_preserved':True,'sheets':len(sheets),'components':sum(len(s['components']) for s in sheets),'wires':sum(len(s['wires']) for s in sheets)}
                except Exception:
                    if result['backup']:shutil.copy2(result['backup'],result['path'])
                    raise
                finally:verification.unlink(missing_ok=True)
            else:result['verification']={'reopened':False,'passed':None,'skipped':True}
            if not self.isolated and not getattr(self,'_saving_source',False) and self.source:
                self.source=self.working=Path(result['path']).resolve();self.source_hash=result['sha256']
                result['current_document']=str(self.source)
            return result

    def _save_source(self,allow_off_page=False,verify=True):
        """Explicit source replacement, only after verified native save and conflict checks."""
        if not self.source or not self.source.is_file():raise ValueError('No existing source file to save')
        source=self.source
        if source==(ROOT/'assets'/'blank14.3.ms14').resolve():
            raise ValueError('Create a workspace circuit with native_create_circuit; packaged templates are internal resources')
        if sha256(source)!=self.source_hash:raise RuntimeError('Source changed outside this session; reopen it before saving')
        staged=source.with_name('save-source-'+uuid.uuid4().hex+'.ms14')
        original_path=self.call('inspect')['projectPath'];backup=None;replaced=False
        self._saving_source=True
        try:
            result=self.save_copy(str(staged),verify=verify,**({'allow_off_page':True} if allow_off_page else {}))
            if sha256(source)!=self.source_hash:raise RuntimeError('Source changed during verification; source was not overwritten')
            backup=self.backup_file(source)
            if sha256(backup)!=self.source_hash or sha256(source)!=self.source_hash:
                raise RuntimeError('Source changed during backup; source was not overwritten')
            staged.replace(source);replaced=True
            if not self.call('setProjectPath',{'path':str(source)}):raise RuntimeError('Could not update native document path')
            self.source_hash=sha256(source)
            return {**result,'path':str(source),'backup':str(backup),'sha256':self.source_hash,
                    'source_unchanged':False,'saved_to_source':True}
        except Exception:
            if replaced:shutil.copy2(backup,source)
            try:self.call('setProjectPath',{'path':original_path})
            except Exception:pass
            raise
        finally:
            self._saving_source=False;staged.unlink(missing_ok=True)

    def save_source(self,allow_off_page=False,verify=True):
        if not isinstance(allow_off_page,bool):raise ValueError('allow_off_page must be boolean')
        if not isinstance(verify,bool):raise ValueError('verify must be boolean')
        with self.lock:return self._save_source(allow_off_page,verify)

    def save_current(self,allow_off_page=False,verify=True):
        with self.lock:
            if not self.isolated:return self.save_source(allow_off_page,**({'verify':False} if not verify else {}))
            source,digest=self.source,self.source_hash
            try:
                self.source=self.working;self.source_hash=self.working_hash or sha256(self.working)
                result=self.save_source(allow_off_page,**({'verify':False} if not verify else {}));result['saved_to_source']=False;result['saved_working_copy']=True
                self.working_hash=sha256(self.working)
                return result
            finally:self.source,self.source_hash=source,digest

    def finish(self,save_changes=True):
        if not isinstance(save_changes,bool):raise ValueError('save_changes must be boolean')
        with self.lock:
            saved=None
            if save_changes and self.agent and self.call('inspect')['modified']:
                if not self.isolated and not self.source and (not self.owned or getattr(self.save_current,'__func__',None) is EditorService.save_current):
                    raise ValueError('This attached circuit has never been saved to disk; save it first with native_save_copy(output_path) or detach without saving via native_close_copy(save_changes=False)')
                if self.interactive_status()['state_name'] in ('running','paused'):self.control_interactive('stop',15)
                saved=self.save_current()
            result=self.close()
            return {**result,'save':saved,'saved_changes':saved is not None}

    def document_context(self):
        return {'source_path':str(self.source) if self.source else None,'source_sha256':self.source_hash,
                'working_path':str(self.working) if self.working else None,'working_sha256':self.working_hash,
                'isolated':self.isolated}

    def open_recovery(self,checkpoint,document=None):
        """Load an internal checkpoint, then rebind the actual document identity."""
        document=document or {}
        NativeHost.open_circuit(self,checkpoint['path'])
        if document.get('source_path'):
            self.source=Path(document['source_path']);self.source_hash=document.get('source_sha256')
            self.working=Path(document.get('working_path') or document['source_path'])
            self.working_hash=document.get('working_sha256');self.isolated=document.get('isolated',False)
            self.call('setProjectPath',{'path':str(self.working)})
            if checkpoint.get('modified'):self.call('markModified')
        return self.call('inspect')

    def configure_wiring(self,autowire_on_connection=None,autowire_on_move=None,connect_touching=None,
                         move_connection_limit=None,reset=False,persist=False):
        if not isinstance(reset,bool) or not isinstance(persist,bool):raise ValueError('reset and persist must be boolean')
        options={}
        for key,value in [('autowire_on_connection',autowire_on_connection),('autowire_on_move',autowire_on_move),('connect_touching',connect_touching)]:
            if value is not None:
                if not isinstance(value,bool):raise ValueError(key+' must be boolean')
                options[key]=value
        if move_connection_limit is not None:
            if isinstance(move_connection_limit,bool) or not isinstance(move_connection_limit,int) or not 1<=move_connection_limit<=2147483647:
                raise ValueError('move_connection_limit must be a positive signed 32-bit integer')
            options['move_connection_limit']=move_connection_limit
        if reset and (options or persist):raise ValueError('Use reset alone to restore temporary wiring settings')
        with self.lock:
            if options or reset or persist:
                if self.interactive_status()['state_name'] in ('running','paused'):raise RuntimeError('Stop interactive simulation before changing wiring options')
            result=self.call('wiringOptions',{'reset':True} if reset else options)
            if persist:return self.call('persistWiringOptions')
            return {**result,'persisted_in_circuit':False,'saved_to_application':False}

    def configure_sheet_display(self,save_to_source=False,**options):
        if not isinstance(save_to_source,bool):raise ValueError('save_to_source must be boolean')
        allowed={'show_grid','show_border','show_bounds'}
        options={k:v for k,v in options.items() if v is not None}
        if set(options)-allowed or any(not isinstance(v,bool) for v in options.values()):raise ValueError('Sheet display options must be known booleans')
        with self.lock:
            mutating=bool(options or save_to_source)
            if mutating and self.interactive_status()['state_name'] in ('running','paused'):raise RuntimeError('Stop interactive simulation before changing sheet display')
            checkpoint=self.checkpoint() if mutating else None
            try:
                result=self.call('sheetDisplaySettings',options)
                if result['changed']:self.call('markModified')
                if save_to_source:result['save']=self._save_source()
            except Exception:
                if checkpoint:self.restore(checkpoint)
                raise
            if checkpoint:self.undo_stack.append(checkpoint);self.redo_stack.clear()
            return {**result,'saved_to_file':save_to_source,'persisted_in_circuit':True}

    def simulation_settings(self,scope='interactive',analysis_type='TRAN',changes=None,solver_options=None,
                            save_to_source=False,expected_revision=None):
        from .settings import normalize_setting_changes
        changes=normalize_setting_changes(changes)
        if any(isinstance(token,int) for c in changes for token in c['path']) and expected_revision is None:
            raise ValueError('Indexed native field paths require expected_revision from the current catalog')
        if scope not in ('interactive','analysis'):raise ValueError('Choose interactive or analysis scope')
        if not isinstance(analysis_type,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',analysis_type):raise ValueError('Invalid native analysis type')
        analysis_type=analysis_type.upper()
        if not isinstance(save_to_source,bool):raise ValueError('save_to_source must be boolean')
        if solver_options is None:solver_options={}
        if not isinstance(solver_options,dict):raise ValueError('solver_options must be a mapping')
        for key,value in solver_options.items():
            if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',key):raise ValueError('Invalid solver option name')
            if value is not None and (not isinstance(value,(str,bool,int,float)) or isinstance(value,float) and not math.isfinite(value)):
                raise ValueError('Solver options require finite scalar values or null to disable')
        with self.lock:
            mutating=bool(changes or solver_options or save_to_source)
            if mutating:
                if self.interactive_status()['state_name'] in ('running','paused'):raise RuntimeError('Stop interactive simulation before changing document settings')
            text=self.call('simulationSettingsText');revision=hashlib.sha256(text.encode('utf-8')).hexdigest()
            if expected_revision is not None and expected_revision!=revision:raise RuntimeError('Simulation settings changed; read the current catalog before updating')
            args={'scope':scope,'analysis_type':analysis_type,'changes':changes,'solver_options':solver_options}
            if expected_revision is not None:args['expected_text']=text
            checkpoint=self.checkpoint() if mutating else None
            temporary=self.call('interactiveOptions').get('configuration',{}) if mutating and scope=='interactive' else {}
            try:
                result=self.call('documentSimulationSettings',args)
                updated_revision=hashlib.sha256(result.pop('_simulation_text').encode('utf-8')).hexdigest()
                if mutating:
                    if result['changed']:self.call('markModified')
                    if scope=='interactive':self.call('interactiveOptions',{'reset':True})
                    if save_to_source:result['save']=self._save_source()
            except Exception as error:
                if checkpoint:
                    self.restore(checkpoint)
                    if temporary:self.call('interactiveOptions',{'configuration':temporary})
                    raise NativeEditError(str(error),{'rolled_back':True,'handles_invalidated':True,'rollback_checkpoint':checkpoint['path']}) from error
                raise
            if checkpoint:self.undo_stack.append(checkpoint);self.redo_stack.clear()
            result.update(revision=updated_revision,
                          saved_to_file=save_to_source,persisted_in_circuit=True,handles_invalidated=False)
            return result

    def checkpoint(self):
        path=self.folder()/('checkpoint-'+uuid.uuid4().hex+'.ms14')
        sheets=self.call('sheets')
        result=self.call('snapshot',{'path':str(path)})
        if result['nativeResult']!=1 or result['errorCode']!=0 or not path.is_file():
            raise RuntimeError('Native checkpoint failed')
        return {'path':str(path),'original_path':result['original_path'],
                'modified':result['modified'],
                'sheet_index':next(s['index'] for s in sheets if s['selected']),
                'document':self.document_context()}

    def restore(self, checkpoint):
        # Multisim can retain a native SPICE session tied to the old graph after numeric export.
        if self.owned and self.numeric_session_used:
            result = self._restart_from_checkpoint(checkpoint)
        else:
            try:
                result = self.call('restoreSnapshot', checkpoint)
            except Exception:
                if not self.owned:
                    raise
                result = self._restart_from_checkpoint(checkpoint)
        self.topology_dirty=False
        self.handle_generation += 1
        return result

    def _restart_from_checkpoint(self, checkpoint):
        source,digest,working,working_digest,session_dir,isolated,undo,redo=(
            self.source,self.source_hash,self.working,self.working_hash,
            self.session_dir,self.isolated,self.undo_stack,self.redo_stack)
        self.close()
        NativeHost.open_circuit(self,checkpoint['path'])
        new_session_dir=self.session_dir
        self.source,self.source_hash,self.undo_stack,self.redo_stack=source,digest,undo,redo
        self.working,self.working_hash,self.isolated=working,working_digest,isolated
        if session_dir is not None:
            self.session_dir=session_dir
            if new_session_dir and new_session_dir!=session_dir:
                shutil.rmtree(new_session_dir,ignore_errors=True)
        return {**self.call('restoreSnapshot',checkpoint),'host_restarted':True}

    def edit(self, operation, args=None):
        batch=self.batch([{'operation':operation,'arguments':args or {}}])
        value=batch['results'][0]
        if isinstance(value,dict) and batch.get('handles_invalidated'):
            value={**value,**{k:batch[k] for k in ('handles_invalidated','handle_generation','id_map','unresolved_ids','state') if k in batch}}
        return value

    def plan_wire_route(self, wire_id: str, clearance: int = 9) -> dict:
        if not isinstance(wire_id,str) or not wire_id or '\0' in wire_id:
            raise ValueError('Provide a current wire ID')
        if not _is_int(clearance) or clearance<0:
            raise ValueError('Clearance must be nonnegative')
        from .layout import plan_wire
        with self.lock:
            wire=next((w for w in self.call('wires')['wires'] if w['id']==wire_id),None)
            if not wire:raise ValueError('Wire not found')
            return plan_wire(self.call('componentBounds')['components'],wire,clearance)

    def _refresh_signal_names(self) -> dict:
        if not self.topology_dirty:
            return {}
        result = self.netlist()
        return {key: result[key] for key in ('handles_invalidated', 'handle_generation', 'id_map', 'unresolved_ids') if key in result}

    def get_circuit_state(self, include_parameters: bool = False, include_nets: bool = False) -> dict:
        with self.lock:
            identity = self._refresh_signal_names() if include_nets else {}
            return {**self.call('circuitState', {'include_parameters': include_parameters, 'include_nets': include_nets}), **identity}

    def get_connectivity(self) -> dict:
        with self.lock:
            identity = self._refresh_signal_names()
            return {**self.call('connectivity'), **identity}

    def resolve_signal(self, component_ref: str, pin: str) -> dict:
        if not isinstance(component_ref,str) or not component_ref.strip() or '\0' in component_ref:
            raise ValueError('Provide a nonempty component_ref')
        if not isinstance(pin,str) or not pin.strip() or '\0' in pin:
            raise ValueError('Provide a nonempty pin name')
        with self.lock:
            identity = self._refresh_signal_names()
            if component_ref in identity.get('unresolved_ids', ()):
                raise ValueError(f'Component ID {component_ref} could not be rebound after topology refresh. Use a current ID or a unique reference.')
            ref = identity.get('id_map', {}).get(component_ref, component_ref)
            return {**self.call('signalForPin', {'ref': ref, 'pin': pin}), **identity}

    def fit_sheet(self, margin: int = 36, resize: bool = True) -> dict:
        return self.edit('fitSheet',{'margin':margin,'resize':resize})

    def _prepare_instrument_op(self, op_name: str, raw_args: dict) -> dict:
        args = dict(raw_args)
        if op_name == 'placeInstrument':
            entry = resolve_instrument(args.get('instrument', ''))
            args['instrument'] = entry['instrument']
            args['dll'] = entry['dll']
            args['manager'] = entry['manager']
            args['res_id'] = entry['res_id']
            args['flags'] = entry['flags']
            args['create_kind'] = entry['create_kind']
            settings = args.pop('settings', None)
            if settings is not None:
                if not isinstance(settings, dict):
                    raise ValueError('settings must be a mapping')
                if settings:
                    args['writes'] = compile_instrument_settings(entry, settings)
            return args
        if op_name == 'setInstrumentSettings':
            if 'writes' in args and args['writes']:
                return args
            settings = args.pop('settings', None)
            if not isinstance(settings, dict) or not settings:
                raise ValueError('setInstrumentSettings requires a non-empty settings mapping')
            info = self.call('getInstrumentSettings', {'ref': args['ref']})
            entry = lookup_by_native(info.get('instrument_manager'), info.get('instrument_type'))
            args['writes'] = compile_instrument_settings(entry, settings)
            return args
        return args

    @staticmethod
    def _format_instrument_result(op_name: str, raw_result: dict, include_raw: bool = False) -> dict:
        if op_name not in ('placeInstrument', 'setInstrumentSettings') or not isinstance(raw_result, dict):
            return raw_result
        entry = lookup_by_native(raw_result.get('instrument_manager'), raw_result.get('instrument_type'))
        raw_props = raw_result.pop('raw_properties', None)
        formatted = format_instrument_settings(entry, raw_props or {}, include_raw=include_raw)
        enriched = {
            **raw_result,
            'instrument': entry['instrument'] if entry else (raw_result.get('instrument_manager') or '').lower(),
            'display_name': entry['display_name'] if entry else raw_result.get('instrument_type'),
            'pin_map': entry['pin_map'] if entry else {},
            **formatted,
        }
        if 'component' in enriched and isinstance(enriched['component'], dict) and entry:
            enriched['component'] = {**enriched['component'], 'instrument': entry['instrument']}
        return enriched

    def list_instruments(self, query: str = '') -> dict:
        if not isinstance(query, str) or '\0' in query:
            raise ValueError('query must be a string')
        install = install_dir()
        catalog = []
        for item in search_instruments(query):
            dll_path = install / item['dll']
            catalog.append({**item, 'dll_present': dll_path.is_file()})
        result = {
            'query': query,
            'count': len(catalog),
            'instruments': catalog,
            'session_attached': bool(self.agent),
        }
        with self.lock:
            if self.agent:
                placed = []
                for inst in self.call('listPlacedInstruments')['instruments']:
                    entry = lookup_by_native(inst.get('instrument_manager'), inst.get('instrument_type'))
                    raw_props = inst.pop('raw_properties', None) or {}
                    formatted = format_instrument_settings(entry, raw_props, include_raw=False)
                    placed.append({
                        **inst,
                        'instrument': entry['instrument'] if entry else inst.get('instrument_manager'),
                        'display_name': entry['display_name'] if entry else inst.get('instrument_type'),
                        'pin_map': entry['pin_map'] if entry else {},
                        'settings': formatted['settings'],
                        **({'readouts': formatted['readouts']} if 'readouts' in formatted else {}),
                    })
                result['placed_instruments'] = placed
        return result

    def place_instrument(self, instrument: str, x: int, y: int, reference: str | None = None,
                         anchor: str = 'origin', pin: str | None = None,
                         angle: float | None = None, mirror_axis: str | None = None,
                         settings: dict | None = None, include_raw: bool = False) -> dict:
        args = {'instrument': instrument, 'x': x, 'y': y, 'anchor': anchor}
        if reference is not None:
            args['ref'] = reference
        if pin is not None:
            args['pin'] = pin
        if angle is not None:
            args['angle'] = angle
        if mirror_axis is not None:
            args['mirror_axis'] = mirror_axis
        if settings is not None:
            args['settings'] = settings
        if include_raw:
            args['_include_raw'] = True
        return self.edit('placeInstrument', args)

    def get_instrument_settings(self, component_ref: str, include_raw: bool = False) -> dict:
        if not isinstance(component_ref, str) or not component_ref.strip() or '\0' in component_ref:
            raise ValueError('Provide a nonempty component_ref')
        if not isinstance(include_raw, bool):
            raise ValueError('include_raw must be boolean')
        with self.lock:
            raw = self.call('getInstrumentSettings', {'ref': component_ref})
        entry = lookup_by_native(raw.get('instrument_manager'), raw.get('instrument_type'))
        raw_props = raw.pop('raw_properties', None) or {}
        formatted = format_instrument_settings(entry, raw_props, include_raw=include_raw)
        return {
            **raw,
            'instrument': entry['instrument'] if entry else raw.get('instrument_manager'),
            'display_name': entry['display_name'] if entry else raw.get('instrument_type'),
            'pin_map': entry['pin_map'] if entry else {},
            **formatted,
        }

    def set_instrument_settings(self, component_ref: str, settings: dict, include_raw: bool = False) -> dict:
        if not isinstance(component_ref, str) or not component_ref.strip() or '\0' in component_ref:
            raise ValueError('Provide a nonempty component_ref')
        if not isinstance(include_raw, bool):
            raise ValueError('include_raw must be boolean')
        args = {'ref': component_ref, 'settings': settings}
        if include_raw:
            args['_include_raw'] = True
        return self.edit('setInstrumentSettings', args)

    def export_instrument_data(self, component_ref: str, output_path: str, overwrite: bool = False) -> dict:
        if not isinstance(component_ref, str) or not component_ref.strip() or '\0' in component_ref:
            raise ValueError('Provide a nonempty component_ref')
        if not isinstance(overwrite, bool):
            raise ValueError('overwrite must be boolean')
        with self.lock:
            info = self.call('getInstrumentSettings', {'ref': component_ref})
            entry = lookup_by_native(info.get('instrument_manager'), info.get('instrument_type'))
            suffixes = set(entry.get('export_data_formats', [])) if entry else {'.scp', '.bod', '.txt'}
            if not suffixes:
                raise ValueError(f"{component_ref} ({entry['instrument']}) does not support native trace data export; supported instruments: oscilloscope (.scp), oscilloscope_4ch (.scp), bode_plotter (.bod)")
            path = self.output_path(output_path, suffixes, overwrite)
            result = self.call('exportInstrumentData', {'ref': component_ref, 'path': str(path)})
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Instrument {component_ref} did not produce trace data (start and run interactive simulation first to collect waveform samples)')
        text = path.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()
        return {
            **result,
            'instrument': entry['instrument'] if entry else info.get('instrument_manager'),
            'bytes': path.stat().st_size,
            'line_count': len(lines),
            'preview': '\n'.join(lines[:25]),
            'source': 'native instrument data exporter',
        }

    def edit_sequence(self, operations, bindings, cancel=None):
        """One checkpoint for a phase; bounded UI-thread slices resolve intermediate results."""
        from .workflow_values import resolve,reference_roots
        operations=[self.normalize_edit(op) for op in operations]
        packed={'place','placeInstrument','move','alignPin','moveLabel','transform','wire','connectEndpoint','route','autoWire',
                'setParameter','addText','updateText','deleteText','updateSheet','moveJunction','updatePort','labelWire','splitWire','rename','remove','connectTouching',
                'sheetSize','sheetTitle','repairWireGeometry','fitSheet','translateSheet'}
        def is_packed(op):
            if op['operation'] == 'placeInstrument':
                return 'settings' not in op.get('arguments', {})
            if op['operation'] in packed:
                return True
            if op['operation'] == 'setInstrumentSettings':
                return bool(op.get('arguments', {}).get('writes'))
            return False
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):
                raise RuntimeError('Stop interactive simulation before editing')
            checkpoint=self.checkpoint();results=[];current=dict(bindings);index=0
            undo_before=list(self.undo_stack);redo_before=list(self.redo_stack)
            token=uuid.uuid4().hex;self._active_edit_sequence=token
            try:
                while index<len(operations):
                    if cancel and cancel.is_set():raise RuntimeError('Workflow cancelled between native edit slices')
                    end=index
                    while end<min(index+8,len(operations)) and is_packed(operations[end]):end+=1
                    if end>index:
                        slice_ops=[]
                        for raw_op in operations[index:end]:
                            op_copy=dict(raw_op)
                            if op_copy['operation']=='placeInstrument' and 'dll' not in op_copy.get('arguments',{}):
                                op_copy['arguments']=self._prepare_instrument_op('placeInstrument',op_copy.get('arguments',{}))
                            slice_ops.append(op_copy)
                        roots=reference_roots(slice_ops)
                        value=self.call('editSequence',{'operations':slice_ops,
                            'bindings':{k:v for k,v in current.items() if k in roots},'cancel_token':token})
                        if value['failed']:
                            index+=value['failed_operation_index'];raise RuntimeError(value['error'])
                        formatted_slice=[self._format_instrument_result(op['operation'],res) for op,res in zip(slice_ops,value['results'])]
                        for op,res in zip(slice_ops,formatted_slice):
                            if op.get('bind'):value['bindings'][op['bind']]=res
                        results.extend(formatted_slice);current.update(value['bindings'])
                    else:
                        op=operations[index];a=resolve(op.get('arguments',{}),current)
                        previous_state=self.call('circuitState',{'include_parameters':True})
                        previous_state['handle_epoch']=[self.process.pid,self.handle_generation]
                        value=self.batch([{'operation':op['operation'],'arguments':a}])['results'][0]
                        from .workflows import remap_bindings
                        state=self.call('circuitState',{'include_parameters':True})
                        state['handle_epoch']=[self.process.pid,self.handle_generation]
                        current=remap_bindings(current,previous_state,state)
                        results=remap_bindings(results,previous_state,state)
                        results.append(value)
                        if op.get('bind'):current[op['bind']]=value
                        end=index+1
                    self.topology_dirty=self.topology_dirty or any(changes_topology(op['operation'],result) for op,result in zip(operations[index:end],results[-(end-index):]))
                    index=end
                self.call('markModified')
            except Exception as error:
                self.restore(checkpoint)
                self.undo_stack=undo_before;self.redo_stack=redo_before
                raise NativeEditError(str(error),{'rolled_back':True,'rollback_scope':'edit_stage',
                    'failed_operation_index':index,'completed_operations':0,'handles_invalidated':True,
                    'rollback_checkpoint':checkpoint['path']}) from error
            finally:
                self._active_edit_sequence=None
            self.undo_stack=undo_before+[checkpoint];self.redo_stack.clear()
            return {'results':results,'bindings':current,'undo_depth':len(self.undo_stack),
                    'rollback_checkpoint':checkpoint['path']}

    def cancel_edit_sequence(self):
        # Posting must not acquire the editor lock or wait for a UI-thread RPC.
        token=self._active_edit_sequence
        if token and self.agent:self.agent.post({'type':'cancel-edit-sequence','token':token})

    def batch(self, operations, include_state=False, atomic=True):
        if not operations: raise ValueError('Provide nonempty edit operations')
        operations=[self.normalize_edit(op) for op in operations]
        for op in operations:
            if op.get('operation') not in MUTATIONS or not isinstance(op.get('arguments',{}),dict):
                raise ValueError('Unsupported edit operation: '+str(op.get('operation')))
            self.validate(op['operation'],op.get('arguments',{}))
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before editing the circuit')
            generation=self.handle_generation
            may_refresh=any(op['operation'] in ('createSubcircuit','replace') for op in operations)
            previous_identity=self.call('projectCircuitState')['states'] if may_refresh else None
            # Resolve the first existing target before saving or reopening anything.
            first=operations[0]
            if first['operation'] in {'move','moveLabel','transform','copy','remove','setParameter','setModelText','rename','replace','setInstrumentSettings'} and first.get('arguments',{}).get('ref'):
                target=first['arguments']['ref'];components=self.call('components')['components']
                matches=[c for c in components if target in (c['ref'],c['id'])] or [c for c in components if target==c.get('local_ref')]
                if len(matches)!=1:
                    state=self.call('circuitState',{'include_parameters':True})
                    candidates=[{'id':c['id'],'ref':c['ref']} for c in (matches or components)]
                    raise NativeEditError(f'Component {target!r} must identify one component on the selected sheet; found {len(matches)}. Use a current component ID for duplicate references. Candidates: {candidates}',
                        {'rolled_back':False,'handles_invalidated':False,'completed_operations':0,'state':state})
            before=self.checkpoint()
            step_before=before
            try:
                results=[]
                for index,op in enumerate(operations):
                    if not atomic and index:step_before=self.checkpoint()
                    # The component factory can inspect the whole electrical graph during replacement.
                    # Reopen its native checkpoint first when prior edits changed that graph.
                    if op['operation']=='replace' and self.topology_dirty:
                        args=dict(op.get('arguments',{}))
                        target=args.get('ref')
                        components=self.call('components')['components']
                        matches=[c for c in components if target in (c['ref'],c['id'])] or [c for c in components if target==c.get('local_ref')]
                        if len(matches)!=1:
                            raise ValueError(f'Component {target!r} must identify one component on the selected sheet; found {len(matches)}')
                        target_id=matches[0]['id'];target_ref=matches[0]['ref']
                        shared_ref=sum(1 for c in components if c['ref']==target_ref)>1
                        old_state=self.call('circuitState',{'include_parameters':True})
                        self.restore(self.checkpoint())
                        new_state=self.call('circuitState',{'include_parameters':True})
                        from .workflows import remap_bindings
                        before_refresh={**old_state,'handle_epoch':'before'};after_refresh={**new_state,'handle_epoch':'after'}
                        remapped_target=remap_bindings(target_id,before_refresh,after_refresh)
                        if isinstance(remapped_target,str):
                            args['ref']=remapped_target
                        elif not shared_ref:
                            args['ref']=target_ref
                        else:
                            raise RuntimeError(f'Component {target!r} could not be uniquely rebound after topology refresh')
                        results=remap_bindings(results,before_refresh,after_refresh)
                        operations[index+1:]=remap_bindings(operations[index+1:],before_refresh,after_refresh)
                    else:args=dict(op.get('arguments',{}))
                    include_raw=bool(args.pop('_include_raw',False))
                    if op['operation'] in ('placeInstrument','setInstrumentSettings'):
                        args=self._prepare_instrument_op(op['operation'],args)
                    raw_res=self.call(op['operation'],args)
                    results.append(self._format_instrument_result(op['operation'],raw_res,include_raw=include_raw))
                    self.topology_dirty=self.topology_dirty or changes_topology(op['operation'],results[-1])
                self.call('markModified')
                if any(op['operation']=='createSubcircuit' for op in operations):
                    subcircuit_sheet_indices=[
                        next((s.get('index') for s in res.get('sheets',[]) if s.get('id')==res.get('sheet_id')),None)
                        if op['operation']=='createSubcircuit' and isinstance(res,dict) else None
                        for op,res in zip(operations,results)
                    ]
                    old_state=self.call('circuitState',{'include_parameters':True})
                    self.restore(self.checkpoint())
                    new_state=self.call('circuitState',{'include_parameters':True})
                    from .workflows import remap_bindings
                    results=remap_bindings(results,{**old_state,'handle_epoch':'before'},{**new_state,'handle_epoch':'after'})
                    refreshed_components=self.call('components')['components'];refreshed_sheets=self.call('sheets')
                    for op,result,sheet_index in zip(operations,results,subcircuit_sheet_indices):
                        if op['operation']=='createSubcircuit':
                            result['components']=refreshed_components;result['sheets']=refreshed_sheets
                            expected_ref=op['arguments'].get('ref') or op['arguments']['title']
                            remapped_symbol=result.get('symbol_id')
                            if isinstance(remapped_symbol,str) and any(c['id']==remapped_symbol for c in refreshed_components):
                                result['symbol_id']=remapped_symbol
                            else:
                                symbol_matches=[c['id'] for c in refreshed_components if expected_ref in (c['ref'],c.get('local_ref'))]
                                if not symbol_matches:
                                    raise RuntimeError(f'Created subcircuit symbol {expected_ref!r} not found after refresh')
                                result['symbol_id']=symbol_matches[-1]
                            sheet_match=(next((s['id'] for s in refreshed_sheets if s.get('index')==sheet_index),None)
                                         if sheet_index is not None else None)
                            if sheet_match is None:
                                title_matches=[s['id'] for s in refreshed_sheets if s.get('title')==op['arguments']['title']]
                                if not title_matches:
                                    raise RuntimeError(f"Created subcircuit sheet {op['arguments']['title']!r} not found after refresh")
                                sheet_match=title_matches[-1]
                            result['sheet_id']=sheet_match
                            result.pop('block',None);result['handles_invalidated']=True
            except Exception as error:
                try: self.restore(before if atomic else step_before)
                except Exception as recovery:
                    raise RuntimeError(f'Edit failed ({error}); recovery failed ({recovery}); checkpoint: {before["path"]}') from error
                if not atomic and results:
                    self.undo_stack.append(before);self.redo_stack.clear()
                state=self.call('circuitState',{'include_parameters':True})
                message=f'Edit operation {index+1}/{len(operations)} ({op["operation"]}) failed: {str(error).splitlines()[0]}. ' + ('The entire batch was rolled back; earlier calls are preserved.' if atomic else 'Only the failed operation was rolled back; completed operations are preserved.')
                raise NativeEditError(message,{'rolled_back':True,'rollback_scope':'batch' if atomic else 'failed_operation',
                    'failed_operation_index':index,'completed_operations':0 if atomic else len(results),'handles_invalidated':True,
                    'rollback_checkpoint':(before if atomic else step_before)['path'],'state':state}) from error
            self.undo_stack.append(before); self.redo_stack.clear()
            refreshed=self.handle_generation!=generation
            identity=identity_changes(previous_identity,self.call('projectCircuitState')['states']) if refreshed and previous_identity is not None else {}
            return {'results':results,'undo_depth':len(self.undo_stack),'rollback_checkpoint':before['path'],
                    **({'handles_invalidated':True,'handle_generation':self.handle_generation,**identity} if refreshed else {}),
                    **({'state':self.call('circuitState',{'include_parameters':True})} if include_state or refreshed else {})}

    @staticmethod
    def normalize_edit(operation):
        return normalize_edit(operation)

    def list_projects(self):
        with self.lock:
            if not self.agent:
                running=[p for p in frida.get_local_device().enumerate_processes() if p.name.lower() in ('multisim','multisim.exe')]
                if len(running)!=1:raise RuntimeError('Select a Multisim process with native_attach; available PIDs: '+str([p.pid for p in running]))
                self.attach(running[0].pid)
            return self.call('projects')

    @staticmethod
    def validate(op,args):
        required={'addText':('text','x','y'),'updateText':('id',),'deleteText':('id',),'moveJunction':('id','x','y'),
                  'updatePort':('id',),'labelWire':('name',),'translateSheet':('dx','dy')}
        for key in required.get(op,()):
            if key not in args:raise ValueError(op+' requires '+key)
        for name,fields in [('updateText',('text','x','y')),('updateSheet',('title','page','width','height')),('updatePort',('name','x','y'))]:
            if op==name and not any(k in args for k in fields):raise ValueError(name+' requires '+', '.join(fields))
        if op in ('updateText','deleteText','moveJunction','updatePort') and (not isinstance(args.get('id'),str) or not args['id'] or '\0' in args['id']):raise ValueError('Provide a current object ID')
        if op=='labelWire':
            if 'id' in args and (not isinstance(args.get('id'),str) or not args['id'] or '\0' in args['id']):
                raise ValueError('Provide a current object ID')
            if not isinstance(args.get('name'),str) or not args['name'].strip() or '\0' in args['name']:
                raise ValueError('Wire net name must be a nonempty string')
        if op=='updateSheet':
            for key in ('width','height'):
                if key in args:EditorService.validate('sheetSize',{'width':args[key],'height':args[key]})
        if op=='fitSheet':
            if 'margin' in args and (not _is_int(args['margin']) or not 0<=args['margin']<=2147483647):
                raise ValueError('margin must be a nonnegative signed 32-bit integer')
            if 'resize' in args and not isinstance(args['resize'],bool):
                raise ValueError('resize must be boolean')
        if op=='connectTouching' and 'refs' in args:
            refs=args['refs']
            if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or not ref for ref in refs):
                raise ValueError('Provide nonempty component references')
        if op=='place':
            if args.get('anchor','origin') not in ('origin','center','pin'):raise ValueError('Placement anchor must be origin, center or pin')
            if args.get('anchor')=='pin' and not isinstance(args.get('pin'),str):raise ValueError('Placement with anchor=pin requires the exact pin name')
            if 'angle' in args and not _is_finite_number(args['angle']):raise ValueError('Rotation must be finite')
            if 'mirror_axis' in args and args['mirror_axis'] not in ('horizontal','vertical'):raise ValueError('Invalid mirror axis')
            if 'value' in args and 'expression' in args:raise ValueError('Provide value or expression, not both')
            for key in ('value','expression'):
                if key not in args:continue
                value=args[key]
                if isinstance(value,str):
                    if not value.strip() or '\0' in value:raise ValueError('Invalid placement expression')
                elif key=='expression' or not _is_finite_number(value):raise ValueError('Invalid placement value')
        if op=='place' and 'parameters' in args:
            if not isinstance(args['parameters'],list):raise ValueError('Provide a component parameter list')
            for parameter in args['parameters']:
                if not isinstance(parameter,dict) or (('value' in parameter)==('expression' in parameter)):raise ValueError('Each parameter needs index and exactly one value or expression')
                EditorService.validate('setParameter',parameter)
        if op=='place' and 'params' in args:
            if not isinstance(args['params'],dict):raise ValueError('params must be a mapping of parameter names to values or expressions')
            for param_name,param_value in args['params'].items():
                if not isinstance(param_name,str) or not param_name.strip() or '\0' in param_name:
                    raise ValueError('Invalid parameter name in params')
                if isinstance(param_value,str):
                    if not param_value.strip() or '\0' in param_value:
                        raise ValueError('Invalid parameter expression in params')
                elif not _is_finite_number(param_value):
                    raise ValueError('Invalid parameter value in params')
        if op=='sheetSize' and any(not _is_int(args.get(k)) or not 0<args[k]<=2147483647 for k in ('width','height')):
            raise ValueError('Sheet width and height must be positive signed 32-bit integers')
        if op=='sheetSize' and any(round(args[k]/96*25.4*500000)>2147483647 for k in ('width','height')):
            raise ValueError('Sheet dimensions exceed the native signed 32-bit CUTRect work-area format')
        for key in ('x','y','dx','dy'):
            if key in args and (not _is_int(args[key]) or not -2147483648<=args[key]<=2147483647):
                raise ValueError(key+' must fit a native signed 32-bit integer')
        if op=='setParameter':
            if ('value' in args)==('expression' in args):
                raise ValueError('Provide exactly one value or expression')
            if 'index' in args and (not _is_int(args['index']) or not 0<=args['index']<=2147483647):
                raise ValueError('Invalid parameter index')
            if 'name' in args and (not isinstance(args['name'],str) or not args['name'].strip() or '\0' in args['name']):
                raise ValueError('Invalid parameter name')
            if 'role' in args and (not isinstance(args['role'],str) or not args['role'].strip() or '\0' in args['role']):
                raise ValueError('Invalid parameter role')
            if 'value' in args and not _is_finite_number(args['value']):
                raise ValueError('Parameter must be finite')
            if 'expression' in args and (not isinstance(args['expression'],str) or not args['expression'].strip() or '\0' in args['expression']):
                raise ValueError('Invalid expression')
        if op=='transform':
            if ('angle' in args)==('axis' in args):
                raise ValueError('transform requires angle or axis, not both')
            if 'angle' in args and not _is_finite_number(args['angle']):
                raise ValueError('Rotation must be finite')
            if 'axis' in args and args.get('axis') not in ('horizontal','vertical'):
                raise ValueError('Invalid mirror axis')
        if op=='placeInstrument':
            entry=resolve_instrument(args.get('instrument',''))
            if 'x' not in args or 'y' not in args:raise ValueError('placeInstrument requires x and y')
            if args.get('anchor','origin') not in ('origin','center','pin'):raise ValueError('Placement anchor must be origin, center or pin')
            if args.get('anchor')=='pin':
                if not isinstance(args.get('pin'),str) or not args['pin']:raise ValueError('Placement with anchor=pin requires the exact pin name')
                if args['pin'] not in entry['pin_map']:
                    raise ValueError(f"Unknown anchor pin {args['pin']!r} for {entry['instrument']}; available pins: {', '.join(entry['pin_map'].keys())}")
            if 'angle' in args and not _is_finite_number(args['angle']):raise ValueError('Rotation must be finite')
            if 'mirror_axis' in args and args['mirror_axis'] not in ('horizontal','vertical'):raise ValueError('Invalid mirror axis')
            if 'settings' in args and args['settings'] is not None:
                if not isinstance(args['settings'],dict):raise ValueError('settings must be a mapping')
                if args['settings']:compile_instrument_settings(entry,args['settings'])
        if op=='setInstrumentSettings':
            if not isinstance(args.get('ref'),str) or not args['ref'] or '\0' in args['ref']:raise ValueError('setInstrumentSettings requires component_ref/ref')
            if 'writes' not in args:
                if not isinstance(args.get('settings'),dict) or not args['settings']:
                    raise ValueError('setInstrumentSettings requires a non-empty settings mapping')
        if op in ('rename','place','placeInstrument','copy','replace'):
            for key in ('ref','new_ref'):
                if key in args and (not isinstance(args[key],str) or not args[key] or '\0' in args[key]): raise ValueError('Invalid reference')
        if 'points' in args:
            if not isinstance(args['points'],list) or len(args['points'])<2: raise ValueError('Provide at least two route vertices')
            for point in args['points']:
                if not isinstance(point,dict): raise ValueError('Invalid route coordinate')
                for key in ('x','y'):
                    if not _is_int(point.get(key)) or not -2147483648<=point[key]<=2147483647: raise ValueError('Invalid route coordinate')
        for key in ('name','text','title','page','family','group','manufacturer','expression'):
            if key in args and (not isinstance(args[key],str) or '\x00' in args[key]): raise ValueError('Invalid '+key)

    def history(self, action):
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before undo or redo')
            source,target=(self.undo_stack,self.redo_stack) if action=='undo' else (self.redo_stack,self.undo_stack)
            if not source: raise ValueError('No '+action+' checkpoint')
            before=self.call('projectCircuitState')['states']
            current=self.checkpoint(); checkpoint=source[-1]
            result=self.restore(checkpoint);source.pop();target.append(current)
            after=self.call('projectCircuitState')['states']
            selected=checkpoint.get('sheet_index',0)
            state=next((s for s in after if s.get('sheet_index')==selected),after[0] if after else {})
            return {**result,'undo_depth':len(self.undo_stack),'redo_depth':len(self.redo_stack),'handles_invalidated':True,
                    'handle_generation':self.handle_generation,'state':state,**identity_changes(before,after)}

    def netlist(self):
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before regenerating its netlist or running numeric analysis')
            refreshed=False
            before=None
            checkpoint=None
            if self.topology_dirty:
                before=self.call('projectCircuitState')['states']
                checkpoint=self.checkpoint()
                self.restore(checkpoint);refreshed=True
            result=self.call('netlist')
            from .netlist_diagnostics import hidden_power_diagnostics
            content=result.get('content','')
            diagnostics=hidden_power_diagnostics(content)
            if diagnostics:
                components=self.call('circuitState',{'include_parameters':True})['components']
                diagnostics=hidden_power_diagnostics(content,components)
            result['diagnostics']=diagnostics
            if refreshed:
                after=self.call('projectCircuitState')['states']
                selected=checkpoint.get('sheet_index',0)
                state=next((s for s in after if s.get('sheet_index')==selected),after[0] if after else {})
                return {**result,'handles_invalidated':True,'handle_generation':self.handle_generation,
                        'state':state,**identity_changes(before,after)}
            return {**result,'handles_invalidated':False}

    @staticmethod
    def output_path(value,suffixes,overwrite=False):
        path=Path(value)
        if not path.is_absolute() or path.suffix.lower() not in suffixes or not path.parent.is_dir():
            raise ValueError('Choose an absolute output path in an existing directory: '+str(suffixes))
        if path.exists() and not overwrite: raise FileExistsError('Output already exists')
        return path.resolve()

    def export_image(self, output_path, overwrite=False, dpi=96, scale=1., region=None, fit_content=False,padding=18,show_frame=False,show_grid=False,*,interactive=False,active_component=None,wait_timeout=None,cancel=None):
        if not _is_int(dpi) or dpi<=0 or not _is_finite_number(scale) or scale<=0:
            raise ValueError('DPI and scale must be positive')
        factor=dpi/96*scale
        if not _is_int(padding) or padding<0:raise ValueError('Padding must be nonnegative')
        if region is not None and fit_content:raise ValueError('Choose region or fit_content')
        if not isinstance(show_frame,bool) or not isinstance(show_grid,bool):raise ValueError('show_frame and show_grid must be boolean')
        with self.lock:
            path=self.output_path(output_path,{'.png','.bmp'},overwrite)
            if not interactive:self.call('synchronizeGraphics')
            state=self.call('circuitState');page=state['page'];content=state['content_bounds']
            off_page=[c['ref'] for c in state['components'] if c['bounds']['left']<0 or c['bounds']['top']<0 or c['bounds']['right']>page['width'] or c['bounds']['bottom']>page['height']]
            if fit_content:
                if not content:raise ValueError('No circuit content to fit')
                region={k:v+(-padding if k in ('left','top') else padding) for k,v in content.items()}
            if region is not None:
                if not isinstance(region,dict) or set(region)!={'left','top','right','bottom'} or any(not _is_int(v) or not -2147483648<=v<=2147483647 for v in region.values()):raise ValueError('Region must contain integer left/top/right/bottom sheet coordinates')
                width=region['right']-region['left'];height=region['bottom']-region['top']
                if width<=0 or height<=0:raise ValueError('Export region must have positive size')
            else:
                width,height=page['width'],page['height']
            requested_region=region or page['bounds']
            # The native bitmap exporter always draws sheet coordinates along its
            # viewport boundary. Render a gutter outside the requested region so
            # removing that synthetic frame never removes real circuit content.
            gutter=0 if show_frame else 36
            render_region={k:v+(-gutter if k in ('left','top') else gutter) for k,v in requested_region.items()} if gutter else region
            intermediate=self.folder()/('native-image-'+uuid.uuid4().hex+'.bmp')
            render_args={'path':str(intermediate),'render_scale':factor,'show_frame':show_frame,'show_grid':show_grid,**({'region':render_region} if render_region else {})}
            captured=None
            try:
                if interactive:
                    deadline=None if wait_timeout is None else time.monotonic()+wait_timeout
                    while True:
                        if cancel is not None and cancel.is_set():raise InterruptedError('Workflow cancelled')
                        captured=self.call('exportInteractiveImage',{**render_args,'active_component':active_component})
                        if captured['ready']:break
                        if captured['state'] not in (1,2):raise RuntimeError('Interactive simulation stopped before a frame was captured')
                        if captured['state']==2 or deadline is not None and time.monotonic()>=deadline:
                            raise RuntimeError('No stable lit frame for '+str(active_component)+': '+('simulation is paused; resume before waiting for another scan phase' if captured['state']==2 else 'capture timed out'))
                        time.sleep(.03)
                else:self.call('exportImage',render_args)
                with Image.open(intermediate) as image:
                    if gutter:
                        offset=round(gutter*factor)
                        image=image.crop((offset,offset,offset+round(width*factor),offset+round(height*factor)))
                    image.save(path,format='PNG' if path.suffix.lower()=='.png' else 'BMP',dpi=(dpi,dpi))
                    size=image.size
            finally:intermediate.unlink(missing_ok=True)
            return {'path':str(path),'width':size[0],'height':size[1],'bytes':path.stat().st_size,
                    'dpi':dpi,'scale':scale,'region':region or page['bounds'],'off_page_components':off_page,'show_frame':show_frame,'show_grid':show_grid,
                    'source':'native schematic image renderer',**({k:captured[k] for k in ('capture_mode','display_states','simulation')} if captured else {})}

    def export_interactive_image(self,output_path,overwrite=False,dpi=144,scale=1.,region=None,fit_content=False,padding=18,show_frame=False,show_grid=False,active_component=None,wait_timeout=None,*,cancel=None):
        if wait_timeout is not None and (not _is_finite_number(wait_timeout) or wait_timeout<0):raise ValueError('wait_timeout must be finite and nonnegative')
        if active_component is not None and (not isinstance(active_component,str) or not active_component):raise ValueError('active_component must be a component reference')
        self.interactive_status()
        return self.export_image(output_path,overwrite,dpi,scale,region,fit_content,padding,show_frame,show_grid,
                                 interactive=True,active_component=active_component,wait_timeout=wait_timeout,cancel=cancel)

    def run_dc_sweep(self, source: str, start: float = 0., stop: float = 5., step: float = 0.1) -> dict:
        return self.run_analysis('dc',dc_source=source,dc_start=start,dc_stop=stop,dc_step=step)

    def run_analysis(self, analysis='op', step=1e-5, stop=0.01, use_initial_conditions=False,
                     ac_sweep='dec',ac_points=20,ac_start=1.,ac_stop=100000.,
                     dc_source=None,dc_start=0.,dc_stop=5.,dc_step=0.1,
                     *,persist=False,save_to_source=False,use_saved_settings=False):
        from .settings import validate_analysis_options
        validate_analysis_options(analysis,step,stop,use_initial_conditions,ac_sweep,ac_points,ac_start,ac_stop,
                                  persist,save_to_source,use_saved_settings,dc_source,dc_start,dc_stop,dc_step)
        with self.lock:
            saved=None;native_commands=None
            if persist:
                from .settings import analysis_changes
                saved=self.simulation_settings('analysis',analysis.upper(),
                    analysis_changes(analysis,step,stop,use_initial_conditions,ac_sweep,ac_points,ac_start,ac_stop),save_to_source=save_to_source)
            if persist or use_saved_settings:
                from .settings import saved_execution
                if saved is None:saved=self.simulation_settings('analysis',analysis.upper())
                saved_execution(saved)
                native_commands=self.call('documentAnalysisCommands',{'scope':'analysis','analysis_type':analysis.upper()})
            stem=self.folder()/('analysis-'+uuid.uuid4().hex)
            diagnostic=stem.with_suffix('.json')
            record={'analysis':analysis,'status':'running','use_initial_conditions':use_initial_conditions,
                    **({'dc_source':dc_source,'dc_start':dc_start,'dc_stop':dc_stop,'dc_step':dc_step} if analysis=='dc' else {})}
            diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
            self.analysis_started.clear()
            try:
                netlist=self.netlist()
                record['netlist']={k:v for k,v in netlist.items() if k!='content'}
                if netlist['failed']:raise RuntimeError('Native netlist check failed: '+netlist['messages'])
                missing_rails=[d for d in netlist.get('diagnostics',[]) if d.get('reason')=='missing_connection']
                if missing_rails:
                    from .netlist_diagnostics import explain_analysis_failure
                    result={'failed':True,'stage':'power-rail-preflight','errors':[]}
                    result.update(explain_analysis_failure(result,missing_rails,analysis,use_initial_conditions))
                    record['native']=result
                    raise RuntimeError('Native analysis preflight failed; '+result['error_text'])
                self.numeric_session_used=True
                with self.analysis_transport(stem) as transport:
                    result=self.call('simulate',{'analysis':analysis,'step':step,'stop':stop,'use_initial_conditions':use_initial_conditions,
                        'ac_sweep':ac_sweep,'ac_points':ac_points,'ac_start':ac_start,'ac_stop':ac_stop,'source_path':str(transport.with_suffix('.cir')),
                        **({'dc_source':dc_source,'dc_start':dc_start,'dc_stop':dc_stop,'dc_step':dc_step} if analysis=='dc' else {}),
                        **({'saved_commands':native_commands} if native_commands else {})})
                    record['native']=result
                    self.analysis_started.clear()
                    if result.get('failed'):
                        from .netlist_diagnostics import explain_analysis_failure
                        result.update(explain_analysis_failure(result,netlist.get('diagnostics',[]),analysis,use_initial_conditions))
                        details=result['error_text']
                        raise RuntimeError('Native analysis failed at '+result.get('stage','analysis')+'; '+details)
                    exported=self.call('simulationExport',{'path':str(transport.with_suffix('.raw'))});record['export']=exported
                raw=stem.with_suffix('.raw')
                if not raw.is_file():raise RuntimeError('Native simulator produced no waveform')
                data=parse_raw(raw)
                actual_plot=str(data.get('plot',''))
                if analysis=='dc':
                    lowered=actual_plot.casefold()
                    valid_plot=lowered in {'dc transfer characteristic','dc analysis','dc sweep','dc sweep analysis'} or (
                        'dc' in lowered and 'operating point' not in lowered)
                else:
                    expected={'tran':'Transient Analysis','op':'DC Operating Point','ac':'AC Analysis'}[analysis]
                    valid_plot=actual_plot==expected
                if not valid_plot: raise RuntimeError('Simulator returned an unexpected plot: '+actual_plot)
                csv_path=stem.with_suffix('.csv')
                export_csv(data,csv_path);summary=summarize(data)
            except Exception as error:
                self.analysis_started.clear()
                record.update(status='failed',error=str(error));diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
                raise RuntimeError(str(error)+'; diagnostics: '+str(diagnostic)) from error
            record.update(status='complete',points=data['points'],raw_path=str(raw),csv_path=str(csv_path))
            diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
            handles_invalidated=bool(netlist.get('handles_invalidated',False))
            return {'analysis':analysis,'plot':data['plot'],'points':data['points'],'vectors':summary,'unit_system':'SI',
                    'preview':data['rows'][:10],'raw_path':str(raw),'csv_path':str(csv_path),
                    'netlist_path':str(stem.with_suffix('.cir')),'native_result':result,'diagnostic_path':str(diagnostic),
                    'diagnostics':netlist.get('diagnostics',[]),
                    'handles_invalidated':handles_invalidated,
                    **({k:netlist[k] for k in ('handle_generation','id_map','unresolved_ids','state') if k in netlist} if handles_invalidated else {}),
                    **({'document_settings':{'revision':saved['revision'],'saved_to_file':saved['saved_to_file'],
                        'analysis_type':saved['analysis_type'],'commands':native_commands,**({'save':saved['save']} if 'save' in saved else {})}} if saved else {})}

    def start_analysis(self,analysis='tran',step=1e-5,stop=0.01,use_initial_conditions=False,*,persist=False,save_to_source=False,use_saved_settings=False):
        from .settings import validate_analysis_options,analysis_changes
        validate_analysis_options(analysis,step,stop,use_initial_conditions,persist=persist,save_to_source=save_to_source,use_saved_settings=use_saved_settings)
        if not self.agent: raise RuntimeError('Open a native project first')
        if self.analysis_job and self.analysis_job['status'] in ('running','pause_requested','stop_requested'):
            raise RuntimeError('An analysis is already running')
        prepared=None
        if persist:
            prepared=self.simulation_settings('analysis',analysis.upper(),
                analysis_changes(analysis,step,stop,use_initial_conditions,'dec',20,1.,100000.),save_to_source=save_to_source)
        self.analysis_started.clear()
        job={'id':uuid.uuid4().hex,'status':'running','started':time.time()};self.analysis_job=job
        def run():
            try:
                job['result']=self.run_analysis(analysis,step,stop,use_initial_conditions,use_saved_settings=persist or use_saved_settings)
                if prepared:
                    job['result']['document_settings'].update(saved_to_file=prepared['saved_to_file'],
                        **({'save':prepared['save']} if 'save' in prepared else {}))
                job['status']='stopped' if job.get('stop_requested') else 'complete'
            except Exception as error:
                job['error']=str(error);job['status']='stopped' if job.get('stop_requested') else 'failed'
            finally:job['finished']=time.time()
        thread=threading.Thread(target=run,daemon=True);self.analysis_thread=thread;thread.start()
        return {'id':job['id'],'status':job['status']}

    def analysis_status(self):
        if not self.analysis_job: return {'status':'idle'}
        return {**self.analysis_job,'native_command_started':self.analysis_started.is_set()}

    def control_analysis(self,action):
        if action not in ('pause','resume','stop'): raise ValueError('Choose pause, resume or stop')
        job=self.analysis_job
        if not job or job['status'] not in ('running','pause_requested','stop_requested'):
            return {'action':action,'requested':False,'status':job['status'] if job else 'idle'}
        if not self.analysis_started.is_set(): raise RuntimeError('Analysis preparation is still running; retry when native_command_started is true')
        job['status']={'pause':'pause_requested','resume':'running','stop':'stop_requested'}[action]
        if action=='stop':job['stop_requested']=True
        result=self.agent.exports_sync.control(action)
        return {**result,'status':job['status']}

    def interactive_status(self,include_displays=False):
        job=self.analysis_job
        if job and job['status'] in ('running','pause_requested','stop_requested'):
            raise RuntimeError('A numeric analysis is active; use native_analysis_status and native_control_analysis')
        return self.call('interactiveStatus',{'include_displays':include_displays})

    def configure_interactive(self,time_step=None,max_time_step=None,real_time=None,reset=False,*,persist=False,save_to_source=False):
        configuration={}
        for name,value in [('time_step',time_step),('max_time_step',max_time_step)]:
            if value is None:continue
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<=0:
                raise ValueError(name+' must be a finite positive number')
            configuration[name]=value
        if real_time is not None:
            if not isinstance(real_time,bool):raise ValueError('real_time must be boolean')
            configuration['real_time']=real_time
        if not isinstance(reset,bool):raise ValueError('reset must be boolean')
        if not isinstance(persist,bool) or not isinstance(save_to_source,bool):raise ValueError('persist and save_to_source must be boolean')
        if save_to_source and not persist:raise ValueError('save_to_source requires persist=true')
        if reset and configuration:raise ValueError('reset cannot be combined with simulation options')
        with self.lock:
            if configuration or reset or save_to_source:
                state=self.interactive_status()
                if state['state_name'] in ('running','paused'):raise RuntimeError('Stop interactive simulation before changing its options')
            if not persist:return self.call('interactiveOptions',{'configuration':configuration,'reset':reset})
            if not configuration and not reset and not save_to_source:
                return {**self.call('documentInteractiveOptions'),'saved_to_file':False}
            checkpoint=self.checkpoint()
            temporary=self.call('interactiveOptions').get('configuration',{})
            try:
                result=self.call('documentInteractiveOptions',{'configuration':configuration,'reset':reset})
                expected={'time_step':None,'max_time_step':None,'real_time':True} if reset else configuration
                if any(result['configuration'].get(key)!=value for key,value in expected.items()):
                    raise RuntimeError('Native document interactive settings failed readback')
                if result['changed']:self.call('markModified')
                # A previous temporary override must not mask the document's settings.
                self.call('interactiveOptions',{'reset':True})
                if save_to_source:result['save']=self._save_source()
            except Exception:
                self.restore(checkpoint)
                if temporary:self.call('interactiveOptions',{'configuration':temporary})
                raise
            self.undo_stack.append(checkpoint);self.redo_stack.clear()
            return {**result,'saved_to_file':save_to_source,'handles_invalidated':False}

    def control_interactive(self,action,wait_timeout=5.0):
        if action not in ('start','pause','resume','stop'):raise ValueError('Choose start, pause, resume or stop')
        if not _is_finite_number(wait_timeout) or wait_timeout<0:raise ValueError('wait_timeout must be finite and nonnegative')
        with self.lock:
            deadline=time.monotonic()+wait_timeout
            before=self.interactive_status();state=before['state_name']
            target={'start':'running','resume':'running','pause':'paused','stop':'stopped'}[action]
            if (state==target or (action=='stop' and state=='unprepared')) and not self.numeric_session_used and not (action=='stop' and before['remote_initialized']):
                return {**before,'action':action,'requested':False,'transition_confirmed':True,'already_in_state':True}
            if (action=='start' and state=='paused') or (action=='resume' and state!='paused') or (action=='pause' and state!='running'):
                raise ValueError(f'Cannot {action} interactive simulation while {state}')
            cleaned=False
            if self.numeric_session_used or (action=='start' and before['remote_initialized'] and state=='stopped'):
                if state in ('stopped','unprepared'):
                    self.call('cleanupNumericSession')
                self.call('interactiveCommand',{'action':'stop'})
                while True:
                    current=self.interactive_status()
                    if not current['remote_initialized']:break
                    if time.monotonic()>=deadline:
                        return {**current,'action':action,'requested':True,'previous_state':state,
                            'transition_confirmed':False,'numeric_context_cleaned':False,
                            'pending_phase':'numeric_cleanup','handles_invalidated':False}
                    time.sleep(min(.1,max(0,deadline-time.monotonic())))
                self.numeric_session_used=False;cleaned=True
                if action=='stop':
                    return {**current,'action':action,'requested':True,'previous_state':state,'transition_confirmed':True,'numeric_context_cleaned':True}
            command=self.call('interactiveCommand',{'action':action})
            while True:
                current=self.interactive_status()
                confirmed=(current['state_name']==target or (action=='stop' and current['state_name']=='unprepared')) and (action!='stop' or not current['remote_initialized'])
                if confirmed or time.monotonic()>=deadline:
                    return {**current,**command,'previous_state':state,'transition_confirmed':confirmed,'numeric_context_cleaned':cleaned,'handles_invalidated':False}
                time.sleep(.1)

    def read_waveform(self,path,offset=0,limit=1000,plot_index=0):
        source=Path(path)
        if not source.is_absolute() or not source.is_file() or source.suffix.lower()!='.raw': raise ValueError('Choose an existing absolute ASCII RAW path')
        if not _is_int(offset) or not _is_int(limit) or offset<0 or limit<1: raise ValueError('Invalid waveform offset or limit')
        first=parse_raw(source);plots=[first,*first.pop('additional_plots')]
        if not _is_int(plot_index) or not 0<=plot_index<len(plots):raise ValueError('Invalid waveform plot index')
        data=plots[plot_index];rows=data['rows']
        return {**{k:v for k,v in data.items() if k!='rows'},'plot_index':plot_index,
                'plots':[{k:v for k,v in plot.items() if k!='rows'} for plot in plots],
                'event_fields':['time','rising','falling'] if data['digital'] else None,
                'offset':offset,'rows':rows[offset:offset+limit],'has_more':offset+limit<len(rows)}

    def attach(self,pid,project_index=0):
        with self.lock:
            if self.process and self.process.poll() is None: raise RuntimeError('Close or detach current native session first')
            found=next((p for p in frida.get_local_device().enumerate_processes() if p.pid==pid and p.name.lower() in ('multisim','multisim.exe')),None)
            if not found: raise ValueError('PID is not a running Multisim process')
            self.close();self.owned=False;self.process=ExistingProcess(pid)
            folder=DATA_DIR/'sessions'/uuid.uuid4().hex;folder.mkdir(parents=True)
            self.session_dir=folder;self.isolated=False;self.working=folder/'attached-session.ms14';self.source=None;self.source_hash=None
            try:
                self.session=frida.attach(pid)
                inspector=self.session.create_script('rpc.exports.modules=()=>Process.enumerateModules().map(m=>({name:m.name,path:m.path}));',runtime='v8')
                inspector.load();modules={m['name'].lower():m['path'] for m in inspector.exports_sync.modules()};inspector.unload()
                for name in ('multisim.exe','DrwEngine.dll','SCH_CAP.dll','Od101dll.dll'):
                    if name.lower() not in modules:
                        raise RuntimeError('Attached process is not ready: '+name)
                code=editor_script()
                self.agent=self.session.create_script(code,runtime='v8');self.agent.on('message',self._message);self.agent.load()
                self.call('selectProject',{'index':project_index})
                info=self.call('inspect');source=Path(info['projectPath'])
                self.source=source.resolve() if source.is_absolute() and source.is_file() else None
                self.source_hash=sha256(self.source) if self.source else None
                if self.source:self.working=self.source
                self.undo_stack,self.redo_stack=[],[];self.topology_dirty=False
                backup=self.checkpoint()
                self.handle_generation += 1
                return {**info,'owned':False,'backup':backup['path'],'source_path':str(self.source) if self.source else None}
            except Exception:
                self.close();raise

    def create(self,title='Circuit',output_path=None):
        with self.lock:
            if self.process and self.process.poll() is None: raise RuntimeError('Close or detach the current project first')
            if not title or not isinstance(title,str) or "\0" in title: raise ValueError('Provide a nonempty native title')
            directory=Path.cwd()
            if output_path:
                path=Path(output_path).expanduser()
                if not path.is_absolute():raise ValueError('output_path must be an absolute .ms14 file path')
                path=path.resolve()
                if path.suffix.lower()!='.ms14' or not path.parent.is_dir():raise ValueError('Choose an .ms14 output in an existing directory')
                if path.exists():raise FileExistsError('Circuit already exists; open it with native_open_circuit to edit it')
            else:
                stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',title).strip(' .') or 'Circuit'
                if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',stem):stem='Circuit-'+stem
                path=directory/(stem+'.ms14');index=2
                while path.exists():path=directory/(stem+'-'+str(index)+'.ms14');index+=1
            with path.open('xb') as target, (ROOT/'assets'/'blank14.3.ms14').open('rb') as template:shutil.copyfileobj(template,target)
            try:
                result=self.open_circuit(str(path))
                if self.call('components')['components'] or self.call('wires')['wires']:
                    raise RuntimeError('Native blank template contains unexpected objects')
                self.edit('sheetTitle',{'title':title})
                saved=self.save_source()
                return {**result,'title':title,'blank':True,'path':str(path),'save':saved}
            except BaseException:
                try:
                    self.close()
                finally:
                    if self.source==path or self.working==path:
                        self.source=self.working=self.source_hash=self.working_hash=None
                    path.unlink(missing_ok=True)
                raise

    def close(self):
        job=getattr(self,'analysis_job',None)
        if self.agent and job and job['status'] in ('running','pause_requested','stop_requested'):
            try:self.control_analysis('stop')
            except Exception:pass
        result = super().close()
        self.numeric_session_used = False
        return result
