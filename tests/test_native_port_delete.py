import pytest
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


@pytest.mark.parametrize('keep_output',[False,True])
def test_connected_hierarchical_port_delete_saves_and_undoes(tmp_path,keep_output):
    host=EditorService();source=tmp_path/'ports.ms14'
    port_name='IN'
    def state(index):
        host.call('selectSheet',{'index':index})
        return host.call('circuitState')
    def check(deleted):
        child=state(1);parent=state(0)
        assert (port_name not in [c['local_ref'] for c in child['components']]) is deleted
        block=next(c for c in parent['components'] if c['ref']=='X1')
        assert {p['name'] for p in block['pins']}==({'OUT'} if keep_output else set())| (set() if deleted else {port_name})
        expected=int(keep_output)+int(not deleted)
        assert len(parent['wires'])==len(child['wires'])==expected
        return child,parent
    try:
        host.create('Port delete',str(source))
        host.edit('createSubcircuit',{'title':'Child','ref':'X1','x':360,'y':180})
        host.call('selectSheet',{'index':1})
        names=['IN','OUT'] if keep_output else ['IN']
        for n,name in enumerate(names):
            host.edit('createPort',{'name':name,'x':90,'y':180+180*n})
            host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R'+str(n+1),'x':360,'y':180+180*n,'parameters':[{'index':1,'value':1000}]})
            port=next(c for c in host.call('components')['components'] if c['local_ref']==name)
            host.edit('connectEndpoint',{'source':{'ref':name,'pin':port['pins'][0]['name']},'target':{'ref':'R'+str(n+1),'pin':'1'}})
        host.call('selectSheet',{'index':0})
        for n,name in enumerate(names):
            host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R'+str(n+10),'x':630,'y':180+180*n,'parameters':[{'index':1,'value':1000}]})
            host.edit('connectEndpoint',{'source':{'ref':'X1','pin':name},'target':{'ref':'R'+str(n+10),'pin':'1'}})
        check(False);assert host.save_source()['verification']['passed']
        host.call('selectSheet',{'index':1})
        if keep_output:
            port=next(c for c in host.call('components')['components'] if c['local_ref']=='IN')
            host.edit('updatePort',{'object_id':port['id'],'name':'INPUT','x':180,'y':180})
            host.edit('updateSheet',{'title':'Amplifier','page':'B'})
            port_name='INPUT';assert host.save_source()['verification']['passed']
        deleted=host.edit('native_delete_object',{'component_ref':port_name})
        assert deleted['deleted'] and deleted['hierarchical_port'] and deleted['node_info_updated']
        check(True);assert host.save_source()['verification']['passed']
        host.history('undo');check(False)
        host.history('redo');check(True)
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source));check(True)
        assert host.source==source.resolve()
    finally:host.close()
