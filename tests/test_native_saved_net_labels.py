import pytest
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.workflows import WorkflowManager

pytestmark=pytest.mark.native


def test_manual_wire_labels_save_reopen_delete_and_undo(tmp_path):
    host=EditorService();source=tmp_path/'labels.ms14'
    def labels():return host.call('projectCircuitState',{'include_persistence':True})['states'][0]['wire_labels']
    try:
        host.create('Named wire',str(source))
        manager=WorkflowManager(host,tmp_path/'records')
        prepared=manager.prepare([{'name':'RESISTOR_VIRTUAL'}])['components'][0]
        assert prepared['anchor']=='center' and 'placement.actual' in prepared['pin_offsets_relative_to']
        for name,ref,x in [('RESISTOR_VIRTUAL','R1',180),('RESISTOR_VIRTUAL','R2',540)]:
            placed=host.edit('place',{'name':name,'ref':ref,'x':x,'y':270,'anchor':'center','parameters':[{'index':1,'value':1000}]})
            assert prepared['pins']==placed['placement']['pin_offsets']
        host.edit('connectEndpoint',{'source':{'ref':'R1','pin':'2'},'target':{'ref':'R2','pin':'1'}})
        host.netlist();wire=host.call('wires')['wires'][0]
        label=host.edit('labelWire',{'id':wire['id'],'name':'OUTPUT'})
        host.edit('addText',{'text':'Named output','x':180,'y':100})
        assert labels()[0]['name']=='OUTPUT'
        assert host.save_source()['verification']['passed']
        host.close();host.open_circuit(str(source))
        assert labels()[0]['name']=='OUTPUT' and 'OUTPUT' in host.netlist()['content']
        wire=host.call('wires')['wires'][0];label=host.edit('labelWire',{'id':wire['id'],'name':'OUTPUT'})
        deleted=host.edit('remove',{'object_id':label['label']})
        assert deleted['deleted'] and deleted['generated_net_label'] and not labels()
        host.history('undo');assert labels()[0]['name']=='OUTPUT'
        wire=host.call('wires')['wires'][0]
        assert host.edit('remove',{'object_id':wire['id']})['deleted']
        assert not host.call('wires')['wires']
        host.history('undo');assert len(host.call('wires')['wires'])==1
        assert host.save_copy(str(source),verify=False)['verification']['skipped']
    finally:host.close()
