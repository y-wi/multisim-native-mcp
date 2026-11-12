import pytest
from multisim_native_mcp.service import EditorService,NativeEditError
from multisim_native_mcp.workflows import WorkflowManager

pytestmark=pytest.mark.native


def test_free_text_update_delete_history_workflow_and_saved_source(tmp_path):
    host=EditorService();source=tmp_path/'text.ms14'
    def texts():return host.call('circuitState')['texts']
    try:
        host.create('Text',str(source))
        note=host.edit('addText',{'text':'Original','x':180,'y':90})
        assert texts()[0]['id']==note['id']
        host.edit('updateText',{'object_id':note['id'],'text':'中文说明\n第二行','x':270,'y':180})
        updated=texts()[0]
        assert updated['id']==note['id'] and updated['text']=='中文说明\n第二行'
        assert (updated['x'],updated['y'])==(270,180)
        host.edit('updateText',{'id':note['id'],'text':''})
        assert texts()[0]['text']==''
        assert host.save_source()['verification']['passed']
        host.history('undo');assert texts()[0]['text']=='中文说明\n第二行'
        with pytest.raises(NativeEditError):host.batch([
            {'operation':'updateText','arguments':{'id':texts()[0]['id'],'text':'Rolled back'}},
            {'operation':'deleteText','arguments':{'id':'missing'}}])
        assert texts()[0]['text']=='中文说明\n第二行'
        manager=WorkflowManager(host,tmp_path/'records')
        result=manager.start({'steps':[
            {'kind':'edit','id':'add','operations':[{'operation':'addText','arguments':{'text':'Temporary','x':90,'y':270},'bind':'note'}]},
            {'kind':'edit','id':'revise','operations':[{'operation':'updateText','arguments':{'id':{'$ref':'note.id'},'text':'Changed','x':180}}]},
            {'kind':'edit','id':'remove','operations':[{'operation':'deleteText','arguments':{'id':{'$ref':'note.id'}}}]},
        ]})
        assert result['status']=='complete',result
        assert len(texts())==1
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source));assert texts()[0]['text']=='中文说明\n第二行'
        host.edit('deleteText',{'id':texts()[0]['id']});assert not texts()
        host.history('undo');assert len(texts())==1
        host.history('redo');assert not texts()
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source));assert not texts()
    finally:host.close()


def test_hierarchical_port_rename_preserves_child_and_parent_connections(tmp_path):
    host=EditorService();source=tmp_path/'hierarchy.ms14'
    def comps():return host.call('components')['components']
    try:
        host.create('Hierarchy',str(source))
        host.edit('createSubcircuit',{'title':'Child','ref':'X1','x':360,'y':180})
        host.call('selectSheet',{'index':1})
        port=host.edit('createPort',{'name':'IN','x':180,'y':180})
        host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R1','x':450,'y':180})
        host.edit('connectEndpoint',{'source':{'ref':'IN','pin':comps()[0]['pins'][0]['name']},'target':{'ref':'R1','pin':'1'}})
        host.call('selectSheet',{'index':0})
        host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R2','x':630,'y':360})
        pin=next(c for c in comps() if c['ref']=='X1')['pins'][0]['name']
        host.edit('connectEndpoint',{'source':{'ref':'X1','pin':pin},'target':{'ref':'R2','pin':'1'}})
        assert host.save_source()['verification']['passed']
        host.call('selectSheet',{'index':1})
        port=next(c for c in comps() if c['local_ref']=='IN')
        host.edit('updatePort',{'id':port['id'],'name':'INPUT','x':270,'y':270})
        assert next(c for c in comps() if c['id']==port['id'])['local_ref']=='INPUT'
        assert len(host.call('wires')['wires'])==1
        assert host.save_source()['verification']['passed']
        host.edit('updateSheet',{'title':'Amplifier','page':'Child A','width':1200,'height':900})
        sheet=host.call('sheets')[1];assert sheet['title']=='Amplifier' and sheet['page']=='Child A' and sheet['width']==1200
        host.call('selectSheet',{'index':0})
        parent=next(c for c in comps() if c['ref']=='X1')
        assert [p['name'] for p in parent['pins']]==['INPUT']
        assert len(host.call('wires')['wires'])==1
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source))
        assert [p['name'] for c in comps() if c['ref']=='X1' for p in c['pins']]==['INPUT']
        host.call('selectSheet',{'index':1});assert host.call('sheets')[1]['page']=='Child A' and host.call('sheets')[1]['title']=='Amplifier'
    finally:host.close()


def test_branch_junction_moves_without_changing_attachments(tmp_path):
    host=EditorService();source=tmp_path/'junction.ms14'
    try:
        host.create('Branch',str(source))
        for ref,x,y in [('R1',180,180),('R2',630,180),('R3',360,450)]:host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':ref,'x':x,'y':y})
        link=host.edit('connectEndpoint',{'source':{'ref':'R1','pin':'2'},'target':{'ref':'R2','pin':'1'}})
        wire=host.call('wires')['wires'][0];a,b=next((a,b) for a,b in zip(wire['points'],wire['points'][1:]) if a['y']==b['y'] and abs(a['x']-b['x'])>=36)
        x=round((a['x']+b['x'])/18)*9;y=a['y']
        junction=host.edit('splitWire',{'id':wire['id'],'x':x,'y':y})['junction_id']
        host.edit('connectEndpoint',{'source':{'junction_id':junction},'target':{'ref':'R3','pin':'1'}})
        before=host.call('wires')['wires'];result=host.edit('moveJunction',{'id':junction,'x':x+54,'y':y+54})
        assert result['updated_wires']==3 and result['after']['x']==x+54 and result['after']['y']==y+54
        assert {(w['id'],w['source']['id'],w['target']['id']) for w in before}=={(w['id'],w['source']['id'],w['target']['id']) for w in host.call('wires')['wires']}
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source));assert len(host.call('wires')['wires'])==3
    finally:host.close()
