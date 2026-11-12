import asyncio
import copy
import json
import pytest

from multisim_native_mcp.edit_contracts import normalize_edit
from multisim_native_mcp.identity import identity_changes
from multisim_native_mcp.response_views import compact_result
from multisim_native_mcp.save_differences import saved_differences,difference_summary
from multisim_native_mcp.service import EditorService,changes_topology
from multisim_native_mcp.workflow_contracts import WorkflowPlan


@pytest.mark.parametrize('operation,arguments,expected_op,expected',[
    ('native_route_wire',{'wire_id':'w','points':[]},'route',{'id':'w','points':[]}),
    ('native_move_component',{'component_ref':'R1','dx':9,'dy':0},'move',{'ref':'R1','dx':9,'dy':0}),
    ('transform_component',{'component_ref':'R1','mirror_axis':'horizontal'},'transform',{'ref':'R1','axis':'horizontal'}),
    ('connect_touching',{'component_refs':['R1']},'connectTouching',{'refs':['R1']}),
    ('delete_object',{'object_id':'text'},'remove',{'id':'text'}),
    ('move_junction',{'junction_id':'j','x':9,'y':18},'moveJunction',{'id':'j','x':9,'y':18}),
    ('place_component',{'name':'R','reference':'R1','x':9,'y':18},'place',{'name':'R','ref':'R1','x':9,'y':18}),
    ('connect_pins',{'source_ref':'R1','source_pin':'1','target_ref':'R2','target_pin':'2'},'wire',{'source':{'ref':'R1','pin':'1'},'target':{'ref':'R2','pin':'2'}}),
    ('connect_endpoints',{'source':{'component_ref':'R1','pin':'1'},'target':{'junction_id':'j'}},'connectEndpoint',{'source':{'ref':'R1','pin':'1'},'target':{'junction_id':'j'}}),
    ('update_hierarchical_port',{'object_id':'p','name':'INPUT'},'updatePort',{'id':'p','name':'INPUT'}),
])
def test_standalone_spelling_works_in_batches_and_typed_workflows(operation,arguments,expected_op,expected):
    item={'operation':operation,'arguments':arguments}
    assert EditorService.normalize_edit(item)=={'operation':expected_op,'arguments':expected}
    plan=WorkflowPlan.model_validate({'steps':[{'kind':'edit','id':'change','operations':[item]}]})
    assert plan.steps[0].operations[0].arguments==expected
    assert item['arguments']==arguments


@pytest.mark.parametrize('operation,arguments',[
    ('route_wire',{'wire_id':'old','id':'new'}),
    ('move_component',{'component_ref':'R1','ref':'R2'}),
    ('connect_pins',{'source_ref':'R1'}),
    ('connect_endpoints',{'source':{'ref':'R1','pin':'1'},'source_ref':'R2','source_pin':'1'}),
])
def test_conflicting_selectors_fail_before_checkpoint_or_native_calls(operation,arguments):
    host=EditorService();host.call=lambda *a:pytest.fail('Native call reached')
    host.checkpoint=lambda:pytest.fail('Checkpoint reached')
    with pytest.raises(ValueError):host.batch([{'operation':operation,'arguments':arguments}])


def parameter_slots():
    return [{'index':n,'value':1000 if n==1 else 0,'expression':None,
             **({'role':'value','name':'resistance','unit':'Ohm'} if n==1 else {'role':'model_option'} if n==0 else {})} for n in range(16)]


def test_compact_results_preserve_values_and_do_not_modify_internal_metadata():
    raw={'state':{'components':[{'id':str(n),'ref':'R'+str(n),'parameters':parameter_slots()} for n in range(10)]}}
    view=compact_result(raw);component=view['state']['components'][0]
    assert component['parameters']==[raw['state']['components'][0]['parameters'][1]]
    assert component['parameter_count']==16 and component['parameters_complete'] is False
    assert len(raw['state']['components'][0]['parameters'])==16
    assert len(json.dumps(view))<len(json.dumps(raw))*.35


def test_compact_results_keep_selected_parameter_edits_and_experiment_values():
    values={'parameters':[{'ref':'R1','index':1,'value':2200}],'trial':{'parameters':[{'index':1,'value':1000}]}}
    assert compact_result(values)==values


def test_parameter_detail_is_opt_in_and_compatibility_tools_remain_callable(monkeypatch):
    from multisim_native_mcp import server
    monkeypatch.setattr(server.host,'edit',lambda *a:{'parameters':parameter_slots(),'id':'result'})
    monkeypatch.setattr(server.host,'call',lambda *a:{'parameters':parameter_slots()})
    compact=server.native_place_component('RESISTOR_VIRTUAL',90,90)
    full=server.native_place_component('RESISTOR_VIRTUAL',90,90,include_parameters=True)
    assert len(compact['parameters'])==1 and len(full['parameters'])==16
    assert len(server.native_get_parameters('R1')['parameters'])==16
    async def check():
        names={t.name for t in await server.server.list_tools()}
        assert {'native_connect_pins','native_delete_text'}.isdisjoint(names)
        alias=await server.server.call_tool('native_delete_text',{'object_id':'text'})
        data=alias.structured_content or json.loads(alias.content[0].text)
        assert not alias.is_error and data['id']=='result'
    asyncio.run(check())


def test_saved_parameter_difference_names_the_component_field_and_both_values():
    a={'ref':'R1','transform':[1,0,0,1,90,90],'pins':[],'parameters':parameter_slots()}
    b=copy.deepcopy(a);b['parameters'][1]['value']=2200
    differences=saved_differences([{'components':[a]}],[{'components':[b]}])
    assert differences==[{'path':'sheets[0].components[ref="R1"].parameters[1].value','kind':'changed','expected':1000,'actual':2200}]
    summary=difference_summary(differences)
    assert 'R1' in summary and '1000 -> 2200' in summary and 'model_option' not in summary


def test_save_differences_distinguish_missing_fields_from_null_values():
    assert saved_differences({'model_text':None},{})==[{'path':'sheets.model_text','kind':'missing','expected':None}]
    assert saved_differences([None],[])==[{'path':'sheets[0]','kind':'missing','expected':None}]


def test_simulation_save_error_reports_native_field_values_and_preserves_output(tmp_path):
    from test_save_export import saving_host,scene
    from multisim_native_mcp.service import NativeSaveError
    host,calls=saving_host(tmp_path,[scene()]);original=host.call
    difference={'path':'simulation_settings["TRAN"]["TSTEP"]','kind':'changed','expected':.001,'actual':.01}
    def call(op,args=None):
        if op=='simulationPropertyDiff':return {'differences':[difference]}
        result=original(op,args)
        if op=='verifySavedCopy':result['simulation_settings']='changed settings'
        return result
    host.call=call;target=tmp_path/'source.ms14';target.write_bytes(b'original')
    with pytest.raises(NativeSaveError,match='TSTEP.*0.001 -> 0.01') as error:host.save_copy(str(target),True)
    assert error.value.details['differences']==[difference] and target.read_bytes()==b'original'


def test_identity_map_does_not_trust_reused_native_addresses():
    def c(id,ref,x):return {'id':id,'ref':ref,'local_ref':ref,'transform':[1,0,0,1,x,90],'pins':[]}
    before={'components':[c('a','VCC',90),c('b','VCC',180)],'texts':[{'id':'note','text':'Deleted','transform':[1,0,0,1,90,18]}]}
    after={'components':[c('b','VCC',90),c('a','VCC',180)]}
    result=identity_changes(before,after)
    assert result=={'id_map':{'a':'b','b':'a'},'unresolved_ids':['note']}


def test_unmatched_component_label_is_reported_as_an_unresolved_handle():
    before={'components':[{'id':'part','ref':'R1','transform':[1,0,0,1,90,90],'pins':[],
                           'labels':[{'id':'label','kind':'reference','text':'R1','transform':[1,0,0,1,0,0]}]}]}
    assert identity_changes(before,{'components':[]})=={'id_map':{},'unresolved_ids':['label','part']}


def test_repeated_connection_does_not_trigger_another_netlist_refresh():
    assert not changes_topology('wire',{'alreadyConnected':True})
    assert not changes_topology('connectEndpoint',{'alreadyConnected':True})
    assert changes_topology('connectEndpoint',{'alreadyConnected':False})
    assert changes_topology('connectTouching',{'topology_changed':True})
    assert not changes_topology('connectTouching',{'topology_changed':False})
    assert not changes_topology('remove',{'deleted':True,'topology_changed':False})
