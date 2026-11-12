import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from multisim_native_mcp import bridge
from multisim_native_mcp.bridge import sha256
from multisim_native_mcp.save_differences import saved_differences,difference_summary
from multisim_native_mcp.service import EditorService,NativeSaveError
from test_save_export import saving_host,scene


def test_save_difference_identifies_the_missing_annotation_without_list_index_noise():
    note={'text':'Output','transform':[1,0,0,1,200,100]}
    title={'text':'Divider','transform':[1,0,0,1,100,50]}
    differences=saved_differences([{'annotations':[note,title]}],[{'annotations':[title]}])
    assert differences==[{'path':'sheets[0].annotations','kind':'missing','expected':note}]
    assert "missing 'Output' at (200, 100)" in difference_summary(differences)


def test_verified_save_reports_structured_missing_annotation(tmp_path):
    state=scene();state['annotations']=[{'text':'Output','transform':[1,0,0,1,200,100]}]
    host,calls=saving_host(tmp_path,[state]);original=host.call
    def call(op,args=None):
        result=original(op,args)
        if op=='verifySavedCopy':result['states'][0]['annotations']=[]
        return result
    host.call=call
    with pytest.raises(NativeSaveError,match="missing 'Output'") as error:host.save_copy(str(tmp_path/'circuit.ms14'))
    assert error.value.details['differences'][0]['expected']['text']=='Output'
    assert Path(error.value.details['diagnostic_path']).is_file()


def test_same_path_verify_false_saves_with_backup_without_reopening(tmp_path):
    host,calls=saving_host(tmp_path,[scene()]);source=tmp_path/'source.ms14';source.write_bytes(b'original')
    host.source=host.working=source;host.source_hash=sha256(source)
    result=host.save_copy(str(source),verify=False)
    assert result['saved_to_source'] and result['verification']['skipped']
    assert Path(result['backup']).read_bytes()==b'original' and 'verifySavedCopy' not in calls


def test_persistent_wire_names_are_part_of_save_verification():
    state=scene();state['wire_labels']=[{'name':'Output','hidden':False,'source':{'ref':'R1'},'target':{'ref':'R2'}}]
    after=copy.deepcopy(state);after['wire_labels'][0]['name']='Changed'
    assert EditorService.saved_signature([state])!=EditorService.saved_signature([after])


@pytest.mark.parametrize('args,expected',[
    ({'object_id':'wire'},{'id':'wire'}),({'component_ref':'R1'},{'ref':'R1'}),({'id':'wire'},{'id':'wire'}),
])
def test_batch_delete_accepts_the_standalone_tool_selectors(args,expected):
    assert EditorService.normalize_edit({'operation':'remove','arguments':args})['arguments']==expected


@pytest.mark.parametrize('args',[{}, {'id':'a','object_id':'b'},{'ref':'R1','id':'wire'}])
def test_ambiguous_delete_is_rejected_before_native_changes(args):
    with pytest.raises(ValueError):EditorService.normalize_edit({'operation':'remove','arguments':args})


def test_runtime_distinguishes_running_application_from_attached_session(monkeypatch):
    monkeypatch.setattr(bridge.frida,'get_local_device',lambda:SimpleNamespace(enumerate_processes=lambda:[SimpleNamespace(pid=42,name='Multisim.exe')]))
    result=EditorService().runtime_status()
    assert result['running'] and result['pid']==42 and not result['session_attached']
    assert result['processes']==[{'pid':42,'name':'Multisim.exe'}]


def test_list_projects_attaches_a_single_existing_process(monkeypatch):
    host=EditorService();events=[]
    monkeypatch.setattr(bridge.frida,'get_local_device',lambda:SimpleNamespace(enumerate_processes=lambda:[SimpleNamespace(pid=42,name='Multisim.exe')]))
    host.attach=lambda pid:events.append(pid)
    host.call=lambda op:{'projects':[{'path':'circuit.ms14'}]}
    assert host.list_projects()['projects'][0]['path']=='circuit.ms14' and events==[42]


def test_duplicate_annotations_are_counted_in_save_differences():
    note={'text':'Output','transform':[1,0,0,1,200,100]}
    differences=saved_differences([{'annotations':[note,note]}],[{'annotations':[note]}])
    assert len(differences)==1 and differences[0]['kind']=='missing'
