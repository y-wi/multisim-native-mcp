import json,os,shutil
from pathlib import Path
import pytest
import frida
from PIL import Image,ImageChops
from multisim_native_mcp.bridge import sha256
from multisim_native_mcp.paths import RESOURCE_DIR
from multisim_native_mcp.service import EditorService
from multisim_native_mcp import bridge,service

pytestmark=pytest.mark.native


def test_rotated_and_copied_symbols_stay_aligned_with_wire_graphics(tmp_path):
    host=EditorService()
    try:
        host.create('Rotated divider')
        for name,ref,x,y in [('DC_POWER','V1',108,108),('RESISTOR_VIRTUAL','R1',306,108),('RESISTOR_VIRTUAL','R2',504,108),('GROUND','0',108,306)]:
            host.edit('place',{'name':name,'ref':ref,'x':x,'y':y})
        for ref,value in [('V1',12),('R1',1000),('R2',1000)]:host.edit('setParameter',{'ref':ref,'index':1,'value':value})
        for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]:
            host.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        for ref in ['R1','R2']:host.edit('transform',{'ref':ref,'angle':90})
        host.edit('copy',{'ref':'R1','new_ref':'R3','x':600,'y':400})
        assert all(abs(v-round(v))<1e-4 for c in host.call('components')['components'] for v in c['transform'][4:])
        host.edit('remove',{'ref':'R3'})
        host.export_image(str(tmp_path/'before.png'))
        for ref in ['R1','R2']:host.edit('move',{'ref':ref,'dx':0,'dy':0})
        host.export_image(str(tmp_path/'after.png'))
        with Image.open(tmp_path/'before.png') as a,Image.open(tmp_path/'after.png') as b:
            assert ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is None
        result=host.run_analysis()
        assert any(v['name']=='I(V1)' and abs(v['last']+.006)<1e-8 for v in result['vectors'])
        output=tmp_path/'rotated.ms14';host.save_copy(str(output))
        host.close();host.open_copy(str(output))
        for wire in host.call('wires')['wires']:
            for end,index in [('source',0),('target',-1)]:
                assert wire['points'][index]=={k:wire[end][k] for k in ('x','y')}
    finally:host.close()


@pytest.fixture
def different_reference(tmp_path,monkeypatch):
    resources=tmp_path/'reference';resources.mkdir()
    for name in ['host_agent.js','editor_agent.js','startup_agent.js','native-profile.json']:
        shutil.copy2(RESOURCE_DIR/name,resources/name)
    (resources/'assets').mkdir()
    shutil.copy2(RESOURCE_DIR/'assets/blank14.3.ms14',resources/'assets/blank14.3.ms14')
    path=resources/'native-profile.json';profile=json.loads(path.read_text())
    profile['version']='0.0.0';profile['modules']={name:'0'*64 for name in profile['modules']}
    path.write_text(json.dumps(profile),encoding='utf-8')
    monkeypatch.setattr(bridge,'ROOT',resources)
    monkeypatch.setattr(service,'ROOT',resources)


def test_native_edit_save_reload_and_analog_analysis(tmp_path,different_reference):
    host=EditorService()
    try:
        status=host.runtime_status()
        assert status['available'] and not status['compatible']
        host.create('Voltage divider')
        assert not host.call('components')['components']
        assert not host.call('wires')['wires']
        for name,ref,x,y in [('DC_POWER','V1',108,108),('RESISTOR_VIRTUAL','R1',306,108),('RESISTOR_VIRTUAL','R2',504,108),('GROUND','0',108,306)]:
            host.edit('place',{'name':name,'ref':ref,'x':x,'y':y})
        for ref,value in [('V1',12),('R1',1000),('R2',1000)]:host.edit('setParameter',{'ref':ref,'index':1,'value':value})
        for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]:host.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        baseline=host.run_analysis()
        assert any(v['name']=='I(V1)' and abs(v['last']+0.006)<1e-8 for v in baseline['vectors'])
        transient=host.run_analysis('tran',0.0001,0.002)
        assert transient['points']>10
        host.edit('copy',{'ref':'R1','new_ref':'R3','x':600,'y':400})
        original=next(w for w in host.call('wires')['wires'] if {w['source'].get('ref'),w['target'].get('ref')}=={'R1','R2'})
        a,b=original['points'][0],original['points'][-1]
        middle=round((a['x']+b['x'])/18)*9
        host.edit('route',{'id':original['id'],'points':[a,{'x':a['x'],'y':252},{'x':b['x'],'y':252},b]})
        junction=host.edit('splitWire',{'id':original['id'],'x':middle,'y':252})
        host.edit('connectEndpoint',{'source':{'ref':'R3','pin':'1'},'target':{'junction_id':junction['junction_id']}})
        host.edit('move',{'ref':'R3','dx':18,'dy':9})
        def attached():
            pins={p['id']:p for c in host.call('components')['components'] for p in c['pins']}
            wires=host.call('wires')['wires']
            assert len(wires)==6 and all(w['has_pen'] for w in wires)
            for wire in wires:
                for end,index in [('source',0),('target',-1)]:
                    if wire[end]['id'] in pins:
                        pin=pins[wire[end]['id']]
                        assert wire['points'][index]=={'x':pin['x'],'y':pin['y']}
        attached()
        host.history('undo');attached();host.history('redo');attached()
        output=tmp_path/'round trip.ms14';host.save_copy(str(output));digest=sha256(output)
        host.close();host.open_copy(str(output));attached()
        host.export_image(str(tmp_path/'round-trip.png'))
        assert not host.netlist()['failed']
        assert sha256(output)==digest
        report={'baseline':baseline,'transient':transient,'saved':str(output),'passed':True}
        (tmp_path/'native-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:host.close()


def test_attach_preserves_existing_process(tmp_path,different_reference):
    owner=EditorService();client=EditorService()
    try:
        owner.create('Attach test')
        owner.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R1','x':306,'y':108})
        pid=owner.process.pid
        owner.agent.exports_sync.close();owner.agent.unload();owner.session.detach()
        owner.agent=owner.session=None
        connected=client.attach(pid)
        assert Path(connected['backup']).is_file()
        client.edit('move',{'ref':'R1','dx':18,'dy':9})
        client.save_copy(str(tmp_path/'attached.ms14'))
        closed=client.close()
        assert closed['detached'] and not closed['closed']
        assert owner.process.poll() is None
    finally:
        client.close()
        if owner.process and owner.process.poll() is None and owner.agent is None:
            owner.session=frida.attach(owner.process.pid)
            code=(RESOURCE_DIR/'host_agent.js').read_text(encoding='utf-8')+'\n'+(RESOURCE_DIR/'editor_agent.js').read_text(encoding='utf-8')
            owner.agent=owner.session.create_script(code,runtime='v8');owner.agent.load()
        owner.close()
