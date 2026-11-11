import ast
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from multisim_native_mcp.persistence import persistence_capabilities
from multisim_native_mcp.service import EditorService,NativeEditError
from multisim_native_mcp.settings import normalize_setting_changes,saved_execution,validate_analysis_options
from multisim_native_mcp.workflow_contracts import WorkflowPlan


@pytest.mark.parametrize('changes',[
    [{'path':[],'value':1}],[{'path':[True],'value':1}],[{'path':[-1],'value':1}],
    [{'path':['ANALYSIS','TSTOP'],'value':float('nan')}],[{'path':[''],'value':1}],
    [{'path':['ANALYSIS'],'value':{'TSTOP':1}}],[{'path':['A'],'value':1,'extra':1}],
])
def test_invalid_native_changes_rejected_before_transport(changes):
    with pytest.raises(ValueError):normalize_setting_changes(changes)


def test_paths_preserve_duplicate_field_indexes_and_scalar_types():
    assert normalize_setting_changes([{'path':['ANALYSIS',3],'value':True}])==[{'path':['ANALYSIS',3],'value':True}]


@pytest.mark.parametrize('args',[
    {'scope':'wrong'},{'solver_options':{'reltol':float('inf')}},{'solver_options':{'method':{}}},
    {'solver_options':{'reltol;quit':1}},{'save_to_source':1},{'analysis_type':'TRAN;quit'},
    {'changes':[{'path':['ANALYSIS',3],'value':1}]},
])
def test_invalid_simulation_options_never_reach_native_calls(args):
    host=EditorService();host.call=lambda *args:pytest.fail('Native transport reached')
    with pytest.raises(ValueError):host.simulation_settings(**args)


def settings_host():
    host=EditorService();calls=[]
    def call(op,args=None):
        calls.append((op,args))
        if op=='interactiveStatus':return {'state_name':'stopped'}
        if op=='simulationSettingsText':return 'native original'
        if op=='documentSimulationSettings':return {'fields':[],'changed':bool(args['changes'] or args['solver_options']),'_simulation_text':'native updated'}
        if op=='interactiveOptions':return {'configuration':{'time_step':.01}}
        if op=='markModified':return {}
        raise AssertionError(op)
    host.call=call;host.checkpoint=lambda:{'path':'checkpoint'}
    host.restore=lambda checkpoint:calls.append(('restore',checkpoint))
    return host,calls


def test_catalog_revision_matches_the_same_native_snapshot_without_mutation():
    host,calls=settings_host();result=host.simulation_settings()
    assert result['revision']==hashlib.sha256(b'native updated').hexdigest()
    assert result['saved_to_file'] is False and '_simulation_text' not in result
    assert [op for op,_ in calls]==['simulationSettingsText','documentSimulationSettings']
    calls.clear()
    with pytest.raises(RuntimeError,match='changed'):host.simulation_settings(changes=[{'path':['ANALYSIS','TSTOP'],'value':1}],expected_revision='stale')
    assert all(op!='documentSimulationSettings' for op,_ in calls)


def test_native_transaction_receives_expected_snapshot_and_clears_overrides():
    host,calls=settings_host()
    result=host.simulation_settings(changes=[{'path':['ANALYSIS','TSTOP'],'value':1}],expected_revision=hashlib.sha256(b'native original').hexdigest())
    sent=next(args for op,args in calls if op=='documentSimulationSettings')
    assert sent['expected_text']=='native original'
    assert ('interactiveOptions',{'reset':True}) in calls and host.undo_stack==[{'path':'checkpoint'}]
    assert not result['saved_to_file']


def test_failed_source_save_restores_document_and_temporary_override():
    host,calls=settings_host()
    host._save_source=lambda:(_ for _ in ()).throw(RuntimeError('source conflict'))
    with pytest.raises(NativeEditError,match='source conflict') as caught:
        host.simulation_settings(changes=[{'path':['ANALYSIS','TSTOP'],'value':1}],save_to_source=True)
    assert caught.value.details['rolled_back'] and caught.value.details['handles_invalidated']
    assert calls[-2:]==[('restore',{'path':'checkpoint'}),('interactiveOptions',{'configuration':{'time_step':.01}})]
    assert not host.undo_stack


@pytest.mark.parametrize('method,options',[
    ('configure_wiring',{'move_connection_limit':True}),('configure_wiring',{'autowire_on_move':1}),
    ('configure_wiring',{'reset':True,'persist':True}),('configure_sheet_display',{'show_grid':1}),
    ('configure_sheet_display',{'unrecognized':True}),('configure_sheet_display',{'save_to_source':1}),
])
def test_preferences_validate_before_native_calls(method,options):
    host=EditorService();host.call=lambda *args:pytest.fail('Invalid preferences reached native transport')
    with pytest.raises(ValueError):getattr(host,method)(**options)


def test_application_wiring_persistence_is_explicitly_separate_from_circuit():
    host=EditorService();calls=[]
    def call(op,args=None):
        calls.append((op,args))
        if op=='interactiveStatus':return {'state_name':'stopped'}
        if op=='persistWiringOptions':return {'scope':'application','persisted_in_circuit':False,'saved_to_application':True}
        return {}
    host.call=call
    assert host.configure_wiring(autowire_on_move=True,persist=True)['scope']=='application'
    assert calls[-1][0]=='persistWiringOptions'


def test_audit_covers_every_public_tool_exactly_once():
    from multisim_native_mcp import server
    tree=ast.parse(Path(server.__file__).read_text(encoding='utf-8'))
    names={n.name for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith('native_')}
    audit=persistence_capabilities();assert len(audit['tools'])==len(names)
    assert {t['tool'] for t in audit['tools']}==names


def stored(analysis,**values):
    return {'analysis_type':analysis,'fields':[{'path':['ANALYSIS',key],'value':value} for key,value in values.items()]}


def test_saved_execution_bounds_finite_native_jobs_without_changing_the_document():
    saved_execution(stored('TRAN',TSTART=0,TSTOP=2,TSTEP=.001))
    saved_execution(stored('TRAN',TSTART=0,TSTOP=2,TSTEP='calculate'))
    saved_execution(stored('AC',VARIATION='lin',NPOINTS_PER_VARIATION=21,FSTART=10,FSTOP=10000))
    for settings in [stored('TRAN',TSTART=0,TSTOP=1e30,TSTEP=.001),
                     stored('TRAN',TSTART=0,TSTOP=2,TSTEP=1e-12),
                     stored('AC',VARIATION='dec',NPOINTS_PER_VARIATION=100000,FSTART=1,FSTOP=1e9)]:
        with pytest.raises(ValueError):saved_execution(settings)


@pytest.mark.parametrize('kwargs',[{'step':True},{'ac_points':True},{'persist':1},{'save_to_source':True},
                                    {'persist':True,'use_saved_settings':True}])
def test_analysis_persistence_preflight(kwargs):
    options={'analysis':'tran','step':1e-5,'stop':.01,'use_initial_conditions':False,**kwargs}
    with pytest.raises(ValueError):validate_analysis_options(**options)


def test_workflow_supports_settings_display_and_explicit_source_save():
    plan=WorkflowPlan.model_validate({'steps':[
        {'id':'settings','kind':'simulation_settings','scope':'analysis','analysis_type':'TRAN','solver_options':{'reltol':.0001}},
        {'id':'display','kind':'sheet_display','show_grid':False},
        {'id':'save','kind':'save','save_to_source':True}]})
    assert plan.steps[-1].save_to_source
    assert not WorkflowPlan.model_validate({'steps':[{'kind':'save','id':'save'}]}).steps[0].output_path
    for save in [{'kind':'save','id':'save','output_path':'x','save_to_source':True},
                 {'kind':'save','id':'save','save_to_source':True,'verify':False}]:
        with pytest.raises(ValidationError):WorkflowPlan.model_validate({'steps':[save]})


def test_workflow_executes_settings_and_source_save_and_exposes_backup(tmp_path):
    from test_workflows import Host
    from multisim_native_mcp.workflows import WorkflowManager
    host=Host(tmp_path);host.source=tmp_path/'source.ms14';host.source.write_bytes(b'original');calls=[]
    def settings(**kwargs):calls.append(('settings',kwargs));return {'saved_to_file':False}
    def display(**kwargs):calls.append(('display',kwargs));return {'saved_to_file':False}
    def save(**kwargs):calls.append(('save',kwargs));return {'path':str(host.source),'backup':'source.bak','saved_to_source':True,'verification':{'passed':True}}
    host.simulation_settings=settings;host.configure_sheet_display=display;host.save_source=save
    manager=WorkflowManager(host,tmp_path/'records')
    result=manager.start({'steps':[
        {'id':'settings','kind':'simulation_settings','scope':'analysis','analysis_type':'TRAN','solver_options':{'method':'gear'}},
        {'id':'display','kind':'sheet_display','show_grid':False},
        {'id':'save','kind':'save','save_to_source':True}]})
    assert result['status']=='complete',result
    assert [op for op,_ in calls]==['settings','display','save']
    assert result['results']['save']['backup']=='source.bak'
