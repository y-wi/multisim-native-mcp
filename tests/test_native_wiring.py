import pytest

from multisim_native_mcp.layout import intersects
from multisim_native_mcp.service import EditorService,NativeEditError

pytestmark=pytest.mark.native


def pin(host,ref,name):
    return next(p for c in host.call('components')['components'] if c['ref']==ref for p in c['pins'] if p['name']==name)


def attached(host):
    for wire in host.call('wires')['wires']:
        assert wire['has_pen']
        for end,index in [('source',0),('target',-1)]:
            assert wire['points'][index]=={k:wire[end][k] for k in ('x','y')}
            assert wire[end]['graphics_aligned']


def test_native_autowire_moves_touching_and_saved_branches(tmp_path):
    h=EditorService()
    try:
        h.create('Native autowiring')
        original=h.call('wiringOptions')
        h.call('wiringOptions',{'autowire_on_connection':True,'autowire_on_move':True,'connect_touching':False,'move_connection_limit':12})
        placed=h.batch([{'operation':'place','arguments':{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic',
                  'ref':ref,'x':x,'y':270,'anchor':'center','parameters':[{'index':1,'value':1000}]}}
                 for ref,x in [('R1',180),('R2',720),('R3',450)]])
        wire=h.edit('wire',{'source':{'ref':'R1','pin':'2'},'target':{'ref':'R2','pin':'1'}})
        assert wire['routing_engine']=='multisim-native'
        obstacle=placed['results'][2]['placement']['body_bounds']
        assert not any(intersects(a,b,obstacle) for a,b in zip(wire['points'],wire['points'][1:]))
        moved=h.edit('move',{'ref':'R1','dx':0,'dy':90})
        assert moved['routing_engine']=='multisim-native'
        attached(h)
        before=h.call('wires')['wires'][0]
        labelled=h.edit('labelWire',{'id':before['id'],'name':'SIGNAL'})
        a,b=before['points'][0],before['points'][-1]
        h.edit('route',{'id':before['id'],'points':[a,{'x':a['x'],'y':630},{'x':b['x'],'y':630},b]})
        rerouted=h.edit('autoWire',{'id':before['id']})
        assert rerouted['wire']['id']==before['id'] and rerouted['preserved_wire_id']
        assert rerouted['label']=={'id':labelled['label'],'text':'SIGNAL','hidden':False,'user_named':True}
        assert next(w for w in h.call('connectivity')['wires'] if w['id']==before['id'])['name']==labelled['name']
        assert h.edit('autoWire',{'id':before['id']})['points']==rerouted['points']
        assert max(p['y'] for p in rerouted['wire']['points'])<630
        h.call('wiringOptions',{'connect_touching':True})
        # Place directly on an existing pin; the native drop creates a real connection.
        p=pin(h,'R3','2')
        h.edit('place',{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','ref':'R4',
                        'x':p['x'],'y':p['y'],'anchor':'pin','pin':'1'})
        assert pin(h,'R4','1')['connections']>0
        # A pin touching the middle of a wire becomes a native, editable branch junction.
        h.call('wiringOptions',{'connect_touching':False})
        h.edit('place',{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','ref':'R5','x':450,'y':450,'anchor':'center'})
        h.edit('transform',{'ref':'R5','angle':90})
        wire=next(w for w in h.call('wires')['wires'] if w['source'].get('ref')=='R1')
        p=pin(h,'R5','1');target={'x':450,'y':360}
        # Set a known horizontal segment to exercise interior contact independently of route choice.
        a,b=wire['points'][0],wire['points'][-1]
        h.edit('route',{'id':wire['id'],'points':[a,{'x':b['x'],'y':a['y']},b]})
        h.call('wiringOptions',{'connect_touching':True})
        result=h.edit('move',{'ref':'R5','dx':target['x']-p['x'],'dy':target['y']-p['y']})
        assert result['topology_changed'] and pin(h,'R5','1')['connections']>0
        assert result['touching']['added_wire_ids']
        attached(h)
        h.save_copy(str(tmp_path/'native-wiring.ms14'))
        h.call('wiringOptions',{'reset':True})
        assert h.call('wiringOptions')==original
    finally:h.close()


def test_disabled_autowiring_and_off_page_failure_preserve_connections(tmp_path):
    h=EditorService()
    try:
        h.create('Wiring settings')
        original=h.call('wiringOptions')
        h.call('wiringOptions',{'autowire_on_connection':False,'autowire_on_move':False,'connect_touching':False})
        for ref,x in [('R1',180),('R2',720)]:
            h.edit('place',{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','ref':ref,'x':x,'y':270,'anchor':'center'})
        wire=h.edit('wire',{'source':{'ref':'R1','pin':'2'},'target':{'ref':'R2','pin':'1'}})
        assert wire['routing_engine']=='orthogonal'
        result=h.edit('move',{'ref':'R1','dx':0,'dy':90})
        assert result['routing_engine']=='preserve'
        attached(h)
        h.call('wiringOptions',{'autowire_on_move':True,'move_connection_limit':1})
        assert h.edit('move',{'ref':'R1','dx':0,'dy':9})['routing_engine']=='preserve'
        h.call('wiringOptions',{'autowire_on_connection':True})
        h.edit('place',{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','ref':'R3','x':1800,'y':270})
        with pytest.raises(NativeEditError,match='inside the sheet'):
            h.edit('wire',{'source':{'ref':'R2','pin':'2'},'target':{'ref':'R3','pin':'1'}})
        assert len(h.call('wires')['wires'])==1
        attached(h)
        h.close();h.create('Restored wiring settings')
        assert h.call('wiringOptions')==original
    finally:h.close()


def test_touching_crossing_of_different_nets_rolls_back(tmp_path):
    h=EditorService()
    try:
        h.create('Crossing contacts')
        h.call('wiringOptions',{'connect_touching':False,'autowire_on_move':False})
        for ref,x,y in [('R1',108,180),('R2',792,180),('R3',450,90),('R4',450,630),('R5',450,450)]:
            h.edit('place',{'name':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','ref':ref,'x':x,'y':y,'anchor':'pin','pin':'1'})
        h.edit('transform',{'ref':'R5','angle':90})
        p=pin(h,'R5','1');h.edit('move',{'ref':'R5','dx':450-p['x'],'dy':360-p['y']})
        for a,b,points in [('R1','R2',[{'x':108,'y':180},{'x':108,'y':360},{'x':792,'y':360},{'x':792,'y':180}]),
                           ('R3','R4',[{'x':450,'y':90},{'x':450,'y':630}])]:
            h.edit('connectEndpoint',{'source':{'ref':a,'pin':'1'},'target':{'ref':b,'pin':'1'},'points':points})
        with pytest.raises(NativeEditError,match='crossing of different nets') as error:
            h.edit('connectTouching',{'refs':['R5']})
        assert error.value.details['rollback_scope']=='batch'
        assert len(h.call('wires')['wires'])==2 and pin(h,'R5','1')['connections']==0
        attached(h)
    finally:h.close()
