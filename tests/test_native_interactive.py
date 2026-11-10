import time
import pytest
from PIL import Image
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_numeric_to_interactive_controls_and_actual_lit_capture(tmp_path):
    h=EditorService()
    try:
        h.create('Native interactive display')
        for name,ref,x,y in [('DC_POWER','V1',90,90),('GROUND','0',90,585),('SEVEN_SEG_COM_A','DS1',540,270)]:
            h.edit('place',{'name':name,'ref':ref,'x':x,'y':y})
        for i in range(7):h.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R'+str(i+1),'x':300,'y':90+i*63,'parameters':[{'index':1,'value':330}]})
        for a,ap,b,bp in [('V1','1','DS1','COM'),('V1','2','0','1')]+[(a,ap,b,bp) for i,segment in enumerate('ABCDEFG') for a,ap,b,bp in [('DS1',segment,'R'+str(i+1),'1'),('R'+str(i+1),'2','0','1')]]:
            h.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        h.edit('setParameter',{'ref':'V1','index':1,'value':5})
        numeric=h.run_analysis('op');assert not numeric['native_result']['failed']
        configuration=h.configure_interactive(time_step=.001,max_time_step=.001,real_time=True)
        assert configuration['configured'] and not configuration['persisted_in_circuit']
        started=h.control_interactive('start',15)
        assert started['transition_confirmed'] and started['state_name']=='running' and started['numeric_context_cleaned'] and not started['handles_invalidated']
        actual=started['interactive_options']['last_start']
        assert actual['applied'] and actual['native_result'] in (None,0)
        assert actual['time_step']==.001 and actual['max_time_step']==.001 and actual['real_time']
        image=h.export_interactive_image(str(tmp_path/'actual-lit.png'),active_component='DS1',wait_timeout=15)
        assert image['capture_mode']=='instantaneous'
        assert next(d for d in image['display_states'] if d['ref']=='DS1')['decoded']=='8'
        with Image.open(image['path']) as im:
            assert sum(r>150 and g<90 and b<90 for r,g,b in im.convert('RGB').get_flattened_data())>100
        paused=h.control_interactive('pause');assert paused['transition_confirmed'] and paused['state_name']=='paused'
        with pytest.raises(RuntimeError,match='Stop interactive'):h.configure_interactive(reset=True)
        with pytest.raises(RuntimeError,match='Stop interactive'):h.edit('move',{'ref':'R1','dx':9,'dy':0})
        with pytest.raises(RuntimeError,match='Stop interactive'):h.netlist()
        with pytest.raises(RuntimeError,match='Stop interactive'):h.history('undo')
        before=h.interactive_status()['simulation_time_s'];time.sleep(.15)
        assert h.interactive_status()['simulation_time_s']==before
        resumed=h.control_interactive('resume');assert resumed['transition_confirmed'] and resumed['state_name']=='running'
        stopped=h.control_interactive('stop');assert stopped['transition_confirmed'] and stopped['state_name'] in ('stopped','unprepared')
        stopped_state=h.interactive_status(include_displays=True)
        assert not stopped_state['remote_initialized']
        assert not stopped_state['display_readout_available'] and stopped_state['display_states']==[]
        assert not h.configure_interactive(reset=True)['configured']
        with pytest.raises(Exception,match='Start interactive'):h.export_interactive_image(str(tmp_path/'stopped.png'))
        h.save_copy(str(tmp_path/'display.ms14'))
    finally:h.close()

