import pytest
from PIL import Image, ImageChops

from multisim_native_mcp.layout import check_layout
from multisim_native_mcp.bridge import editor_script
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_legacy_grid_graphics_repair_history_and_round_trip(tmp_path):
    h=EditorService()
    try:
        h.create('Connector geometry')
        for name,ref,x,y in [('DC_POWER','V1',108,108),('CAPACITOR_VIRTUAL','C1',360,108),('GROUND','0',108,306)]:
            h.edit('place',{'name':name,'ref':ref,'x':x,'y':y,'anchor':'pin','pin':'1'})
        for a,ap,b,bp in [('V1','1','C1','1'),('C1','2','0','1'),('V1','2','0','1')]:
            h.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        wire=next(w for w in h.call('wires')['wires'] if {w['source'].get('ref'),w['target'].get('ref')}=={'V1','0'})
        a,b=wire['points'][0],wire['points'][-1]
        assert a['x']==b['x']
        junction=h.edit('splitWire',{'id':wire['id'],'x':a['x'],'y':round((a['y']+b['y'])/18)*9})
        # Reproduce an imported layout whose graphic transform predates grid snapping.
        extra=r'''
editorHandlers.legacyGeometry=args=>{
 const graphic=id=>method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(ptr(id));
 for(const id of [component('C1').id,args.junction])method('Od101dll.dll','?Translate@CODGraphic@@','void',['pointer','float','float'])(graphic(id),2,3);
 return true;
};
editorHandlers.largeState=()=>({wires:Array.from({length:1500},(_,i)=>({id:String(i),source:{id:'a',position:{x:i,y:0}},target:{id:'b',position:{x:i,y:9}},points:[{x:i,y:0},{x:i,y:9}]}))});
'''
        h.agent.exports_sync.close();h.agent.unload()
        code=editor_script()+'\n'+extra
        h.agent=h.session.create_script(code,runtime='v8');h.agent.on('message',h._message);h.agent.load()
        h.call('legacyGeometry',{'junction':junction['junction_id']})
        def state():return h.call('circuitState')
        def errors(s):return check_layout(s['components'],s['wires'])['errors']
        before=state();assert errors(before)>0
        repaired=h.edit('repairWireGeometry')
        assert repaired['electrical_connections_unchanged']
        assert repaired['aligned_components']==['C1'] and repaired['aligned_junctions']==[junction['junction_id']]
        after=state();assert errors(after)==0
        assert [(w['id'],w['source']['id'],w['target']['id']) for w in before['wires']]==[(w['id'],w['source']['id'],w['target']['id']) for w in after['wires']]
        h.history('undo');assert errors(state())>0
        h.history('redo');assert errors(state())==0
        assert not h.netlist()['failed']
        for _ in range(5):
            result=h.call('largeState')
            assert len(result['wires'])==1500 and result['wires'][-1]['target']['position']=={'x':1499,'y':9}
        saved=tmp_path/'aligned.ms14';h.save_copy(str(saved));h.close();h.open_copy(str(saved))
        assert errors(state())==0
        h.export_image(str(tmp_path/'before.png'))
        h.edit('move',{'ref':'C1','dx':0,'dy':0})
        h.export_image(str(tmp_path/'after.png'))
        with Image.open(tmp_path/'before.png') as a,Image.open(tmp_path/'after.png') as b:
            assert ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is None
    finally:h.close()
