import copy
import json
import os
import shutil
import subprocess
import threading

import pytest
from pydantic import ValidationError

from multisim_native_mcp.paths import RESOURCE_DIR
from multisim_native_mcp.workflow_contracts import WorkflowPlan
from multisim_native_mcp.workflow_values import resolve
from multisim_native_mcp.workflows import NeedsInput, WorkflowManager, remap_bindings


def circuit(pointer='c1'):
    return {'page':{'width':960,'height':720},'wires':[], 'components':[
        {'id':pointer,'ref':'VCC','local_ref':'VCC','transform':[1,0,0,1,180,180],
         'pins':[{'id':pointer+'p','name':'1','x':180,'y':180,'connections':0}], 'labels':[],
         'parameters':[{'index':0,'value':5}]}]}


class Host:
    def __init__(self,tmp_path):
        self.lock=threading.RLock();self.agent=True;self.state=circuit()
        self.source=None;self.working=tmp_path/'working.ms14';self.working.write_bytes(b'checkpoint')
        self.analysis_started=threading.Event();self.native_call_count=0;self.native_call_seconds=0
    def call(self,operation,args=None):
        self.native_call_count+=1
        if operation=='circuitState':return copy.deepcopy(self.state)
        if operation=='wiringOptions':return args or {}
        raise AssertionError(operation)
    def checkpoint(self):return {'path':str(self.working)}
    def open_copy(self,path):self.agent=True;self.state=circuit('c2')


@pytest.mark.parametrize('plan',[
    {'steps':[{'id':'a','kind':'edit','operations':[{'operation':'move','arguments':{'ref':{'$ref':'future.component.id'},'dx':9,'dy':0}}]}]},
    {'steps':[{'id':'a','kind':'session','mode':'open'}]},
    {'steps':[{'id':'a','kind':'close'},{'id':'b','kind':'netlist'}]},
    {'steps':[{'id':'a','kind':'analysis','measurements':[],'criteria':[{'id':'missing','target':1}]}]},
    {'steps':[{'id':'a','kind':'analysis','options':{'analysis':'ac','ac_start':100,'ac_stop':10}}]},
])
def test_plan_preflight_rejects_invalid_dependency_or_stage(plan):
    with pytest.raises(ValidationError):WorkflowPlan.model_validate(plan)


def test_result_references_and_bounded_arithmetic():
    b={'r':{'component':{'id':'c1','pins':[{'x':180}]}}}
    assert resolve({'ref':{'$ref':'r.component.id'},'x':{'$add':[{'$ref':'r.component.pins.0.x'},9]}},b)=={'ref':'c1','x':189}
    assert resolve({'$sub':[20,9]},b)==11
    for value in ({'$ref':'r.constructor'},{'$ref':'missing'}, {'$add':[1,True]}):
        with pytest.raises(ValueError):resolve(value,b)


def test_shared_reference_rebinding_uses_unique_geometry():
    before=circuit();second=copy.deepcopy(before['components'][0]);second.update(id='other',transform=[1,0,0,1,540,180]);second['pins']=[{'id':'otherp','name':'1','x':540,'y':180}]
    before['components'].append(second);after=copy.deepcopy(before)
    for i,c in enumerate(after['components']):c['id']='new'+str(i);c['pins'][0]['id']='newpin'+str(i)
    b=remap_bindings({'power':{'component':before['components'][0]}},before,after)
    assert b['power']['component']['id']=='new0'
    after['components'].append(copy.deepcopy(after['components'][0]))
    assert '$invalid_handle' in remap_bindings({'id':'c1'},before,after)['id']
    moved=copy.deepcopy(before);moved['components'][0]['transform'][4]+=9
    assert remap_bindings({'id':'c1'},before,moved)['id']=='c1'


def test_reopen_does_not_trust_reused_addresses_for_identical_power_symbols():
    before=circuit('old1');peer=copy.deepcopy(before['components'][0])
    peer.update(id='old2',transform=[1,0,0,1,540,180]);peer['pins'][0].update(id='old2pin',x=540)
    before['components'].append(peer);before['handle_epoch']=[1,1]
    after=copy.deepcopy(before);after['handle_epoch']=[1,2]
    after['components'][0]['id']='old2';after['components'][1]['id']='old1'
    after['components'][0]['pins'][0]['id']='old2pin';after['components'][1]['pins'][0]['id']='old1pin'
    rebound=remap_bindings({'power':'old1'},before,after)
    assert rebound['power']=='old2'


def test_session_delta_preserves_cache_and_detects_handle_changes(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records')
    first=manager.session_state();revision=first['revision']
    assert manager.session_state(revision)=={'revision':revision,'changed':False}
    h.state['components'][0]['parameters'][0]['value']=12
    changed=manager.session_state(revision)
    assert changed['changed'] and not changed['full']
    assert 'parameters' not in changed['components'][0]
    assert manager.cache['components'][0]['parameters'][0]['value']==12
    previous=changed['revision'];h.state['components'][0]['id']='new'
    assert manager.session_state(previous)['changed']


def test_failed_phase_resume_preserves_completed_stages(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records');calls=[]
    def stage(s,record):
        calls.append(s['id'])
        if s['id']=='check' and calls.count('check')==1:raise NeedsInput('Choose criteria',{'available':['output']})
        return {'passed':True}
    manager._stage=stage
    plan={'steps':[{'id':'configure','kind':'wiring','connect_touching':False},{'id':'check','kind':'layout'}]}
    failed=manager.start(plan)
    assert failed['status']=='needs_input' and failed['next_step']==1
    assert failed['failure']['details']=={'available':['output']}
    resumed=manager.control(failed['id'],'resume')
    assert resumed['status']=='complete' and calls==['configure','check','check']
    assert resumed['stats']['retries']==1 and resumed['stats']['external_calls']==2


def test_long_wait_cancel_and_revision_conflict(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records');entered=threading.Event()
    def stage(s,record):entered.set();assert manager.cancel_event.wait(5);return {'stopped':True}
    manager._stage=stage
    plan={'steps':[{'id':'stage','kind':'wiring','connect_touching':False}]}
    with pytest.raises(ValueError):manager.start(plan,wait_timeout=100)
    assert manager.active is None
    running=manager.start(plan,wait_timeout=0);assert entered.wait(5)
    cancelled=manager.control(running['id'],'cancel',wait_timeout=5)
    assert cancelled['status']=='cancelled'
    conflict=manager.start({**plan,'expected_revision':'stale'})
    assert conflict['status']=='needs_input' and 'revision' in conflict['error']
    assert h.state==circuit()


def test_restart_marks_interrupted_and_resume_rebinds_saved_alias(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records')
    record={'id':'a'*32,'status':'running','plan':{'steps':[{'id':'done','kind':'wiring'},{'id':'check','kind':'layout'}]},
            'next_step':1,'completed':[{'id':'done','kind':'wiring'}], 'bindings':{'done':{},'power':{'component':circuit()['components'][0]}},
            'stats':{'external_calls':1,'retries':0},'events':[],'resume_checkpoint':h.checkpoint()}
    state=manager._capture();record.update(state=state,revision=state['revision']);manager.store.write(record)
    h.agent=False;manager=WorkflowManager(h,tmp_path/'records')
    assert manager.store.read(record['id'])['status']=='interrupted'
    manager._stage=lambda stage,record:{'passed':True}
    result=manager.control(record['id'],'resume')
    assert result['status']=='complete',result
    assert manager.status(record['id'],detail=True)['bindings']['power']['component']['id']=='c2'


def test_output_preflight_happens_before_any_stage(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records');called=[]
    manager._stage=lambda s,r:called.append(s['id'])
    existing=tmp_path/'exists.ms14';existing.write_bytes(b'keep')
    result=manager.start({'steps':[{'id':'edit','kind':'wiring'},{'id':'save','kind':'save','output_path':str(existing)}]})
    assert result['status']=='needs_input' and not called and existing.read_bytes()==b'keep'


def test_packed_native_slice_resolves_bindings_and_stops_before_bad_native_calls():
    source=(RESOURCE_DIR/'editor_agent.js').read_text(encoding='utf-8')
    section=source[source.index('function sequenceValue('):source.index('const editorHandlers=')]
    harness=r'''
const assert=require('node:assert/strict');let calls=[];
const editorHandlers={place:a=>{calls.push(a);return {component:{id:'c'+calls.length,pins:[{x:a.x}]}};}};
function wire(a){calls.push(a);return {id:'wire'};}
function move(a){calls.push(a);return a;}
const source=JSON.parse(require('node:fs').readFileSync(0,'utf8')).source;
eval(source+`
 const first=editSequence({operations:[{operation:'place',bind:'part',arguments:{name:'R',x:180,y:90}},
  {operation:'move',arguments:{ref:{$ref:'part.component.id'},dx:{$sub:[{$ref:'part.component.pins.0.x'},9]},dy:0}}]});
 assert.equal(first.failed,false);assert.deepEqual(calls[1],{ref:'c1',dx:171,dy:0});
 const failed=editSequence({operations:[{operation:'move',arguments:{ref:'c1',dx:'bad',dy:0}}]});
 assert.equal(failed.failed,true);assert.equal(calls.length,2);
 assert.throws(()=>sequenceValue({$ref:'part.constructor'},{part:{}}),/Unresolved/);
`);
console.log('ok');
'''
    result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps({'source':section}),text=True,capture_output=True,check=True,timeout=15)
    assert result.stdout.strip()=='ok'


def test_primary_value_preflight_uses_value_slot_and_collects_pin_errors(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records')
    from multisim_native_mcp.workflows import digest
    request={'name':'RESISTOR_VIRTUAL','family':'','group':'','manufacturer':''}
    manager.catalog[digest(request)]={'pins':[{'name':'1'},{'name':'2'}],
        'parameters':[{'index':0,'role':'model_option'},{'index':1,'role':'value'}]}
    manager.prepare=lambda requests:None
    ops=[{'operation':'place','bind':'r','arguments':{'name':'RESISTOR_VIRTUAL','value':'1k'}},
         {'operation':'setParameter','arguments':{'ref':{'$ref':'r.component.id'},'role':'value','value':2200}}]
    manager._preflight_edits(ops,{})
    assert ops[0]['arguments']['parameters']==[{'index':1,'expression':'1k'}]
    assert ops[1]['arguments']['index']==1
    invalid=[{'operation':'place','bind':'r','arguments':{'name':'RESISTOR_VIRTUAL','anchor':'pin','pin':'bad'}},
             {'operation':'wire','arguments':{'source':{'ref':{'$ref':'r.component.id'},'pin':'also_bad'}}}]
    with pytest.raises(NeedsInput) as error:manager._preflight_edits(invalid,{})
    assert len(error.value.result['issues'])==2


def test_existing_component_selection_is_unique_and_address_independent(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records');manager.cache=copy.deepcopy(h.state)
    other=copy.deepcopy(h.state['components'][0]);other.update(id='second',transform=[1,0,0,1,540,180]);other['pins'][0].update(id='secondpin',x=540)
    manager.cache['components'].append(other)
    record={'bindings':{}}
    selected=manager._stage({'id':'select','kind':'select','components':{'supply':{'ref':'VCC','pin':'1','x':540,'y':180}}},record)
    assert selected['components']['supply']['id']=='second'
    with pytest.raises(NeedsInput):manager._stage({'id':'select','kind':'select','components':{'supply':{'ref':'VCC'}}},record)


def test_runtime_budget_cancels_at_a_supported_boundary(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records')
    def stage(s,r):assert manager.cancel_event.wait(5);return {'stopped':True}
    manager._stage=stage
    result=manager.start({'max_runtime':.05,'steps':[{'id':'stage','kind':'wiring'}]},wait_timeout=5)
    assert result['status']=='cancelled' and result['error']=='Workflow runtime limit reached'


def test_native_edit_slices_keep_bindings_local_and_one_undo_checkpoint(tmp_path):
    from multisim_native_mcp.service import EditorService
    h=EditorService();seen=[];checkpoint={'path':str(tmp_path/'checkpoint.ms14')}
    h.checkpoint=lambda:checkpoint
    def call(op,args=None):
        if op=='simulationInfo':return {'state':0}
        if op=='markModified':return {}
        assert op=='editSequence';seen.append(copy.deepcopy(args));bindings=dict(args['bindings']);results=[]
        for edit in args['operations']:
            a=resolve(edit['arguments'],bindings);value={'id':a.get('ref','native-text')}
            results.append(value)
            if edit.get('bind'):bindings[edit['bind']]=value
        return {'failed':False,'results':results,'bindings':bindings}
    h.call=call
    ops=[{'operation':'addText','bind':'first','arguments':{'text':'test','x':0,'y':0}}]
    ops += [{'operation':'addText','arguments':{'text':'test','x':n,'y':0}} for n in range(7)]
    ops += [{'operation':'move','arguments':{'ref':{'$ref':'first.id'},'dx':9,'dy':0}}]
    result=h.edit_sequence(ops,{'large_analysis':{'unneeded':[0]*1000}})
    assert len(seen)==2 and seen[0]['bindings']=={} and set(seen[1]['bindings'])=={'first'}
    assert 'large_analysis' in result['bindings'] and len(h.undo_stack)==1


def test_resume_rebinds_from_job_state_after_an_external_state_read(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records')
    def stage(s,r):
        if not r.get('retried'):
            r['bindings']['power']={'component':copy.deepcopy(h.state['components'][0])}
            r['retried']=True;raise NeedsInput('Select a criterion')
        return {'passed':True}
    manager._stage=stage
    failed=manager.start({'steps':[{'id':'check','kind':'layout'}]})
    h.state=circuit('new')
    current=manager.session_state()
    result=manager.control(failed['id'],'resume',expected_revision=current['revision'])
    assert result['status']=='complete',result
    assert manager.status(result['id'],detail=True)['bindings']['power']['component']['id']=='new'


def test_a_second_client_does_not_interrupt_a_live_owner(tmp_path):
    manager=WorkflowManager(Host(tmp_path),tmp_path/'records')
    record={'id':'b'*32,'status':'running','owner_pid':os.getpid()}
    manager.store.write(record)
    observer=WorkflowManager(None,tmp_path/'records')
    assert observer.store.read(record['id'])['status']=='running'


def test_record_write_failure_releases_waiters_and_execution_slot(tmp_path):
    h=Host(tmp_path);manager=WorkflowManager(h,tmp_path/'records');write=manager.store.write;calls=[]
    def failing(record):
        calls.append(record['id'])
        if len(calls)>1:raise OSError('storage unavailable')
        return write(record)
    manager.store.write=failing
    result=manager.start({'steps':[{'id':'stage','kind':'wiring'}]})
    assert result['status']=='failed' and manager.active is None and manager.finished.is_set()
    assert 'storage unavailable' in manager.status(result['id'])['persistence_error']
