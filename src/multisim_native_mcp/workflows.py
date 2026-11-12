"""Stage-based native execution, result bindings and resumable jobs."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

from .contracts import normalize_criteria
from .jobs import ExperimentStore
from .layout import check_layout
from .measurements import measure
from .paths import DATA_DIR
from .verification import decode_display, verify
from .waveforms import parse_raw
from .workflow_contracts import ComponentRequest, WorkflowPlan
from .workflow_values import resolve


class NeedsInput(RuntimeError):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


def process_alive(pid):
    if not isinstance(pid,int) or pid<=0:return False
    if pid==os.getpid():return True
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        code=wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:kernel.CloseHandle(handle)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def semantic(value):
    """A drawing revision independent of native allocation addresses and text caches."""
    if isinstance(value, list):
        values=[semantic(v) for v in value]
        if values and all(isinstance(v,dict) for v in values) and any(all(keys<=v.keys() for v in values) for keys in ({'name'},{'ref','transform'},{'source','target'},{'kind','text'},{'text','transform'})):
            values.sort(key=lambda v:json.dumps(v,sort_keys=True))
        return values
    if isinstance(value, dict):
        return {k:semantic(v) for k,v in value.items() if k not in {
            'id','component_id','ci','path','graphic_position','graphics_aligned','bounds','body_bounds',
            'content_bounds','center','selected','coordinate_system','handle_epoch'}}
    if isinstance(value,float):return round(value,8)
    return value


def remap_bindings(bindings, before, after):
    """Rebind only uniquely identifiable objects across a controlled native reopen."""
    mapping={};old_ids=set()
    def key(c):
        return digest({'library':c.get('library'),'transform':c['transform'],
                       'pins':sorted((p['name'],p['x'],p['y']) for p in c['pins'])})
    grouped={}
    for c in after.get('components',[]):grouped.setdefault(key(c),[]).append(c)
    for c in before.get('components',[]):
        old_ids.add(c['id']);old_ids.update(p['id'] for p in c['pins'])
        same_epoch=before.get('handle_epoch')==after.get('handle_epoch')
        candidates=[q for q in after.get('components',[]) if same_epoch and q['id']==c['id'] and
                    (q['ref'],q.get('local_ref'),q.get('library'))==(c['ref'],c.get('local_ref'),c.get('library'))]
        if not candidates:
            candidates=grouped.get(key(c),[])
            named=[q for q in candidates if (q['ref'],q.get('local_ref'))==(c['ref'],c.get('local_ref'))]
            if len(named)==1:candidates=named
        if len(candidates)!=1:continue
        target=candidates[0];mapping[c['id']]=target['id']
        for p in c['pins']:
            hits=[q for q in target['pins'] if (q['name'],q['x'],q['y'])==(p['name'],p['x'],p['y'])]
            if len(hits)==1:mapping[p['id']]=hits[0]['id']
        for l in c.get('labels',[]):
            old_ids.add(l['id'])
            hits=[q for q in target.get('labels',[]) if (q['kind'],q.get('transform'))==(l['kind'],l.get('transform'))]
            if len(hits)==1:mapping[l['id']]=hits[0]['id']
    def endpoint(e):return (e.get('ref'),e.get('pin'),e['x'],e['y'])
    for t in before.get('texts',[]):
        old_ids.add(t['id'])
        hits=[q for q in after.get('texts',[]) if (q['text'],q['transform'])==(t['text'],t['transform'])]
        same=[q for q in after.get('texts',[]) if before.get('handle_epoch')==after.get('handle_epoch') and q['id']==t['id']]
        if len(same or hits)==1:mapping[t['id']]=(same or hits)[0]['id']
    for w in before.get('wires',[]):
        old_ids.add(w['id']);old_ids.update(w[e]['id'] for e in ('source','target'))
        hits=[q for q in after.get('wires',[]) if q['points']==w['points'] and
              endpoint(q['source'])==endpoint(w['source']) and endpoint(q['target'])==endpoint(w['target'])]
        if len(hits)==1:
            target=hits[0];mapping[w['id']]=target['id']
            for e in ('source','target'):mapping[w[e]['id']]=target[e]['id']
    def update(value):
        if isinstance(value,list):return [update(v) for v in value]
        if isinstance(value,dict):return {k:update(v) for k,v in value.items()}
        if isinstance(value,str) and value in old_ids:
            # Unmatched old IDs become an explicit invalid binding, never a guessed object.
            return mapping.get(value,{'$invalid_handle':value})
        return value
    return update(bindings)


def ensure_valid(value):
    if isinstance(value,list):
        for v in value:ensure_valid(v)
    elif isinstance(value,dict):
        if '$invalid_handle' in value:raise NeedsInput('A result binding no longer identifies one native object; select it from the current session state')
        for v in value.values():ensure_valid(v)


class WorkflowManager:
    def __init__(self,host,root=None):
        self.host=host;self.store=ExperimentStore(root or DATA_DIR/'workflows')
        self.guard=threading.RLock();self.active=None;self.thread=None
        self.cancel_event=threading.Event();self.finished=threading.Event()
        self.record=None;self.cache=None;self.catalog={};self.catalog_session=None
        for p in self.store.root.glob('*.json'):
            record=self.store.read(p.stem)
            if record['status'] in ('running','queued','cancel_requested') and not process_alive(record.get('owner_pid')):
                record.update(status='interrupted',finished=time.time());self.store.write(record)

    def _capture(self, rebind=True):
        state=self.host.call('circuitState',{'include_parameters':True})
        state['handle_epoch']=[getattr(getattr(self.host,'process',None),'pid',0),getattr(self.host,'handle_generation',0)]
        state['content_revision']=digest(semantic(state))
        state['revision']=digest({'content':state['content_revision'],'epoch':state['handle_epoch'],
                                  'handles':[(c['id'],[p['id'] for p in c['pins']]) for c in state['components']],
                                  'wires':[w['id'] for w in state['wires']],'texts':[t['id'] for t in state.get('texts',[])]})
        if rebind and self.active and self.record and self.cache:
            self.record['bindings']=remap_bindings(self.record['bindings'],self.cache,state)
        self.cache=state
        return state

    def session_state(self,since_revision=None,include_parameters=False):
        with self.host.lock:
            before=self.cache;state=self._capture(rebind=False)
            if since_revision==state['revision']:return {'revision':state['revision'],'changed':False}
            if before and since_revision==before['revision']:
                old={c['id']:c for c in before['components']};current={c['id']:c for c in state['components']}
                result={'revision':state['revision'],'changed':True,'full':False,
                        'components':[copy.deepcopy(c) for k,c in current.items() if semantic(c)!=semantic(old.get(k))],
                        'removed_component_ids':list(old.keys()-current.keys()),'wires':state['wires'],'page':state['page'],
                        'texts':state.get('texts',[]),'removed_text_ids':list({t['id'] for t in before.get('texts',[])}-{t['id'] for t in state.get('texts',[])})}
            else:result={'revision':state['revision'],'changed':True,'full':True,'state':copy.deepcopy(state)}
            if not include_parameters:
                for c in result.get('components',result.get('state',{}).get('components',[])):c.pop('parameters',None)
            return result

    def _preflight_paths(self,steps):
        seen=set();issues=[];protected=[];current=self.host.source
        for step in steps:
            if step['kind']=='session' and step['mode']=='open':
                source=Path(step['source_path']);current=source
                if step.get('isolated_copy'):protected.append(source)
                if not source.is_absolute() or source.suffix.lower()!='.ms14' or not source.is_file():
                    issues.append({'stage':step['id'],'path':str(source),'error':'Choose an existing absolute .ms14 source'})
            elif step['kind']=='session' and step['mode']=='create':
                current=Path(step['output_path']) if step.get('output_path') else None
        for step in steps:
            if step['kind']=='save' and not step.get('output_path'):
                if not current and not any(s['kind']=='session' and s['mode'] in ('attach','create') for s in steps):
                    issues.append({'stage':step['id'],'error':'Source save requires an existing source circuit'})
                continue
            outputs=[step] if step['kind'] in ('save','export') else step.get('captures',[])
            for output in outputs:
                path=Path(output['output_path'])
                suffixes={'.ms14'} if step['kind']=='save' else {'.png','.bmp'}
                if not path.is_absolute() or path.suffix.lower() not in suffixes or not path.parent.is_dir():
                    issues.append({'stage':step['id'],'path':str(path),'error':'Choose an absolute output with an existing parent directory'})
                elif path.exists() and not step.get('overwrite',False) and not (step['kind']=='save' and current and path.resolve()==current.resolve() and not protected):
                    issues.append({'stage':step['id'],'path':str(path),'error':'Output exists; specify overwrite=true or another path'})
                elif str(path.resolve()).lower() in seen:
                    issues.append({'stage':step['id'],'path':str(path),'error':'Output path is used by another stage'})
                seen.add(str(path.resolve()).lower())
                if any(path.resolve()==source.resolve() or (path.exists() and source.exists() and path.samefile(source)) for source in protected):
                    issues.append({'stage':step['id'],'path':str(path),'error':'The source circuit is protected'})
        if issues:raise NeedsInput('Workflow output preflight failed',{'issues':issues})

    def prepare(self,components,refresh=False):
        requests=[c.model_dump() if isinstance(c,ComponentRequest) else ComponentRequest.model_validate(c).model_dump() for c in components]
        if not requests:raise ValueError('Prepare nonempty component types')
        with self.host.lock:
            session=str(self.host.working)
            if self.catalog_session!=session or refresh:self.catalog={};self.catalog_session=session
            missing=[r for r in requests if digest(r) not in self.catalog];issues=[];values=[]
            if missing:
                snapshot=self.host.checkpoint();before=self._capture();options=self.host.call('wiringOptions')
                try:
                    self.host.call('wiringOptions',{'connect_touching':False})
                    for i,r in enumerate(missing):
                        search=self.host.call('librarySearch',{'query':r['name'],'family':r['family'],'group':r['group'],'limit':None})
                        candidates=[c for c in search['results'] if c.get('Component_Name','').casefold()==r['name'].casefold()]
                        if r['manufacturer']:candidates=[c for c in candidates if c.get('Manufacturer_Name','').casefold()==r['manufacturer'].casefold()]
                        if len(candidates)!=1:
                            issues.append({'component':r,'error':'Expected one exact library component','candidates':candidates or search['results']});continue
                        try:
                            ref='MCP_PREPARE_'+uuid.uuid4().hex[:12]
                            placed=self.host.call('place',{**r,'ref':ref,'x':180,'y':180,'anchor':'center'})
                            c=placed['component'];actual=placed['placement']['actual']
                            entry={'request':r,'library':c.get('library'),'anchor':'center','coordinate_system':'sheet_units',
                                   'pin_offsets_relative_to':'placement.actual (center anchor)',
                                   'placement':placed['placement'],'pins':[{'name':p['name'],'dx':p['x']-actual['x'],'dy':p['y']-actual['y']} for p in c['pins']],
                                   'parameters':placed['parameters'],'candidate':candidates[0]}
                            self.catalog[digest(r)]=entry
                        except Exception as error:issues.append({'component':r,'error':str(error)})
                finally:
                    self.host.restore(snapshot)
                    self.host.call('wiringOptions',{'connect_touching':options['connect_touching']})
                    self.cache=before;self._capture()
            for r in requests:
                if digest(r) in self.catalog:values.append(self.catalog[digest(r)])
            if issues:raise NeedsInput('Component preparation requires library choices',{'components':values,'issues':issues})
            return {'components':values,'prepared':len(values),'cache_hits':len(requests)-len(missing),
                    'revision':self.cache['revision'] if self.cache else None}

    def start(self,plan,wait_timeout=30):
        self._wait_value(wait_timeout)
        plan=plan if isinstance(plan,WorkflowPlan) else WorkflowPlan.model_validate(plan)
        with self.guard:
            if self.active:raise RuntimeError('A workflow is already running')
            record={'id':uuid.uuid4().hex,'status':'queued','created':time.time(),'plan':plan.model_dump(exclude_none=True),
                    'next_step':0,'completed':[],'bindings':{},'stats':{'external_calls':1,'retries':0},'events':[],
                    'owner_pid':os.getpid()}
            self.record=record;self.store.write(record);self._launch(record)
        return self.status(record['id'],wait_timeout,count=False)

    def _launch(self,record):
        self.active=record['id'];self.cancel_event.clear();self.finished.clear()
        self.thread=threading.Thread(target=self._execute,args=(record,),daemon=True);self.thread.start()

    def _save_record(self,record):
        with self.guard:self.store.write(record)

    def _execute(self,record):
        started=time.monotonic();calls=getattr(self.host,'native_call_count',0);seconds=getattr(self.host,'native_call_seconds',0.)
        record['status']='running';record['started']=time.time();record.pop('error',None);record.pop('failure',None)
        record.pop('cancel_reason',None)
        runtime=record['plan'].get('max_runtime');budget=None
        if runtime is not None:
            budget=threading.Timer(runtime,lambda:self._request_cancel(record['id'],'Requested workflow runtime reached'))
            budget.daemon=True;budget.start()
        try:
            with self.host.lock:
                steps=record['plan']['steps'];self._preflight_paths(steps[record['next_step']:])
                if self.host.agent:
                    state=self._capture()
                    expected=record.get('resume_revision') or record['plan'].get('expected_revision')
                    if record.pop('reopened_for_resume',False):
                        if record.get('state',{}).get('content_revision')!=state['content_revision']:
                            raise NeedsInput('Saved resume checkpoint differs from the successful phase')
                    elif expected and state['revision']!=expected:raise NeedsInput('Circuit changed since the supplied revision',{'expected_revision':expected,'actual_revision':state['revision']})
                for index in range(record['next_step'],len(steps)):
                    record['next_step']=index;stage=steps[index]
                    if self.cancel_event.is_set():raise InterruptedError('Workflow cancelled')
                    if runtime is not None and time.monotonic()-started>runtime:raise InterruptedError('Workflow runtime limit reached')
                    if self.host.agent and self.cache:
                        expected=self.cache['revision'];actual=self._capture()
                        if actual['revision']!=expected:raise NeedsInput('Circuit changed outside this workflow',{'expected_revision':expected,'actual_revision':actual['revision']})
                    phase_started=time.monotonic();self._save_record(record)
                    result=self._stage(stage,record)
                    record['bindings'][stage['id']]=result
                    if self.host.agent:
                        self._capture()
                        record['state']=self.cache;record['revision']=self.cache['revision']
                        if not (stage['kind']=='interactive' and not stage.get('stop_after',True)):
                            record['resume_checkpoint']=self.host.checkpoint()
                            if hasattr(self.host,'document_context'):record['document']=self.host.document_context()
                    record['completed'].append({'id':stage['id'],'kind':stage['kind'],'seconds':round(time.monotonic()-phase_started,4)})
                    record['next_step']=index+1
                    record.get('partial_outputs',{}).pop(stage['id'],None)
                    record['events'].append({'stage':stage['id'],'status':'complete','time':time.time()})
                    self._save_record(record)
                record['status']='complete'
        except InterruptedError as error:
            record.update(status='cancelled',error=str(error))
        except Exception as error:
            record.update(status='needs_input' if isinstance(error,NeedsInput) else 'failed',error=str(error))
            record['failure']={'step_index':record['next_step'],'stage':record['plan']['steps'][min(record['next_step'],len(record['plan']['steps'])-1)]['id'],
                               'details':getattr(error,'details',None) or getattr(error,'result',None)}
            if self.host.agent:
                try:
                    self._capture();record['state']=self.cache;record['revision']=self.cache['revision']
                except Exception as diagnostic:record['diagnostic_error']=str(diagnostic)
        finally:
            if budget:budget.cancel()
            if self.cancel_event.is_set():record.update(status='cancelled',error=record.get('cancel_reason','Workflow cancelled'))
            record['stats']['native_calls']=record['stats'].get('native_calls',0)+getattr(self.host,'native_call_count',0)-calls
            record['stats']['native_seconds']=round(record['stats'].get('native_seconds',0)+getattr(self.host,'native_call_seconds',0.)-seconds,4)
            record['stats']['elapsed_seconds']=round(record['stats'].get('elapsed_seconds',0)+time.monotonic()-started,4)
            record['finished']=time.time()
            try:self._save_record(record)
            except Exception as error:record.update(status='failed',error='Cannot persist workflow result: '+str(error))
            finally:
                with self.guard:self.active=None;self.finished.set()

    def _preflight_edits(self,ops,bindings):
        requests=[];schemas={};issues=[]
        for op in ops:
            if op['operation']=='place':
                a=op.get('arguments',{});r={k:a.get(k,'') for k in ('name','family','group','manufacturer')}
                if not isinstance(r['name'],str):raise NeedsInput('Library names must be literal strings during preflight')
                if r not in requests:requests.append(r)
        if requests:self.prepare(requests)
        for op in ops:
            a=op.get('arguments',{})
            if op['operation']=='place':
                r={k:a.get(k,'') for k in ('name','family','group','manufacturer')};schema=self.catalog[digest(r)]
                if op.get('bind'):schemas[op['bind']]=schema
                if a.get('anchor')=='pin' and a.get('pin') not in {p['name'] for p in schema['pins']}:
                    issues.append({'operation':op.get('bind'),'error':'Unknown placement anchor pin','available':schema['pins']})
                if 'value' in a:
                    slots=[p for p in schema['parameters'] if p.get('role')=='value']
                    if len(slots)!=1:issues.append({'operation':op.get('bind'),'error':'Primary value slot is ambiguous; provide indexed parameters','available':schema['parameters']})
                    else:
                        value=a.pop('value');slot=slots[0]['index']
                        if any(p.get('index')==slot for p in a.get('parameters',[])):issues.append({'operation':op.get('bind'),'error':'Primary value supplied twice'})
                        a.setdefault('parameters',[]).append({'index':slot,'expression' if isinstance(value,str) else 'value':value})
                indexes={p['index'] for p in schema['parameters']}
                for p in a.get('parameters',[]):
                    if p.get('index') not in indexes:issues.append({'operation':op.get('bind') or a.get('ref'),'error':'Unknown parameter slot','available':schema['parameters']})
            if op['operation']=='setParameter' and 'index' not in a:
                target=a.get('ref');alias=target.get('$ref','').split('.')[0] if isinstance(target,dict) else None
                if alias in schemas:parameters=schemas[alias]['parameters']
                else:parameters=self.host.call('parameters',{'ref':resolve(target,bindings)})['parameters']
                slots=[p for p in parameters if p.get('role')==a.get('role','value') and ('name' not in a or p.get('name')==a['name'])]
                if len(slots)!=1:issues.append({'operation':op,'error':'Parameter selector must match one slot','available':parameters})
                else:a['index']=slots[0]['index'];a.pop('role',None);a.pop('name',None)
            for end in ('source','target'):
                e=a.get(end,{})
                if not isinstance(e,dict):continue
                ref=e.get('ref');alias=ref.get('$ref','').split('.')[0] if isinstance(ref,dict) else None
                if alias in schemas and isinstance(e.get('pin'),str) and e['pin'] not in {p['name'] for p in schemas[alias]['pins']}:
                    issues.append({'endpoint':e,'error':'Unknown pin','available':schemas[alias]['pins']})
        if issues:raise NeedsInput('Edit preflight failed',{'issues':issues})

    def _signal(self,value):
        if isinstance(value,str):return value
        if not isinstance(value,dict):raise ValueError('Signal must be a vector name or a component/pin selector')
        if set(value)=={'ref','pin'}:return self.host.call('signalForPin',value)['signal']
        if set(value)=={'current'}:
            target=value['current'];cs=self.cache['components']
            hits=[c for c in cs if target in (c['id'],c['ref'])]
            if len(hits)!=1:raise NeedsInput('Current selector must identify one component')
            return 'I('+hits[0]['ref']+')'
        raise ValueError('Signal selector requires {ref,pin} or {current}')

    def _measure(self,raw_path,measurements,criteria):
        requests=copy.deepcopy(measurements)
        for m in requests:
            m['signal']=self._signal(m['signal'])
            if m.get('reference') is not None:m['reference']=self._signal(m['reference'])
        values=measure(parse_raw(Path(raw_path)),requests) if requests else []
        acceptance=verify(values,normalize_criteria(criteria,{m['id'] for m in values})) if criteria else {'passed':True,'criteria':[]}
        result={'raw_path':raw_path,'measurements':values,**acceptance}
        if not result['passed']:raise NeedsInput('Waveform acceptance failed',result)
        return result

    def _stage(self,stage,record):
        kind=stage['kind'];payload={k:v for k,v in stage.items() if k not in ('id','kind')}
        a=payload if kind=='edit' else resolve(payload,record['bindings']);ensure_valid(a)
        if kind=='session':
            if a['mode']=='create':result=self.host.create(a.get('title','Circuit'),a['output_path'])
            elif a['mode']=='open':
                open_document=self.host.open_copy if a.get('isolated_copy') else self.host.open_circuit
                result=open_document(a['source_path'],a.get('output_path')) if a.get('isolated_copy') else open_document(a['source_path'])
            else:result=self.host.attach(a['pid'],a.get('project_index',0))
            self.cache=None;self.catalog={};self._capture(rebind=False);return {**result,'state':self.cache}
        if kind=='prepare':return self.prepare(a['components'])
        if kind=='select':
            selected={};issues=[]
            for name,selector in a['components'].items():
                hits=[]
                for c in self.cache['components']:
                    if any(c.get(k)!=selector[k] for k in ('ref','local_ref','id') if k in selector):continue
                    if 'x' in selector:
                        points=[p for p in c['pins'] if p['name']==selector['pin']] if selector.get('pin') else [{'x':c['transform'][4],'y':c['transform'][5]}]
                        if not any((p['x'],p['y'])==(selector['x'],selector['y']) for p in points):continue
                    hits.append(c)
                if len(hits)!=1:issues.append({'selection':name,'selector':selector,'candidates':hits})
                else:selected[name]=hits[0]
            if issues:raise NeedsInput('Component selection requires unique matches',{'issues':issues})
            return {'components':selected}
        if kind=='wiring':
            persist=a.pop('persist',False)
            result=self.host.configure_wiring(**a,persist=True) if persist else self.host.call('wiringOptions',a)
            record['wiring_options']={k:result[k] for k in ('autowire_on_connection','autowire_on_move','connect_touching','move_connection_limit')}
            return result
        if kind=='simulation_settings':return self.host.simulation_settings(**a)
        if kind=='sheet_display':return self.host.configure_sheet_display(**a)
        if kind=='edit':
            # Keep intra-stage references unresolved until their native operation executes.
            ops=copy.deepcopy(stage['operations']);self._preflight_edits(ops,record['bindings'])
            previous=copy.deepcopy(record['bindings'])
            try:
                result=self.host.edit_sequence(ops,record['bindings'],self.cancel_event)
                record['bindings']=result.pop('bindings');return result
            except Exception:
                record['bindings']=previous;raise
        if kind=='netlist':
            result=self.host.netlist();self._capture()
            if result['failed']:raise NeedsInput('Netlist check failed',result)
            return result
        if kind=='layout':
            if a.get('repair_geometry'):self.host.edit('repairWireGeometry',{})
            result=check_layout(self.host.call('componentBounds')['components'],self.host.call('wires')['wires'])
            if result['errors'] or (a.get('require_no_warnings') and result['warnings']):raise NeedsInput('Layout check failed',result)
            return result
        if kind=='analysis':
            native=self.host.run_analysis(**a.get('options',{}));self._capture()
            # Refresh selectors after native netlist preparation invalidates handles.
            measurements=resolve(stage.get('measurements',[]),record['bindings']);ensure_valid(measurements)
            try:checked=self._measure(native['raw_path'],measurements,a.get('criteria',[]))
            except NeedsInput as error:
                error.result={**native,**(error.result or {})};raise
            return {**native,**checked}
        if kind=='verify':return self._measure(a['raw_path'],a['measurements'],a['criteria'])
        if kind=='decode':
            for digit in a['digits']:
                digit['segments']=[self._signal(s) for s in digit['segments']]
                digit['select']=self._signal(digit['select'])
            result=decode_display(parse_raw(Path(a['raw_path'])),a['digits'],a.get('expected'),**a.get('options',{}))
            if not result['passed']:raise NeedsInput('Display acceptance failed',result)
            return result
        if kind=='save':
            if a.pop('save_to_source',False):return self.host.save_source(allow_off_page=a.get('allow_off_page',False),**({'verify':False} if not a.get('verify',True) else {}))
            if not a.get('output_path'):return self.host.save_current(allow_off_page=a.get('allow_off_page',False),**({'verify':False} if not a.get('verify',True) else {}))
            return self.host.save_copy(**a)
        if kind=='export':return self.host.export_image(**a)
        if kind=='interactive':
            if a.get('persist'):
                configuration=self.host.configure_interactive(a.get('time_step'),a.get('max_time_step'),a.get('real_time'),persist=True)
            else:configuration=self.host.configure_interactive(a.get('time_step'),a.get('max_time_step'),a.get('real_time'))
            frames=[]
            try:
                started=self.host.control_interactive('start',15)
                if not started['transition_confirmed']:raise NeedsInput('Interactive start was not confirmed',started)
                for capture in a['captures']:
                    if self.cancel_event.is_set():raise InterruptedError('Workflow cancelled')
                    if self.host.interactive_status()['state_name']=='paused':self.host.control_interactive('resume',15)
                    selected=capture.get('active_component')
                    if selected:
                        hits=[c for c in self.cache['components'] if selected in (c['ref'],c['id'])]
                        if len(hits)!=1:raise NeedsInput('Capture selector must identify one display')
                        selected=hits[0]['ref']
                    expected=capture.get('expected_digit')
                    if expected is None:
                        frame=self.host.export_interactive_image(capture['output_path'],overwrite=a.get('overwrite',False),
                            active_component=selected,wait_timeout=capture.get('wait_timeout'),cancel=self.cancel_event)
                    else:
                        output=Path(capture['output_path']);temporary=output.with_name('capture-'+uuid.uuid4().hex+output.suffix)
                        timeout=capture.get('wait_timeout');deadline=None if timeout is None else time.monotonic()+timeout
                        try:
                            while True:
                                if self.cancel_event.is_set():raise InterruptedError('Workflow cancelled')
                                frame=self.host.export_interactive_image(str(temporary),overwrite=True,active_component=selected,
                                    wait_timeout=None if deadline is None else max(0,deadline-time.monotonic()),cancel=self.cancel_event)
                                if any(d['decoded']==expected and (not selected or d['ref']==selected) for d in frame['display_states']):break
                                if self.cancel_event.is_set():raise InterruptedError('Workflow cancelled')
                                if deadline is not None and time.monotonic()>=deadline:raise NeedsInput('Captured display does not match expected digit',frame)
                                self.cancel_event.wait(.03)
                            temporary.replace(output);frame['path']=str(output)
                        finally:temporary.unlink(missing_ok=True)
                    frames.append(frame)
                    record.setdefault('partial_outputs',{})[stage['id']]=[f['path'] for f in frames]
                    self._save_record(record)
                return {'started':started,'configuration':configuration,'frames':frames,'passed':True}
            finally:
                if a.get('stop_after',True) or self.cancel_event.is_set():self.host.control_interactive('stop',15)
        if kind=='close':return self.host.finish(a.get('save_changes',True))
        raise ValueError('Unsupported stage: '+kind)

    def status(self,identifier,wait_timeout=0,detail=False,count=True):
        self._wait_value(wait_timeout)
        with self.guard:
            live=self.active==identifier
            if count and self.record and self.record['id']==identifier:
                self.record['stats']['external_calls']+=1
        if live:self.finished.wait(wait_timeout)
        elif wait_timeout and not (self.record and self.record['id']==identifier):
            deadline=time.monotonic()+wait_timeout
            while True:
                stored=self.store.read(identifier)
                if stored['status'] not in ('queued','running','cancel_requested') or not process_alive(stored.get('owner_pid')) or time.monotonic()>=deadline:break
                time.sleep(min(.1,max(0,deadline-time.monotonic())))
        with self.guard:
            record=copy.deepcopy(self.record) if self.record and self.record['id']==identifier else self.store.read(identifier)
        if detail:return record
        completed=set(c['id'] for c in record['completed'])
        result={k:record[k] for k in ('id','status','next_step','completed','stats','revision','error','failure','partial_outputs') if k in record}
        result['record_path']=str(self.store.path(identifier));outputs={}
        for stage in record['plan']['steps']:
            if stage['id'] not in completed:continue
            value=record['bindings'][stage['id']]
            if stage['kind']=='analysis':outputs[stage['id']]={k:value[k] for k in ('measurements','passed','criteria','raw_path','csv_path','netlist_path','document_settings') if k in value}
            elif stage['kind'] in ('save','export'):outputs[stage['id']]={k:value[k] for k in ('path','backup','saved_to_source','verification','page_check','width','height') if k in value}
            elif stage['kind']=='interactive':outputs[stage['id']]={'passed':value['passed'],
                **({'configuration':value['configuration']} if 'configuration' in value else {}),
                'frames':[{k:f[k] for k in ('path','display_states','capture_mode') if k in f} for f in value['frames']]}
            elif stage['kind'] in ('layout','verify','decode','prepare','simulation_settings','sheet_display'):outputs[stage['id']]=value
        result['results']=outputs
        if self.record and self.record['id']==identifier and not live:
            try:self.store.write(self.record)
            except OSError as error:result['persistence_error']=str(error)
        return result

    def control(self,identifier,action,replacement=None,wait_timeout=30,expected_revision=None):
        self._wait_value(wait_timeout)
        if action=='cancel':
            with self.guard:
                if self.active!=identifier:return self.status(identifier)
            self._request_cancel(identifier,'Workflow cancelled')
            return self.status(identifier,wait_timeout)
        if action!='resume':raise ValueError('Choose cancel or resume')
        with self.guard:
            if self.active:raise RuntimeError('A workflow is already running')
            record=self.record if self.record and self.record['id']==identifier else self.store.read(identifier)
            if record['status'] not in ('failed','needs_input','interrupted','cancelled'):raise ValueError('Only an unfinished workflow can resume')
            index=record['next_step']
            if replacement:
                steps=record['plan']['steps'][:index]+replacement
                record['plan']=WorkflowPlan.model_validate({**record['plan'],'steps':steps}).model_dump(exclude_none=True)
            else:record['plan']=WorkflowPlan.model_validate(record['plan']).model_dump(exclude_none=True)
            if not self.host.agent and index:
                checkpoint=record.get('resume_checkpoint')
                if not checkpoint:raise NeedsInput('No saved successful phase is available for resume')
                self.host.open_recovery(checkpoint,record.get('document') or checkpoint.get('document'));self.cache=record.get('state');record['reopened_for_resume']=True
                if record.get('wiring_options'):self.host.call('wiringOptions',record['wiring_options'])
            self.record=record
            self.cache=copy.deepcopy(record.get('state'))
            record['resume_revision']=expected_revision or record.get('revision')
            record['owner_pid']=os.getpid()
            record['stats']['external_calls']+=1;record['stats']['retries']+=1
            self._launch(record)
        return self.status(identifier,wait_timeout,count=False)

    @staticmethod
    def _wait_value(value):
        if not math.isfinite(value) or value<0:raise ValueError('wait_timeout must be a finite nonnegative number')

    def _request_cancel(self,identifier,reason):
        with self.guard:
            if self.active!=identifier:return
            self.record['cancel_reason']=reason;self.record['status']='cancel_requested';self.cancel_event.set()
        if self.host.analysis_started.is_set():
            try:self.host.agent.exports_sync.control('stop')
            except Exception:pass

    def shutdown(self):
        if self.active:
            self.cancel_event.set()
            if self.host.analysis_started.is_set():
                try:self.host.agent.exports_sync.control('stop')
                except Exception:pass
        if self.thread:self.thread.join()
