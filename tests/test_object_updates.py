import copy
import pytest
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.workflow_contracts import WorkflowPlan
from multisim_native_mcp.workflows import remap_bindings


@pytest.mark.parametrize('operation,args',[
    ('updateText',{'id':'text'}),('deleteText',{}),('updateText',{'id':'text','text':None}),
    ('updateSheet',{}),('updateSheet',{'width':0}),('updateSheet',{'height':20000}),
    ('moveJunction',{'id':'junction','x':0}),('updatePort',{'id':'port'}),('updatePort',{'id':'port','name':'bad\0name'}),
])
def test_invalid_object_updates_are_rejected_before_native_edits(operation,args):
    with pytest.raises(ValueError):EditorService.validate(operation,args)


@pytest.mark.parametrize('operation,args',[
    ('updateText',{'id':'text','text':''}),('updateText',{'id':'text','x':-9}),
    ('deleteText',{'id':'text'}),('updateSheet',{'width':1200}),
    ('moveJunction',{'id':'junction','x':180,'y':90}),('updatePort',{'id':'port','name':'INPUT'}),
])
def test_object_updates_are_available_in_workflows(operation,args):
    EditorService.validate(operation,args)
    WorkflowPlan.model_validate({'steps':[{'id':'edit','kind':'edit','operations':[{'operation':operation,'arguments':args}]}]})


def test_text_bindings_remap_after_native_refresh_and_reject_ambiguity():
    before={'handle_epoch':[1,1],'texts':[{'id':'old','text':'Note','transform':[1,0,0,1,90,90]}]}
    after=copy.deepcopy(before);after['handle_epoch']=[1,2];after['texts'][0]['id']='new'
    assert remap_bindings({'note':{'id':'old'}},before,after)=={'note':{'id':'new'}}
    after['texts'].append({**after['texts'][0],'id':'another'})
    assert remap_bindings({'note':{'id':'old'}},before,after)['note']['id']=={'$invalid_handle':'old'}


def test_text_bindings_survive_in_place_changes_between_workflow_stages():
    before={'handle_epoch':[1,1],'texts':[{'id':'note','text':'Old','transform':[1,0,0,1,90,90]}]}
    after=copy.deepcopy(before);after['texts'][0].update(text='New',transform=[1,0,0,1,180,90])
    assert remap_bindings({'note':{'id':'note'}},before,after)=={'note':{'id':'note'}}


def test_incremental_state_reports_text_edits_deletion_and_changed_handles(tmp_path):
    from types import SimpleNamespace
    from threading import RLock
    from multisim_native_mcp.workflows import WorkflowManager
    state={'components':[],'wires':[],'page':{},'texts':[{'id':'old','text':'Note','transform':[1,0,0,1,90,90]}]}
    host=SimpleNamespace(call=lambda *a:copy.deepcopy(state),lock=RLock())
    manager=WorkflowManager(host,tmp_path/'records')
    first=manager.session_state()
    state['texts'][0]['id']='new'
    delta=manager.session_state(first['revision'])
    assert delta['changed'] and delta['texts'][0]['id']=='new' and delta['removed_text_ids']==['old']
    state['texts']=[]
    delta=manager.session_state(delta['revision']);assert delta['texts']==[] and delta['removed_text_ids']==['new']
