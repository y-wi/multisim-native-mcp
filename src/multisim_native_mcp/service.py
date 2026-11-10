"""Validated native editor transactions and analysis artifacts; no circuit file rewriting."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import csv
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

import frida
from PIL import Image
from .bridge import NativeHost, ROOT, INSTALL, sha256
from .paths import DATA_DIR

MUTATIONS = {'wire','move','moveLabel','place','copy','remove','transform','route','setParameter','setModelText',
             'rename','addText','labelWire','splitWire','connectEndpoint','reconnect',
             'replace','createSheet','createSubcircuit','createPort','sheetTitle','sheetSize','repairWireGeometry'}
TOPOLOGY_MUTATIONS={'wire','place','copy','remove','connectEndpoint','reconnect','replace','splitWire',
                    'createSheet','createSubcircuit','createPort','rename'}


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

    def folder(self):
        if not self.working: raise RuntimeError('Open a copy or attach to a project first')
        return self.working.parent

    def checkpoint(self):
        path=self.folder()/('checkpoint-'+uuid.uuid4().hex+'.ms14')
        sheets=self.call('sheets')
        result=self.call('snapshot',{'path':str(path)})
        if result['nativeResult']!=1 or result['errorCode']!=0 or not path.is_file():
            raise RuntimeError('Native checkpoint failed')
        return {'path':str(path),'original_path':result['original_path'],
                'modified':result['modified'],
                'sheet_index':next(s['index'] for s in sheets if s['selected'])}

    def restore(self, checkpoint):
        try:
            result=self.call('restoreSnapshot',checkpoint)
        except Exception:
            if not self.owned: raise
            source,digest,undo,redo=self.source,self.source_hash,self.undo_stack,self.redo_stack
            self.close()
            NativeHost.open_copy(self,checkpoint['path'])
            self.source,self.source_hash,self.undo_stack,self.redo_stack=source,digest,undo,redo
            result=self.call('restoreSnapshot',checkpoint)
            result['host_restarted']=True
        self.topology_dirty=False
        return result

    def edit(self, operation, args=None):
        return self.batch([{'operation':operation,'arguments':args or {}}])['results'][0]

    def batch(self, operations, include_state=False, atomic=True):
        if not 1<=len(operations)<=100: raise ValueError('Provide 1 to 100 edit operations')
        for op in operations:
            if op.get('operation') not in MUTATIONS or not isinstance(op.get('arguments',{}),dict):
                raise ValueError('Unsupported edit operation: '+str(op.get('operation')))
            self.validate(op['operation'],op.get('arguments',{}))
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before editing the circuit')
            # Resolve the first existing target before saving or reopening anything.
            first=operations[0]
            if first['operation'] in {'move','moveLabel','transform','copy','remove','setParameter','setModelText','rename','replace'} and first.get('arguments',{}).get('ref'):
                target=first['arguments']['ref'];components=self.call('components')['components']
                matches=[c for c in components if target in (c['ref'],c['id'])] or [c for c in components if target==c.get('local_ref')]
                if len(matches)!=1:
                    state=self.call('circuitState',{'include_parameters':True})
                    raise NativeEditError(f'Component {target!r} must identify one component on the selected sheet; found {len(matches)}. Available references: {[c["ref"] for c in components]}',
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
                        args['ref']=next(c['ref'] for c in self.call('components')['components'] if args['ref'] in (c['ref'],c['local_ref'],c['id']))
                        self.restore(self.checkpoint())
                    else:args=op.get('arguments',{})
                    results.append(self.call(op['operation'],args))
                    self.topology_dirty=self.topology_dirty or op['operation'] in TOPOLOGY_MUTATIONS
                self.call('markModified')
                if any(op['operation']=='createSubcircuit' for op in operations):
                    self.restore(self.checkpoint())
                    for op,result in zip(operations,results):
                        if op['operation']=='createSubcircuit':
                            result['components']=self.call('components')['components'];result['sheets']=self.call('sheets')
                            result['symbol_id']=next(c['id'] for c in result['components'] if c['ref']==op['arguments'].get('ref',op['arguments']['title']))
                            result['sheet_id']=next(s['id'] for s in result['sheets'] if s['title']==op['arguments']['title'])
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
            return {'results':results,'undo_depth':len(self.undo_stack),'rollback_checkpoint':before['path'],
                    **({'state':self.call('circuitState',{'include_parameters':True})} if include_state else {})}

    @staticmethod
    def validate(op,args):
        if op=='place':
            if args.get('anchor','origin') not in ('origin','center','pin'):raise ValueError('Placement anchor must be origin, center or pin')
            if args.get('anchor')=='pin' and not isinstance(args.get('pin'),str):raise ValueError('Placement with anchor=pin requires the exact pin name')
        if op=='place' and 'parameters' in args:
            if not isinstance(args['parameters'],list) or len(args['parameters'])>256:raise ValueError('Provide at most 256 component parameters')
            for parameter in args['parameters']:
                if not isinstance(parameter,dict) or (('value' in parameter)==('expression' in parameter)):raise ValueError('Each parameter needs index and exactly one value or expression')
                EditorService.validate('setParameter',parameter)
        if op=='sheetSize' and any(not isinstance(args.get(k),int) or not 96<=args[k]<=8192 for k in ('width','height')):
            raise ValueError('Sheet width and height must be 96 to 8192 native pixels')
        for key in ('x','y','dx','dy'):
            if key in args and (not isinstance(args[key],int) or abs(args[key])>100000):
                raise ValueError(key+' must be an integer within 100000 sheet units')
        if op=='setParameter':
            if not isinstance(args.get('index'),int) or not 0<=args['index']<256: raise ValueError('Invalid parameter index')
            if 'value' in args and not math.isfinite(float(args['value'])): raise ValueError('Parameter must be finite')
        if op=='transform' and 'angle' in args and args['angle']%90: raise ValueError('Rotation must be a multiple of 90 degrees')
        if op=='transform' and 'angle' not in args and args.get('axis') not in ('horizontal','vertical'): raise ValueError('Invalid mirror axis')
        if op in ('rename','place','copy','replace'):
            for key in ('ref','new_ref'):
                if key in args and not re.fullmatch(r'[A-Za-z0-9_.$:-]{1,128}',args[key]): raise ValueError('Invalid reference')
        if 'points' in args:
            if not isinstance(args['points'],list) or not 2<=len(args['points'])<=1000: raise ValueError('Provide 2 to 1000 route vertices')
            for point in args['points']:
                for key in ('x','y'):
                    if not isinstance(point.get(key),int) or abs(point[key])>100000: raise ValueError('Invalid route coordinate')
        for key in ('name','text','title','family','group','manufacturer','expression'):
            if key in args and (not isinstance(args[key],str) or len(args[key])>4096 or '\x00' in args[key]): raise ValueError('Invalid '+key)

    def history(self, action):
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before undo or redo')
            source,target=(self.undo_stack,self.redo_stack) if action=='undo' else (self.redo_stack,self.undo_stack)
            if not source: raise ValueError('No '+action+' checkpoint')
            current=self.checkpoint(); checkpoint=source[-1]
            result=self.restore(checkpoint);source.pop();target.append(current)
            return {**result,'undo_depth':len(self.undo_stack),'redo_depth':len(self.redo_stack),'handles_invalidated':True}

    def netlist(self):
        with self.lock:
            if self.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before regenerating its netlist or running numeric analysis')
            refreshed=False
            if self.topology_dirty:
                self.restore(self.checkpoint());refreshed=True
            result=self.call('netlist')
            return {**result,'handles_invalidated':refreshed,
                    **({'state':self.call('circuitState',{'include_parameters':True})} if refreshed else {})}

    @staticmethod
    def output_path(value,suffixes,overwrite=False):
        path=Path(value)
        if not path.is_absolute() or path.suffix.lower() not in suffixes or not path.parent.is_dir():
            raise ValueError('Choose an absolute output path in an existing directory: '+str(suffixes))
        if path.exists() and not overwrite: raise FileExistsError('Output already exists')
        return path.resolve()

    def export_image(self, output_path, overwrite=False, dpi=96, scale=1., region=None, fit_content=False,padding=18,show_frame=False,show_grid=False,*,interactive=False,active_component=None,wait_timeout=5.0):
        if not isinstance(dpi,int) or not 36<=dpi<=600 or not math.isfinite(scale) or not .1<=scale<=8:
            raise ValueError('Require 36 to 600 DPI and scale 0.1 to 8')
        factor=dpi/96*scale
        if not .1<=factor<=10:raise ValueError('Combined DPI/scale must be 0.1 to 10 times native size')
        if not isinstance(padding,int) or not 0<=padding<=1000:raise ValueError('Padding must be 0 to 1000 sheet units')
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
                if set(region)!={'left','top','right','bottom'} or any(not isinstance(v,int) or abs(v)>100000 for v in region.values()):raise ValueError('Region must contain integer left/top/right/bottom sheet coordinates')
                width=region['right']-region['left'];height=region['bottom']-region['top']
                if width<=0 or height<=0:raise ValueError('Export region must have positive size')
            else:
                width,height=page['width'],page['height']
                if state['components'] and all(c['bounds']['right']<0 or c['bounds']['bottom']<0 or c['bounds']['left']>width or c['bounds']['top']>height for c in state['components']):
                    raise ValueError('Circuit is outside the page; use fit_content=true, an explicit region, or resize the sheet')
            if math.ceil(width*factor)*math.ceil(height*factor)>32000000:raise ValueError('Export exceeds 32 million pixels')
            requested_region=region or page['bounds']
            # The native bitmap exporter always draws sheet coordinates along its
            # viewport boundary. Render a gutter outside the requested region so
            # removing that synthetic frame never removes real circuit content.
            gutter=0 if show_frame else 36
            render_region={k:v+(-gutter if k in ('left','top') else gutter) for k,v in requested_region.items()} if gutter else region
            if math.ceil((width+2*gutter)*factor)*math.ceil((height+2*gutter)*factor)>32000000:
                raise ValueError('Native export including frame gutter exceeds 32 million pixels; reduce DPI, scale or region size')
            intermediate=self.folder()/('native-image-'+uuid.uuid4().hex+'.bmp')
            render_args={'path':str(intermediate),'render_scale':factor,'show_frame':show_frame,'show_grid':show_grid,**({'region':render_region} if render_region else {})}
            captured=None
            if interactive:
                deadline=time.monotonic()+wait_timeout
                while True:
                    captured=self.call('exportInteractiveImage',{**render_args,'active_component':active_component})
                    if captured['ready']:break
                    if captured['state']==2 or time.monotonic()>=deadline:
                        raise RuntimeError('No stable lit frame for '+str(active_component)+': '+('simulation is paused; resume before waiting for another scan phase' if captured['state']==2 else 'capture timed out'))
                    time.sleep(.03)
            else:self.call('exportImage',render_args)
            with Image.open(intermediate) as image:
                if gutter:
                    offset=round(gutter*factor)
                    image=image.crop((offset,offset,offset+round(width*factor),offset+round(height*factor)))
                image.save(path,format='PNG' if path.suffix.lower()=='.png' else 'BMP',dpi=(dpi,dpi))
                size=image.size
            return {'path':str(path),'width':size[0],'height':size[1],'bytes':path.stat().st_size,
                    'dpi':dpi,'scale':scale,'region':region or page['bounds'],'off_page_components':off_page,'show_frame':show_frame,'show_grid':show_grid,
                    'source':'native schematic image renderer',**({k:captured[k] for k in ('capture_mode','display_states','simulation')} if captured else {})}

    def export_interactive_image(self,output_path,overwrite=False,dpi=144,scale=1.,region=None,fit_content=False,padding=18,show_frame=False,show_grid=False,active_component=None,wait_timeout=5.0):
        if not math.isfinite(wait_timeout) or not 0<=wait_timeout<=15:raise ValueError('wait_timeout must be 0 to 15 seconds')
        if active_component is not None and (not isinstance(active_component,str) or not active_component):raise ValueError('active_component must be a component reference')
        self.interactive_status()
        return self.export_image(output_path,overwrite,dpi,scale,region,fit_content,padding,show_frame,show_grid,
                                 interactive=True,active_component=active_component,wait_timeout=wait_timeout)

    def run_analysis(self, analysis='op', step=1e-5, stop=0.01, use_initial_conditions=False,
                     ac_sweep='dec',ac_points=20,ac_start=1.,ac_stop=100000.):
        if analysis not in ('op','tran','ac'): raise ValueError('analysis must be op, tran or ac')
        if not (math.isfinite(step) and math.isfinite(stop) and 0<step<=stop<=100 and stop/step<=100000*(1+1e-12)):
            raise ValueError('Require 0 < step <= stop <= 100 seconds and at most 100000 requested steps')
        if not isinstance(use_initial_conditions,bool):raise ValueError('use_initial_conditions must be boolean')
        if use_initial_conditions and analysis!='tran':raise ValueError('Initial conditions apply to transient analysis')
        if ac_sweep not in ('lin','dec','oct') or not isinstance(ac_points,int) or not 1<=ac_points<=100000:
            raise ValueError('Choose lin, dec or oct and 1 to 100000 points')
        if not (math.isfinite(ac_start) and math.isfinite(ac_stop) and 0<ac_start<ac_stop<=1e12):
            raise ValueError('Require 0 < AC start < stop <= 1e12 Hz')
        estimated=ac_points if ac_sweep=='lin' else ac_points*math.log(ac_stop/ac_start,10 if ac_sweep=='dec' else 2)+1
        if estimated>100000:raise ValueError('AC sweep exceeds 100000 requested points')
        with self.lock:
            stem=self.folder()/('analysis-'+uuid.uuid4().hex)
            diagnostic=stem.with_suffix('.json');record={'analysis':analysis,'status':'running','use_initial_conditions':use_initial_conditions}
            diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
            self.analysis_started.clear()
            try:
                netlist=self.netlist()
                record['netlist']={k:v for k,v in netlist.items() if k!='content'}
                if netlist['failed']:raise RuntimeError('Native netlist check failed: '+netlist['messages'])
                self.numeric_session_used=True
                result=self.call('simulate',{'analysis':analysis,'step':step,'stop':stop,'use_initial_conditions':use_initial_conditions,
                    'ac_sweep':ac_sweep,'ac_points':ac_points,'ac_start':ac_start,'ac_stop':ac_stop,'source_path':str(stem.with_suffix('.cir'))})
                record['native']=result
                self.analysis_started.clear()
                if result.get('failed'):raise RuntimeError('Native analysis failed at '+result.get('stage','analysis'))
                raw=stem.with_suffix('.raw');exported=self.call('simulationExport',{'path':str(raw)});record['export']=exported
                if not raw.is_file():raise RuntimeError('Native simulator produced no waveform')
                data=parse_raw(raw)
                expected={'tran':'Transient Analysis','op':'DC Operating Point','ac':'AC Analysis'}[analysis]
                if data['plot']!=expected: raise RuntimeError('Simulator returned an unexpected plot: '+str(data['plot']))
                csv_path=stem.with_suffix('.csv')
                export_csv(data,csv_path);summary=summarize(data)
            except Exception as error:
                self.analysis_started.clear()
                record.update(status='failed',error=str(error));diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
                raise RuntimeError(str(error)+'; diagnostics: '+str(diagnostic)) from error
            record.update(status='complete',points=data['points'],raw_path=str(raw),csv_path=str(csv_path))
            diagnostic.write_text(json.dumps(record,indent=2),encoding='utf-8')
            return {'analysis':analysis,'plot':data['plot'],'points':data['points'],'vectors':summary,'unit_system':'SI',
                    'preview':data['rows'][:10],'raw_path':str(raw),'csv_path':str(csv_path),
                    'netlist_path':str(stem.with_suffix('.cir')),'native_result':result,'diagnostic_path':str(diagnostic),
                    'handles_invalidated':netlist['handles_invalidated']}

    def start_analysis(self,analysis='tran',step=1e-5,stop=0.01,use_initial_conditions=False):
        if not self.agent: raise RuntimeError('Open a native project first')
        if self.analysis_job and self.analysis_job['status'] in ('running','pause_requested','stop_requested'):
            raise RuntimeError('An analysis is already running')
        self.analysis_started.clear()
        job={'id':uuid.uuid4().hex,'status':'running','started':time.time()};self.analysis_job=job
        def run():
            try:
                job['result']=self.run_analysis(analysis,step,stop,use_initial_conditions)
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

    def configure_interactive(self,time_step=None,max_time_step=None,real_time=None,reset=False):
        configuration={}
        for name,value in [('time_step',time_step),('max_time_step',max_time_step)]:
            if value is None:continue
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 1e-12<=value<=1:
                raise ValueError(name+' must be a finite number from 1e-12 to 1 second')
            configuration[name]=value
        if real_time is not None:
            if not isinstance(real_time,bool):raise ValueError('real_time must be boolean')
            configuration['real_time']=real_time
        if not isinstance(reset,bool):raise ValueError('reset must be boolean')
        if reset and configuration:raise ValueError('reset cannot be combined with simulation options')
        with self.lock:
            if configuration or reset:
                state=self.interactive_status()
                if state['state_name'] in ('running','paused'):raise RuntimeError('Stop interactive simulation before changing its options')
            return self.call('interactiveOptions',{'configuration':configuration,'reset':reset})

    def control_interactive(self,action,wait_timeout=5.0):
        if action not in ('start','pause','resume','stop'):raise ValueError('Choose start, pause, resume or stop')
        if not math.isfinite(wait_timeout) or not 0<=wait_timeout<=15:raise ValueError('wait_timeout must be 0 to 15 seconds')
        with self.lock:
            before=self.interactive_status();state=before['state_name']
            target={'start':'running','resume':'running','pause':'paused','stop':'stopped'}[action]
            if (state==target or (action=='stop' and state=='unprepared')) and not self.numeric_session_used and not (action=='stop' and before['remote_initialized']):
                return {**before,'action':action,'requested':False,'transition_confirmed':True,'already_in_state':True}
            if (action=='start' and state=='paused') or (action=='resume' and state!='paused') or (action=='pause' and state!='running'):
                raise ValueError(f'Cannot {action} interactive simulation while {state}')
            cleaned=False
            if self.numeric_session_used or (action=='start' and before['remote_initialized'] and state=='stopped'):
                self.call('interactiveCommand',{'action':'stop'})
                cleanup_deadline=time.monotonic()+15
                while True:
                    current=self.interactive_status()
                    if not current['remote_initialized']:break
                    if time.monotonic()>=cleanup_deadline:raise RuntimeError('Numeric simulator cleanup did not complete before interactive control')
                    time.sleep(.1)
                self.numeric_session_used=False;cleaned=True
                if action=='stop':
                    return {**current,'action':action,'requested':True,'previous_state':state,'transition_confirmed':True,'numeric_context_cleaned':True}
            command=self.call('interactiveCommand',{'action':action});deadline=time.monotonic()+wait_timeout
            while True:
                current=self.interactive_status()
                confirmed=(current['state_name']==target or (action=='stop' and current['state_name']=='unprepared')) and (action!='stop' or not current['remote_initialized'])
                if confirmed or time.monotonic()>=deadline:
                    return {**current,**command,'previous_state':state,'transition_confirmed':confirmed,'numeric_context_cleaned':cleaned,'handles_invalidated':False}
                time.sleep(.1)

    def read_waveform(self,path,offset=0,limit=1000,plot_index=0):
        source=Path(path)
        if not source.is_absolute() or not source.is_file() or source.suffix.lower()!='.raw': raise ValueError('Choose an existing absolute ASCII RAW path')
        if not 0<=offset or not 1<=limit<=1000: raise ValueError('Invalid waveform offset or limit')
        first=parse_raw(source);plots=[first,*first.pop('additional_plots')]
        if not isinstance(plot_index,int) or not 0<=plot_index<len(plots):raise ValueError('Invalid waveform plot index')
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
            self.working=folder/'attached-session.ms14';self.source=None;self.source_hash=None
            try:
                self.session=frida.attach(pid)
                inspector=self.session.create_script('rpc.exports.modules=()=>Process.enumerateModules().map(m=>({name:m.name,path:m.path}));',runtime='v8')
                inspector.load();modules={m['name'].lower():m['path'] for m in inspector.exports_sync.modules()};inspector.unload()
                for name in ('multisim.exe','DrwEngine.dll','SCH_CAP.dll','Od101dll.dll'):
                    if name.lower() not in modules:
                        raise RuntimeError('Attached process is not ready: '+name)
                code=(ROOT/'host_agent.js').read_text(encoding='utf-8')+'\n'+(ROOT/'editor_agent.js').read_text(encoding='utf-8')
                self.agent=self.session.create_script(code,runtime='v8');self.agent.on('message',self._message);self.agent.load()
                self.call('selectProject',{'index':project_index})
                info=self.call('inspect');source=Path(info['projectPath'])
                self.source=source.resolve() if source.is_absolute() and source.is_file() else None
                self.source_hash=sha256(self.source) if self.source else None
                self.undo_stack,self.redo_stack=[],[];self.topology_dirty=False
                backup=self.checkpoint()
                return {**info,'owned':False,'backup':backup['path'],'source_path':str(self.source) if self.source else None}
            except Exception:
                self.close();raise

    def create(self,title='Circuit'):
        if self.process and self.process.poll() is None: raise RuntimeError('Close or detach the current project first')
        if not title or len(title)>128: raise ValueError('Provide a title of 1 to 128 characters')
        result=self.open_copy(str(ROOT/'assets'/'blank14.3.ms14'))
        if self.call('components')['components'] or self.call('wires')['wires']:
            self.close();raise RuntimeError('Native blank template contains unexpected objects')
        self.edit('sheetTitle',{'title':title})
        return {**result,'title':title,'blank':True}

    def close(self):
        job=getattr(self,'analysis_job',None)
        if self.agent and job and job['status'] in ('running','pause_requested','stop_requested'):
            try:self.control_analysis('stop')
            except Exception:pass
        return super().close()
