"""Persistent, explicitly retried native experiments."""
import copy
import json
import re
import threading
import time
import uuid
from pathlib import Path
from .paths import DATA_DIR
from .bridge import sha256
from .experiments import run_sweep,validate_spec


class ExperimentStore:
    def __init__(self,root=None):
        self.root=Path(root or DATA_DIR/'experiments');self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
    def path(self,identifier):
        if not re.fullmatch(r'[0-9a-f]{32}',identifier):raise ValueError('Invalid experiment ID')
        return self.root/(identifier+'.json')
    def write(self,record):
        with self.lock:
            path=self.path(record['id']);temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8');temporary.replace(path)
    def read(self,identifier):
        with self.lock:return json.loads(self.path(identifier).read_text(encoding='utf-8'))
    def list(self,limit=20):
        if not 1<=limit<=100:raise ValueError('Limit must be 1 to 100')
        with self.lock:
            paths=sorted(self.root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:limit]
            return [{k:v for k,v in json.loads(p.read_text(encoding='utf-8')).items() if k in ('id','status','created','finished','retry_of','error')} for p in paths]


class ExperimentManager:
    def __init__(self,host,root=None):
        self.host=host;self.store=ExperimentStore(root);self.guard=threading.RLock()
        self.active=None;self.thread=None;self.cancel_event=threading.Event()
        for p in self.store.root.glob('*.json'):
            record=self.store.read(p.stem)
            if record['status'] in ('queued','running','cancel_requested'):
                record.update(status='interrupted',finished=time.time());self.store.write(record)

    def start(self,parameters,analysis,measurements,criteria=None,objective=None,background=True,retry_of=None):
        spec=copy.deepcopy({'parameters':parameters,'analysis':analysis,'measurements':measurements,'criteria':criteria or [],'objective':objective})
        validate_spec(**spec)
        with self.guard:
            if self.active:raise RuntimeError('An experiment is already running')
            identifier=uuid.uuid4().hex
            with self.host.lock:
                if not self.host.agent:raise RuntimeError('Open a native project first')
                source=self.host.checkpoint()['path']
                image=self.store.root/(identifier+'.png')
                self.host.export_image(str(image.resolve()))
            record={'id':identifier,'status':'queued','created':time.time(),'spec':spec,'schematic_path':str(image.resolve()),
                    'source':source,'source_sha256':sha256(Path(source)),'retry_of':retry_of}
            if hasattr(self.host,'document_context'):record['document']=self.host.document_context()
            self.store.write(record);self.active=record['id'];self.cancel_event.clear()
            def execute():
                with self.guard:
                    record['status']='cancel_requested' if self.cancel_event.is_set() else 'running';self.store.write(record)
                def progress(result):
                    with self.guard:
                        record['result']=result
                        record['status']='cancel_requested' if self.cancel_event.is_set() else 'running'
                        self.store.write(record)
                try:
                    result=run_sweep(self.host,**spec,cancel=self.cancel_event,progress=progress)
                    record.update(result=result,status=result['status'])
                except Exception as error:record.update(status='failed',error=str(error))
                finally:
                    with self.guard:
                        record['finished']=time.time();self.store.write(record);self.active=None
            if background:
                self.thread=threading.Thread(target=execute,daemon=True);self.thread.start()
                return {'id':record['id'],'status':'queued','record_path':str(self.store.path(record['id']))}
        execute()
        return self.store.read(record['id'])

    def cancel(self,identifier):
        with self.guard:
            if identifier!=self.active:return {'id':identifier,'requested':False,'status':self.store.read(identifier)['status']}
            self.cancel_event.set();record=self.store.read(identifier);record['status']='cancel_requested';self.store.write(record)
            control=None
            if self.host.analysis_started.is_set():
                try:control=self.host.agent.exports_sync.control('stop')
                except Exception as error:control={'error':str(error)}
            return {'id':identifier,'requested':True,'status':'cancel_requested','native_control':control}

    def retry(self,identifier):
        with self.guard:
            if self.active:raise RuntimeError('An experiment is already running')
            record=self.store.read(identifier)
            if self.host.agent:raise RuntimeError('Close the current native session before retrying its saved experiment copy')
            path=Path(record['source'])
            if sha256(path)!=record['source_sha256']:raise RuntimeError('Saved experiment circuit has changed')
            self.host.open_recovery({'path':str(path)},record.get('document'))
            return self.start(**record['spec'],retry_of=identifier)

    def shutdown(self):
        if self.active:self.cancel(self.active)
        if self.thread:self.thread.join(timeout=60)
