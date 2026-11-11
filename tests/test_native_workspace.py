from pathlib import Path

import pytest

from multisim_native_mcp.service import EditorService
from multisim_native_mcp.workflows import WorkflowManager

pytestmark=pytest.mark.native


def test_workspace_create_edit_close_save_and_direct_reopen(tmp_path):
    host=EditorService();path=tmp_path/'新电路.ms14'
    try:
        result=host.create('工作区电路',output_path=str(path))
        assert result['mode']=='direct' and result['working_copy'] is None
        assert Path(result['projectPath'])==host.working==host.source==path
        assert path.is_file() and host.folder()!=tmp_path
        host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R1','x':180,'y':180,'parameters':[{'index':1,'value':2200}]})
        checkpoint=host.checkpoint()
        assert Path(checkpoint['path']).parent==host.folder()
        closed=host.finish()
        assert closed['saved_changes'] and Path(closed['save']['backup']).parent!=tmp_path
        assert sorted(p.name for p in tmp_path.iterdir())==['新电路.ms14']
        opened=host.open_circuit(str(path));assert opened['working_path']==str(path) and opened['mode']=='direct'
        assert host.call('inspect')['projectPath']==str(path)
        assert next(p['value'] for p in host.call('parameters',{'ref':'R1'})['parameters'] if p['index']==1)==2200
        host.edit('setParameter',{'ref':'R1','index':1,'value':3300})
        same_path=host.save_copy(str(path))
        assert same_path['saved_to_source'] and same_path['verification']['passed']
    finally:host.close()


def test_workspace_filename_collisions_and_attach_matching_open_source(tmp_path):
    owner=EditorService();client=EditorService()
    try:
        owner.create('Circuit');path=owner.source;owner.finish()
        created=owner.create('Circuit')
        assert Path(created['path']).name=='Circuit-2.ms14'
        owner.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R1','x':180,'y':180})
        pid=owner.process.pid
        # Model a user's ordinary open window, with no second MCP timer agent.
        owner.agent.exports_sync.close();owner.agent.unload();owner.session.detach();owner.agent=owner.session=None
        attached=client.open_circuit(created['path'])
        assert attached['attached_existing'] and not attached['owned']
        client.edit('setParameter',{'ref':'R1','index':1,'value':4700})
        result=client.finish();assert result['saved_changes'] and result['detached']
        assert owner.process.poll() is None and owner.process.pid==pid
        client.attach(pid)
        assert next(p['value'] for p in client.call('parameters',{'ref':'R1'})['parameters'] if p['index']==1)==4700
        client.finish(False)
        third=client.create('Third circuit')
        assert third['attached_existing'] and Path(third['path']).name=='Third circuit.ms14'
        assert owner.process.poll() is None
        assert path.is_file()
    finally:client.close();owner.close()


def test_default_workflow_open_create_save_and_close_use_workspace_sources(tmp_path):
    host=EditorService();manager=WorkflowManager(host,tmp_path/'records');path=tmp_path/'workflow.ms14'
    try:
        result=manager.start({'steps':[
            {'id':'new','kind':'session','mode':'create','title':'Workspace workflow','output_path':str(path)},
            {'id':'place','kind':'edit','operations':[{'operation':'place','arguments':{'name':'RESISTOR_VIRTUAL','ref':'R1','x':180,'y':180,'value':1200}}]},
            {'id':'save','kind':'save'}, {'id':'close','kind':'close'}]})
        while result['status']=='running':result=manager.status(result['id'],30)
        assert result['status']=='complete',result
        assert result['results']['save']['path']==str(path) and result['results']['save']['saved_to_source']
        result=manager.start({'steps':[
            {'id':'open','kind':'session','mode':'open','source_path':str(path)},
            {'id':'value','kind':'edit','operations':[{'operation':'setParameter','arguments':{'ref':'R1','index':1,'value':5600}}]},
            {'id':'close','kind':'close'}]})
        while result['status']=='running':result=manager.status(result['id'],30)
        assert result['status']=='complete',result
        host.open_circuit(str(path))
        assert next(p['value'] for p in host.call('parameters',{'ref':'R1'})['parameters'] if p['index']==1)==5600
    finally:manager.shutdown();host.close()
