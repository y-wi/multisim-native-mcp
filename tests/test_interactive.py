import pytest
from multisim_native_mcp.service import EditorService


def fake_host(states):
    h=EditorService();iterator=iter(states);last=states[-1];calls=[]
    def call(operation,args=None):
        nonlocal last
        calls.append((operation,args))
        if operation=='interactiveStatus':
            last=next(iterator,last)
            return {'state_name':last,'state':{'unprepared':-1,'stopped':0,'running':1,'paused':2}[last],'remote_initialized':last in ('running','paused')}
        if operation=='interactiveCommand':return {'action':args['action'],'requested':True,'command_id':42}
        raise AssertionError(operation)
    h.call=call
    return h,calls


def test_interactive_transition_is_observed_and_resume_is_separate():
    h,calls=fake_host(['paused','paused','running'])
    result=h.control_interactive('resume',.5)
    assert result['requested'] and result['transition_confirmed'] and result['state_name']=='running'
    assert ('interactiveCommand',{'action':'resume'}) in calls
    h,calls=fake_host(['running'])
    assert h.control_interactive('start')['already_in_state']
    assert all(operation!='interactiveCommand' for operation,args in calls)


def test_interactive_timeout_does_not_claim_transition():
    h,calls=fake_host(['stopped'])
    result=h.control_interactive('start',0)
    assert result['requested'] and not result['transition_confirmed']
    assert result['state_name']=='stopped'


def test_invalid_transition_and_numeric_job_do_not_dispatch_commands():
    h,calls=fake_host(['paused'])
    with pytest.raises(ValueError,match='Cannot start'):h.control_interactive('start')
    assert all(operation!='interactiveCommand' for operation,args in calls)
    h.analysis_job={'status':'running'}
    with pytest.raises(RuntimeError,match='numeric analysis'):h.interactive_status()


def test_numeric_context_is_cleaned_before_interactive_start():
    h,calls=fake_host(['stopped','stopped','running']);h.numeric_session_used=True
    result=h.control_interactive('start')
    assert not result['handles_invalidated'] and result['numeric_context_cleaned']
    assert calls.index(('interactiveCommand',{'action':'stop'}))<calls.index(('interactiveCommand',{'action':'start'}))
    assert not h.numeric_session_used


@pytest.mark.parametrize('args',[{'wait_timeout':-1},{'wait_timeout':float('nan')},{'active_component':''}])
def test_invalid_interactive_capture_options_fail_before_native_calls(args):
    h=EditorService();h.call=lambda *args:pytest.fail('Reached native calls')
    with pytest.raises(ValueError):h.export_interactive_image('unused.png',**args)


@pytest.mark.parametrize('options',[
    {'time_step':0},{'time_step':float('nan')},{'max_time_step':float('inf')},
    {'max_time_step':-2},{'time_step':True},{'real_time':1},{'reset':1},
    {'reset':True,'time_step':.001},
])
def test_invalid_interactive_solver_options_do_not_reach_native_host(options):
    h=EditorService();h.call=lambda *args:pytest.fail('Invalid options reached native host')
    with pytest.raises(ValueError):h.configure_interactive(**options)


def test_configuration_is_readable_during_run_but_changes_require_stopped_state():
    h,calls=fake_host(['running'])
    h.call=lambda op,args=None:({'configuration':{'time_step':.001}} if op=='interactiveOptions' else
                               {'state_name':'running'})
    assert h.configure_interactive()['configuration']['time_step']==.001
    for options in [{'time_step':.001},{'reset':True}]:
        with pytest.raises(RuntimeError,match='Stop interactive'):h.configure_interactive(**options)


def test_configuration_has_explicit_units_and_numeric_job_guard():
    h,calls=fake_host(['stopped']);original=h.call
    h.call=lambda op,args=None:args if op=='interactiveOptions' else original(op,args)
    assert h.configure_interactive(.001,.0001,True)=={
        'configuration':{'time_step':.001,'max_time_step':.0001,'real_time':True},'reset':False}
    assert h.configure_interactive(reset=True)=={'configuration':{},'reset':True}
    h.analysis_job={'status':'running'}
    with pytest.raises(RuntimeError,match='numeric analysis'):h.configure_interactive(time_step=.001)
