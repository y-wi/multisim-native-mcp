import pytest
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.settings import normalize_setting_changes,validate_analysis_options
from multisim_native_mcp.workflow_contracts import WorkflowPlan
from multisim_native_mcp.waveforms import parse_raw


def test_large_workflows_and_settings_have_no_workload_ceiling():
    plan=WorkflowPlan.model_validate({'steps':[{'id':'edit','kind':'edit','operations':[
        {'operation':'move','arguments':{'ref':'R1','dx':100001,'dy':0}} for _ in range(1100)]}]})
    assert plan.max_runtime is None and len(plan.steps[0].operations)==1100
    assert WorkflowPlan.model_validate({'max_runtime':1000000,'steps':[{'id':'close','kind':'close'}]}).max_runtime==1000000
    assert len(normalize_setting_changes([{'path':['nested']*20+[10000],'value':1} for _ in range(120)]))==120
    validate_analysis_options('tran',1e-15,1000,False)
    validate_analysis_options('ac',1e-5,.01,False,'dec',1000000,1,1e20)


@pytest.mark.parametrize('op,args',[
    ('move',{'x':100001,'y':-100001}),('setParameter',{'index':1000,'value':1}),
    ('sheetSize',{'width':12000,'height':12000}),('sheetSize',{'width':1,'height':1}),
    ('route',{'points':[{'x':n,'y':0} for n in range(1100)]}),
    ('transform',{'angle':37.5}),('addText',{'text':'text'*2000,'x':0,'y':0}),('rename',{'ref':'电阻一'}),
])
def test_edits_beyond_old_artificial_limits(op,args):
    EditorService.validate(op,args)


def test_native_coordinate_storage_range_is_preserved():
    with pytest.raises(ValueError):EditorService.validate('move',{'x':2147483648})


def test_raw_reader_accepts_more_than_ten_thousand_vectors(tmp_path):
    count=10001;file=tmp_path/'many.raw'
    file.write_text('No. Variables: '+str(count)+'\nNo. Points: 1\nVariables:\n'+
                    ''.join(str(n)+' v'+str(n)+' voltage\n' for n in range(count))+
                    'Values:\n0 0\n'+'0\n'*(count-1),encoding='utf-8')
    assert len(parse_raw(file)['variables'])==count


@pytest.mark.parametrize('stopped',[False,True])
def test_capture_without_deadline_still_stops_or_cancels(tmp_path,stopped):
    import threading
    host=EditorService();host.working=tmp_path/'circuit.ms14';cancel=threading.Event()
    def call(op,args=None):
        if op=='circuitState':return {'page':{'width':100,'height':100,'bounds':{'left':0,'top':0,'right':100,'bottom':100}},'content_bounds':None,'components':[]}
        if op=='exportInteractiveImage':
            cancel.set();return {'ready':False,'state':0 if stopped else 1}
        raise AssertionError(op)
    host.call=call
    with pytest.raises(RuntimeError if stopped else InterruptedError):
        host.export_image(str(tmp_path/'frame.png'),interactive=True,cancel=cancel)


def test_report_accepts_more_than_eight_signals():
    from multisim_native_mcp.reports import waveform_svg
    data={'complex':False,'variables':[{'index':0,'name':'v','native_name':'v','kind':'voltage','unit':'V'}],'rows':[[1],[2]]}
    assert waveform_svg(data,['v']*9).count('<polyline')==9


def test_sheet_dimensions_check_actual_native_work_area_encoding():
    with pytest.raises(ValueError,match='CUTRect'):
        EditorService.validate('sheetSize',{'width':20000,'height':20000})


def test_close_has_no_timed_kill():
    from types import SimpleNamespace
    from multisim_native_mcp.bridge import NativeHost
    events=[];host=NativeHost()
    host.process=SimpleNamespace(pid=1,poll=lambda:None,terminate=lambda:events.append('terminate'),wait=lambda:events.append('wait'))
    host.close();assert events==['terminate','wait']
