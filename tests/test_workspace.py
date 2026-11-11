import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from multisim_native_mcp import bridge
from multisim_native_mcp.bridge import NativeHost,sha256
from multisim_native_mcp.cli import client_entry
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.workflow_contracts import WorkflowPlan


def test_client_configuration_has_no_global_circuit_directory():
    assert 'env' not in client_entry()
    from multisim_native_mcp.workflow_contracts import SessionStage
    assert 'workspace_path' not in SessionStage.model_fields


def test_recovery_backup_is_internal_and_has_no_adjacent_backup(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,'DATA_DIR',tmp_path/'internal')
    workspace=tmp_path/'workspace';workspace.mkdir();source=workspace/'circuit.ms14';source.write_bytes(b'original')
    host=EditorService();backup=host.backup_file(source)
    assert backup.parent==host.recovery_folder() and backup.read_bytes()==b'original'
    assert list(workspace.iterdir())==[source]


def test_normal_close_saves_but_failure_keeps_the_session_open():
    host=EditorService();host.agent=True;events=[]
    host.call=lambda *args:{'modified':True}
    host.interactive_status=lambda:{'state_name':'stopped'}
    host.save_current=lambda:events.append('save') or {'path':'source.ms14'}
    host.close=lambda:events.append('close') or {'closed':True}
    result=host.finish();assert events==['save','close'] and result['saved_changes']
    events.clear()
    host.save_current=lambda:(_ for _ in ()).throw(RuntimeError('external conflict'))
    with pytest.raises(RuntimeError):host.finish()
    assert not events
    host.finish(False);assert events==['close']
    host.agent=None


def test_explicit_copy_close_targets_copy_and_preserves_original_identity(tmp_path):
    host=EditorService();host.isolated=True
    host.source=tmp_path/'original.ms14';host.source.write_bytes(b'original');host.source_hash=sha256(host.source)
    host.working=tmp_path/'copy.ms14';host.working.write_bytes(b'copy');host.working_hash=sha256(host.working)
    def save(allow_off_page=False):
        assert host.source==host.working
        host.source.write_bytes(b'edited copy');return {'path':str(host.source)}
    host.save_source=save;result=host.save_current()
    assert result['saved_working_copy'] and not result['saved_to_source']
    assert host.source.name=='original.ms14' and host.source.read_bytes()==b'original'
    assert host.working.read_bytes()==b'edited copy'


def test_source_path_save_does_not_require_an_overwrite_flag(tmp_path):
    host=EditorService();host.source=tmp_path/'circuit.ms14';host.source.write_bytes(b'old');host.working=host.source
    host.save_source=lambda allow_off_page=False:{'saved_to_source':True}
    assert host.save_copy(str(host.source))['saved_to_source']


def test_new_document_has_a_workspace_path_before_native_start(tmp_path,monkeypatch):
    host=EditorService();monkeypatch.chdir(tmp_path)
    def opened(self,path):
        self.source=self.working=Path(path);self.source_hash=sha256(self.source)
        assert self.source.parent==tmp_path and self.source.is_file()
        return {'working_path':str(self.source),'mode':'direct'}
    host.open_circuit=lambda path:opened(host,path)
    host.call=lambda *args:{'components':[],'wires':[]}
    host.edit=lambda *args:{};host.save_source=lambda:{'verification':{'passed':True}}
    assert Path(host.create('New design')['path']).name=='New design.ms14'
    assert Path(host.create('New design')['path']).name=='New design-2.ms14'
    with pytest.raises(FileExistsError):host.create(output_path=str(tmp_path/'New design.ms14'))


def test_normal_workflow_defaults_are_direct_and_save_current():
    plan=WorkflowPlan.model_validate({'steps':[{'id':'open','kind':'session','mode':'open','source_path':'E:/circuit.ms14'},
        {'id':'save','kind':'save'},{'id':'close','kind':'close'}]})
    assert not plan.steps[0].isolated_copy and not plan.steps[1].save_to_source and plan.steps[2].save_changes


def test_numeric_simulation_has_no_fixed_kill_timer(monkeypatch):
    host=NativeHost();host.agent=SimpleNamespace(exports_sync=SimpleNamespace(dispatch=lambda *args:json.dumps({'ok':True})))
    host.process=SimpleNamespace(poll=lambda:None);events=[]
    class Timer:
        def __init__(self,delay,callback):events.append(delay)
        def start(self):pass
        def cancel(self):pass
    monkeypatch.setattr(bridge.threading,'Timer',Timer)
    assert host.call('simulate')['ok'] and not events
    host.call('inspect');assert not events
    host.process=host.agent=None


def test_recovery_rebinds_original_path_hash_and_pending_save(tmp_path,monkeypatch):
    host=EditorService();calls=[]
    def opened(self,path):self.source=self.working=Path(path)
    monkeypatch.setattr(NativeHost,'open_circuit',opened)
    host.call=lambda op,args=None:calls.append((op,args)) or {'modified':True}
    source=tmp_path/'circuit.ms14';source.write_bytes(b'original')
    checkpoint={'path':str(tmp_path/'internal-checkpoint.ms14'),'modified':True}
    context={'source_path':str(source),'working_path':str(source),'source_sha256':sha256(source),
             'isolated':False}
    host.open_recovery(checkpoint,context)
    assert host.source==host.working==source and host.source_hash==sha256(source)
    assert calls[:2]==[('setProjectPath',{'path':str(source)}),('markModified',None)]


def test_default_workflow_save_targets_current_copy_not_original(tmp_path):
    from multisim_native_mcp.workflows import WorkflowManager
    from test_workflows import Host
    host=Host(tmp_path);host.source=tmp_path/'original.ms14';calls=[]
    host.save_current=lambda **kwargs:calls.append('current') or {'saved_working_copy':True}
    host.save_source=lambda **kwargs:(_ for _ in ()).throw(AssertionError('original save'))
    manager=WorkflowManager(host,tmp_path/'records')
    result=manager.start({'steps':[{'id':'save','kind':'save'}]})
    assert result['status']=='complete',result
    assert calls==['current']
