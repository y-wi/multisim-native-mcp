import shutil
from pathlib import Path

import pytest

from multisim_native_mcp.bridge import sha256
from multisim_native_mcp.paths import RESOURCE_DIR
from multisim_native_mcp.service import EditorService,NativeEditError

pytestmark=pytest.mark.native


def source_file(tmp_path):
    source=tmp_path/'持久化电路.ms14';shutil.copy2(RESOURCE_DIR/'assets'/'blank14.3.ms14',source)
    return source


def field(settings,*path):
    return next(f['value'] for f in settings['fields'] if f['path']==list(path))


def test_all_native_analysis_profiles_solver_options_and_atomic_source_reopen(tmp_path):
    source=source_file(tmp_path);host=EditorService()
    try:
        opened=host.open_copy(str(source));original_hash=sha256(source)
        initial=host.simulation_settings();analyses=initial['available_analyses']
        assert {'TRAN','AC','OP','PSWEEP','MONTE','WORST'}<=set(analyses)
        assert {'reltol','abstol','vntol','method','itl4','temp'}<={o['name'] for o in initial['solver_options']}
        for scope in ['interactive','analysis']:
            for kind in analyses:
                result=host.simulation_settings(scope,kind,changes=[{'path':['MAX_POINTS'],'value':127999}])
                assert field(result,'MAX_POINTS')==127999
        advanced=host.simulation_settings('interactive','TRAN',solver_options={
            'reltol':.0002,'abstol':2e-12,'vntol':2e-6,'method':'gear','itl4':150,'temp':35,'inertialdelay':False},
            changes=[{'path':['ANALYSIS','TSTEP'],'value':.001},{'path':['ANALYSIS','TMAX'],'value':.001},
                     {'path':['ANALYSIS','IC'],'value':'zero_ic'},{'path':['DIGITAL_THRESHOLD_H'],'value':3},
                     {'path':['DIGITAL_THRESHOLD_L'],'value':2},{'path':['PLOT_TITLE'],'value':'原生仿真参数测试'}])
        assert field(advanced,'MSM_ASYS_OPT')==0 and field(advanced,'USE_ASYS_OPT')==1
        commands=host.call('documentAnalysisCommands',{'scope':'interactive','analysis_type':'TRAN'})
        assert 'zero_ic' in commands['command'] and 'reltol = 0.0002' in commands['options_command']
        assert 'itl4 = 150' in commands['options_command'] and 'temp = 35' in commands['options_command']
        assert '"gear"' in commands['options_command'] and 'set inertialdelay' not in commands['options_command']
        before=host.call('simulationSettingsText')
        with pytest.raises(NativeEditError):host.simulation_settings(solver_options={'reltol':-1})
        assert host.call('simulationSettingsText')==before
        ac=host.simulation_settings('analysis','AC')
        duplicate=next(f for f in ac['fields'] if f['label']=='hrange' and isinstance(f['path'][-1],int))
        host.simulation_settings('analysis','AC',changes=[{'path':duplicate['path'],'value':2}],expected_revision=ac['revision'])
        assert sha256(source)==original_hash
        saved=host.save_source();assert saved['verification']['simulation_settings_preserved']
        assert sha256(Path(saved['backup']))==original_hash
        host.close();reopened=host.open_copy(str(source));assert opened['pid']!=reopened['pid']
        for scope in ['interactive','analysis']:
            for kind in analyses:assert field(host.simulation_settings(scope,kind),'MAX_POINTS')==127999
        actual=host.simulation_settings('interactive','TRAN')
        assert field(actual,'PLOT_TITLE')=='原生仿真参数测试'
        assert actual['solver_options']==advanced['solver_options']
        actual_commands=host.call('documentAnalysisCommands',{'scope':'interactive','analysis_type':'TRAN'})
        assert actual_commands==commands
    finally:host.close()


def test_saved_numeric_settings_and_full_document_source_save(tmp_path):
    source=source_file(tmp_path);host=EditorService()
    try:
        host.open_copy(str(source))
        for name,ref,x,y in [('DC_POWER','V1',108,108),('RESISTOR_VIRTUAL','R1',306,108),('RESISTOR_VIRTUAL','R2',504,108),('GROUND','0',108,306)]:
            host.edit('place',{'name':name,'ref':ref,'x':x,'y':y})
        for ref,value in [('V1',12),('R1',1000),('R2',1000)]:host.edit('setParameter',{'ref':ref,'index':1,'value':value})
        for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]:
            host.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        diode=host.edit('place',{'name':'1N4148','ref':'D1','x':600,'y':306})['component']
        for pin in diode['pins']:host.edit('wire',{'source':{'ref':'D1','pin':pin['name']},'target':{'ref':'0','pin':'1'}})
        model=host.call('modelInfo',{'ref':'D1'});text=next(a['text'] for a in model['attributes'] if a['index']==1)
        text+='\n* MCP persistent model roundtrip\n'
        host.edit('setModelText',{'ref':'D1','text':text})
        host.edit('addText',{'text':'持久化验证','x':108,'y':450})
        host.edit('sheetTitle',{'title':'Persistent settings'})
        display=host.configure_sheet_display(show_grid=False,show_border=True,show_bounds=False)
        host.simulation_settings('analysis','TRAN',changes=[{'path':['ANALYSIS','TMAX'],'value':.0001}],solver_options={'reltol':.0002,'method':'gear','itl4':150})
        numeric=host.run_analysis('tran',step=.0001,stop=.002,persist=True,save_to_source=True)
        assert numeric['vectors'][0]['last']==pytest.approx(.002)
        assert 'reltol = 0.0002' in numeric['document_settings']['commands']['options_command']
        assert numeric['document_settings']['saved_to_file']
        host.close();host.open_copy(str(source))
        assert host.configure_sheet_display()['native_preferences']==display['native_preferences']
        assert next(a['text'] for a in host.call('modelInfo',{'ref':'D1'})['attributes'] if a['index']==1)==text
        state=host.call('projectCircuitState',{'include_parameters':True,'include_persistence':True})['states'][0]
        assert any(a['text']=='持久化验证' for a in state['annotations'])
        assert state['sheets'][0]['page']=='Persistent settings'
        dc=host.run_analysis('op',use_saved_settings=True)
        assert next(v for v in dc['vectors'] if v['name']=='I(V1)')['last']==pytest.approx(-.006,abs=1e-8)
        ac=host.run_analysis('ac',ac_sweep='lin',ac_points=21,ac_start=10,ac_stop=10000,persist=True,save_to_source=True)
        assert ac['points']==21 and ac['vectors'][0]['last']==pytest.approx([10000,0])
        host.close();host.open_copy(str(source))
        saved_ac=host.run_analysis('ac',use_saved_settings=True)
        assert saved_ac['points']==21 and saved_ac['vectors'][0]['first']==pytest.approx([10,0])
        job=host.start_analysis('tran',step=.0001,stop=.003,persist=True,save_to_source=True)
        host.analysis_thread.join(timeout=30)
        assert host.analysis_job['status']=='complete',host.analysis_job
        assert host.analysis_job['result']['vectors'][0]['last']==pytest.approx(.003)
        assert host.analysis_job['result']['document_settings']['saved_to_file']
    finally:host.close()


def test_native_application_wiring_preferences_survive_new_process_and_restore(tmp_path):
    source=source_file(tmp_path);host=EditorService();original=None
    keys=('autowire_on_connection','autowire_on_move','connect_touching','move_connection_limit')
    try:
        host.open_copy(str(source));original={k:v for k,v in host.configure_wiring().items() if k in keys}
        desired={**original,'connect_touching':not original['connect_touching'],'move_connection_limit':13}
        saved=host.configure_wiring(**desired,persist=True)
        assert saved['scope']=='application' and not saved['persisted_in_circuit'] and saved['saved_to_application']
        host.close();host.open_copy(str(source))
        actual=host.configure_wiring();assert all(actual[k]==value for k,value in desired.items())
    finally:
        if original:
            if not host.agent:host.open_copy(str(source))
            host.configure_wiring(**original,persist=True)
        host.close()
