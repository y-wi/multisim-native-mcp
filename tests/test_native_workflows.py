import pytest

from multisim_native_mcp.service import EditorService
from multisim_native_mcp.workflows import WorkflowManager

pytestmark=pytest.mark.native


def divider_plan(folder):
    def ref(name):return {'$ref':name+'.component.id'}
    operations=[]
    for name,alias,reference,x,y,value in [
        ('DC_POWER','supply','V1',108,180,12),('RESISTOR_VIRTUAL','upper','R1',360,180,1000),
        ('RESISTOR_VIRTUAL','lower','R2',540,180,1000),('GROUND','ground','0',108,450,None)]:
        a={'name':name,'ref':reference,'x':x,'y':y,'anchor':'pin','pin':'1'}
        if value is not None:a['value']=value
        if name=='RESISTOR_VIRTUAL':a.update(family='RESISTOR',group='Basic')
        operations.append({'operation':'place','bind':alias,'arguments':a})
    for s,sp,t,tp in [('supply','1','upper','1'),('upper','2','lower','1'),('lower','2','supply','2'),('supply','2','ground','1')]:
        operations.append({'operation':'wire','arguments':{'source':{'ref':ref(s),'pin':sp},'target':{'ref':ref(t),'pin':tp}}})
    return {'steps':[
        {'id':'session','kind':'session','mode':'create','title':'Workflow divider','output_path':str(folder/'divider-initial.ms14')},
        {'id':'wiring','kind':'wiring','connect_touching':False,'autowire_on_connection':True},
        {'id':'build','kind':'edit','operations':operations},
        {'id':'layout','kind':'layout'},
        {'id':'dc','kind':'analysis','options':{'analysis':'op'},'measurements':[
            {'id':'midpoint','metric':'mean','signal':{'ref':ref('lower'),'pin':'1'}},
            {'id':'current','metric':'mean','signal':{'current':ref('supply')}}],
         'criteria':[{'id':'midpoint','target':6,'absolute_tolerance':1e-8},
                     {'id':'current','target':-.006,'absolute_tolerance':1e-9}]},
        {'id':'save','kind':'save','output_path':str(folder/'divider.ms14')},
        {'id':'image','kind':'export','output_path':str(folder/'divider.png')},
        {'id':'close','kind':'close'}]}


def finish(manager,result):
    for _ in range(12):
        if result['status'] not in ('queued','running','cancel_requested'):return result
        result=manager.status(result['id'],30)
    raise AssertionError('Workflow did not finish')


def test_native_workflow_build_analyze_save_and_export(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
    try:
        result=finish(manager,manager.start(divider_plan(tmp_path)))
        assert result['status']=='complete',result
        assert result['results']['dc']['passed']
        assert result['results']['save']['verification']['passed']
        assert result['stats']['external_calls']<=3
        detail=manager.status(result['id'],detail=True)
        assert len(detail['completed'])==8
        assert detail['bindings']['lower']['component']['id']==detail['bindings']['build']['results'][2]['component']['id']
        assert (tmp_path/'divider.png').stat().st_size>1000
    finally:manager.shutdown();host.close()


def test_native_failed_edit_stage_rolls_back_and_resumes_without_rebuilding(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
    try:
        plan=divider_plan(tmp_path);plan['steps']=plan['steps'][:3]+[
            {'id':'adjust','kind':'edit','operations':[
                {'operation':'move','arguments':{'ref':{'$ref':'upper.component.id'},'dx':9,'dy':0}},
                {'operation':'move','arguments':{'ref':'MISSING','dx':9,'dy':0}}]}]
        failed=finish(manager,manager.start(plan))
        assert failed['status']=='failed' and failed['next_step']==3,failed
        detail=manager.status(failed['id'],detail=True)
        assert detail['failure']['details']['rollback_scope']=='edit_stage'
        upper=next(c for c in detail['state']['components'] if c['ref']=='R1')
        assert next(p for p in upper['pins'] if p['name']=='1')['x']==360
        assert detail['bindings']['upper']['component']['id']==upper['id']
        remaining=divider_plan(tmp_path)['steps'][4:]
        remaining[0]['criteria'][0]['target']=8
        remaining[0]['criteria'][1]['target']=-.004
        adjusted={'id':'adjust','kind':'edit','operations':[{'operation':'setParameter',
            'arguments':{'ref':{'$ref':'lower.component.id'},'role':'value','value':2000}}]}
        result=finish(manager,manager.control(failed['id'],'resume',[adjusted,*remaining]))
        assert result['status']=='complete',result
        assert [c['id'] for c in result['completed']].count('build')==1
        assert result['results']['dc']['passed'] and result['results']['save']['verification']['passed']
    finally:manager.shutdown();host.close()


def test_native_shared_power_alias_survives_netlist_refresh(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
    try:
        ops=[]
        for n,x in enumerate((180,540),1):
            for name,ref,y in [('VCC','P'+str(n),180),('RESISTOR_VIRTUAL','R'+str(n),360),('GROUND','G'+str(n),540)]:
                ops.append({'operation':'place','bind':ref,'arguments':{'name':name,'ref':ref,'x':x,'y':y,'anchor':'pin','pin':'VCC' if name=='VCC' else '1',
                           **({'value':1000} if name=='RESISTOR_VIRTUAL' else {})}})
            for a,b,ap,bp in [('P'+str(n),'R'+str(n),'1','1'),('R'+str(n),'G'+str(n),'2','1')]:
                ops.append({'operation':'wire','arguments':{'source':{'ref':{'$ref':a+'.component.id'},'pin':'VCC' if a.startswith('P') else ap},
                                                          'target':{'ref':{'$ref':b+'.component.id'},'pin':bp}}})
        result=finish(manager,manager.start({'steps':[
            {'id':'start','kind':'session','mode':'create','output_path':str(tmp_path/'initial.ms14')},
            {'id':'wiring','kind':'wiring','connect_touching':False,'autowire_on_move':False,'autowire_on_connection':False},
            {'id':'build','kind':'edit','operations':ops}, {'id':'netlist','kind':'netlist'},
            {'id':'move','kind':'edit','operations':[{'operation':'move','arguments':{'ref':{'$ref':'P2.component.id'},'dx':9,'dy':18}}]},
            {'id':'save','kind':'save','output_path':str(tmp_path/'power.ms14')}]}))
        assert result['status']=='complete',result
        state=host.call('circuitState');assert len([c for c in state['components'] if c['ref']=='VCC'])==2
        detail=manager.status(result['id'],detail=True)
        selected=detail['bindings']['P2']['component']['id']
        links=detail['bindings']['netlist']['state']['wires']
        expected=sum(any(w[e].get('component_id')==selected for e in ('source','target')) for w in links)
        assert detail['bindings']['move']['results'][0]['updated_wires']==expected
        assert next(p for c in state['components'] if c['id']==selected for p in c['pins'] if p['name']=='VCC')['x']==549
        assert detail['bindings']['P1']['component']['id']!=detail['bindings']['P2']['component']['id']
    finally:manager.shutdown();host.close()


def test_native_interactive_workflow_captures_actual_lit_frames(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
    try:
        ops=[]
        for name,ref,x,y in [('DC_POWER','V1',90,90),('GROUND','0',90,585),('SEVEN_SEG_COM_A','DS1',540,270)]:
            ops.append({'operation':'place','arguments':{'name':name,'ref':ref,'x':x,'y':y,
                         **({'value':5} if ref=='V1' else {})}})
        for i in range(7):ops.append({'operation':'place','arguments':{'name':'RESISTOR_VIRTUAL','ref':'R'+str(i+1),'x':300,'y':90+i*63,'value':330}})
        connections=[('V1','1','DS1','COM'),('V1','2','0','1')]+[(a,ap,b,bp) for i,s in enumerate('ABCDEFG') for a,ap,b,bp in [('DS1',s,'R'+str(i+1),'1'),('R'+str(i+1),'2','0','1')]]
        for a,ap,b,bp in connections:ops.append({'operation':'wire','arguments':{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}}})
        result=finish(manager,manager.start({'steps':[
            {'id':'start','kind':'session','mode':'create','output_path':str(tmp_path/'initial.ms14')},
            {'id':'wiring','kind':'wiring','connect_touching':False},
            {'id':'build','kind':'edit','operations':ops},
            {'id':'live','kind':'interactive','time_step':.001,'max_time_step':.001,'real_time':True,
             'captures':[{'output_path':str(tmp_path/f'lit-{n}.png'),'active_component':'DS1','expected_digit':'8'} for n in (1,2)]},
            {'id':'save','kind':'save','output_path':str(tmp_path/'display.ms14')}, {'id':'close','kind':'close'}]}))
        assert result['status']=='complete',result
        assert len(result['results']['live']['frames'])==2
        from PIL import Image
        for n in (1,2):
            with Image.open(tmp_path/f'lit-{n}.png') as image:
                assert sum(r>150 and g<90 and b<90 for r,g,b in image.convert('RGB').get_flattened_data())>100
    finally:manager.shutdown();host.close()


def test_native_resume_after_restart_reuses_failed_acceptance_samples(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
    try:
        plan=divider_plan(tmp_path);plan['steps']=plan['steps'][:3]+[plan['steps'][4]]
        plan['steps'][3]['criteria'][0]['target']=7
        failed=finish(manager,manager.start(plan))
        assert failed['status']=='needs_input',failed
        raw=failed['failure']['details']['raw_path']
        assert failed['next_step']==3
        manager.shutdown();host.close()
        host=EditorService();manager=WorkflowManager(host,tmp_path/'records')
        tail=[{'id':'accept','kind':'verify','raw_path':raw,
               'measurements':[{'id':'current','metric':'mean','signal':'I(V1)'}],
               'criteria':[{'id':'current','target':-.006,'absolute_tolerance':1e-9}]},
              {'id':'save','kind':'save','output_path':str(tmp_path/'resumed.ms14')},
              {'id':'close','kind':'close'}]
        result=finish(manager,manager.control(failed['id'],'resume',tail))
        assert result['status']=='complete',result
        assert result['results']['accept']['passed'] and result['results']['save']['verification']['passed']
        assert [c['id'] for c in result['completed']].count('build')==1
    finally:manager.shutdown();host.close()
