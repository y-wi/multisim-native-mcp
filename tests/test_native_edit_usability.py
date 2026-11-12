import pytest
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_compact_public_edits_aliases_and_explicit_refresh_mapping(tmp_path,monkeypatch):
    from multisim_native_mcp import server
    host=EditorService();source=tmp_path/'divider.ms14'
    monkeypatch.setattr(server,'host',host)
    try:
        host.create('Compact divider',str(source))
        host.configure_wiring(connect_touching=False,autowire_on_connection=False,autowire_on_move=False)
        operations=[{'operation':'native_place_component','arguments':{'name':name,'reference':ref,'x':x,'y':y,
                      **({'parameters':[{'index':1,'value':value}]} if value is not None else {})}}
                    for name,ref,x,y,value in [('DC_POWER','V1',90,90,12),('RESISTOR_VIRTUAL','R1',360,90,1000),
                                             ('RESISTOR_VIRTUAL','R2',540,90,1000),('GROUND','0',90,360,None)]]
        operations += [{'operation':'connect_pins','arguments':{'source_ref':a,'source_pin':ap,'target_ref':b,'target_pin':bp}}
                       for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]]
        edited=server.native_edit_batch(operations)
        assert all(len(item.get('parameters',[]))<=1 for item in edited['results'])
        assert edited['results'][1]['parameter_count']>1 and not edited['results'][1]['parameters_complete']
        note=server.native_add_text('Before refresh',90,450)
        old=server.native_get_circuit_state()
        old_r1=next(c['id'] for c in old['components'] if c['ref']=='R1')
        checked=server.native_check_netlist()
        assert checked['handles_invalidated'] and checked['id_map'] is not None
        current_r1=next(c['id'] for c in checked['state']['components'] if c['ref']=='R1')
        assert checked['id_map'].get(old_r1,old_r1)==current_r1
        assert checked['id_map'].get(note['id'],note['id'])==checked['state']['texts'][0]['id']
        repeated=server.native_connect_endpoints({'component_ref':'R2','pin':'1'},{'component_ref':'R1','pin':'2'})
        assert repeated['alreadyConnected'] and len(host.call('wires')['wires'])==4
        assert server.native_check_netlist()['handles_invalidated'] is False
        server.native_edit_batch([
            {'operation':'move_component','arguments':{'component_ref':current_r1,'dx':9,'dy':0}},
            {'operation':'update_text','arguments':{'object_id':checked['id_map'].get(note['id'],note['id']),'text':'After refresh'}},
        ],include_state=False)
        assert server.native_check_netlist()['handles_invalidated'] is False
        current=server.native_get_circuit_state()
        assert current['texts'][0]['text']=='After refresh'
        server.native_delete_object(object_id=current['texts'][0]['id'])
        assert server.native_check_netlist()['handles_invalidated'] is False
        restored=server.native_undo()
        assert restored['handles_invalidated'] and 'id_map' in restored and restored['state']['texts']
        redone=server.native_redo();assert not redone['state']['texts']
        assert len(server.native_get_parameters('R1')['parameters'])>1
        assert len(next(c for c in server.native_get_circuit_state(include_parameters=True)['components'] if c['ref']=='R1')['parameters'])>1
        numeric=host.run_analysis('op')
        assert next(v for v in numeric['vectors'] if v['name']=='I(V1)')['last']==pytest.approx(-.006,abs=1e-8)
        before=host.call('simulationSettingsText')
        host.configure_interactive(time_step=.000123,max_time_step=.000123,persist=True)
        differences=host.call('simulationPropertyDiff',{'expected':before,'actual':host.call('simulationSettingsText')})['differences']
        step_changes=[d for d in differences if 'TSTEP' in d['path'] and not d['path'].endswith('.native_type') and d['actual'] is not None]
        assert any(float(d['actual'])==pytest.approx(.000123) for d in step_changes)
        assert server.native_save_source()['verification']['passed']
        host.close();host.open_circuit(str(source))
        assert len(host.call('wires')['wires'])==4 and not host.call('textObjects')
    finally:host.close()


def test_mixed_batch_returns_current_ids_after_creating_a_subcircuit(tmp_path):
    host=EditorService();source=tmp_path/'mixed.ms14'
    try:
        host.create('Mixed batch',str(source))
        result=host.batch([
            {'operation':'place_component','arguments':{'name':'RESISTOR_VIRTUAL','reference':'R1','x':180,'y':180,'parameters':[{'index':1,'value':1000}]}},
            {'operation':'create_subcircuit','arguments':{'title':'Child','reference':'X1','x':540,'y':180}},
        ],include_state=False)
        assert result['handles_invalidated'] and 'id_map' in result
        current=next(c for c in result['state']['components'] if c['ref']=='R1')
        assert result['results'][0]['component']['id']==current['id']
        moved=host.edit('move_component',{'component_ref':result['results'][0]['component']['id'],'dx':9,'dy':0})
        assert moved['ref']=='R1'
        assert host.save_source()['verification']['passed']
    finally:host.close()
