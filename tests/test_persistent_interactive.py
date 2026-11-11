from pathlib import Path

import pytest

from multisim_native_mcp.bridge import sha256
from multisim_native_mcp.service import EditorService


@pytest.mark.parametrize('options',[
    {'persist':1},{'save_to_source':1},{'save_to_source':True},
    {'persist':True,'reset':True,'real_time':False},
])
def test_persistent_validation_precedes_native_calls(options):
    host=EditorService();host.call=lambda *args:pytest.fail('Native call reached')
    with pytest.raises(ValueError):host.configure_interactive(**options)


def persistent_host():
    host=EditorService();calls=[];configuration={'time_step':None,'max_time_step':None,'real_time':True}
    def call(op,args=None):
        calls.append((op,args))
        if op=='interactiveStatus':return {'state_name':'stopped'}
        if op=='documentInteractiveOptions':
            if args:configuration.update(args['configuration'])
            return {'configuration':dict(configuration),'changed':bool(args)}
        if op in ('markModified','interactiveOptions'):return {}
        raise AssertionError(op)
    host.call=call
    host.checkpoint=lambda: {'path':'checkpoint'}
    host.restore=lambda checkpoint:calls.append(('restore',checkpoint))
    return host,calls


def test_document_read_is_side_effect_free_and_mutation_clears_temporary_override():
    host,calls=persistent_host()
    assert host.configure_interactive(persist=True)['saved_to_file'] is False
    assert [op for op,_ in calls]==['documentInteractiveOptions']
    calls.clear()
    result=host.configure_interactive(time_step=.001,persist=True)
    assert result['configuration']['time_step']==.001 and not result['saved_to_file']
    assert calls[-1]==('interactiveOptions',{'reset':True})
    assert host.undo_stack==[{'path':'checkpoint'}]


def test_bad_native_readback_rolls_back_before_source_save():
    host,calls=persistent_host();original=host.call
    def call(op,args=None):
        result=original(op,args)
        if op=='documentInteractiveOptions':result['configuration']['time_step']=.1
        return result
    host.call=call
    host._save_source=lambda:pytest.fail('Invalid configuration reached source save')
    with pytest.raises(RuntimeError,match='readback'):
        host.configure_interactive(time_step=.001,persist=True,save_to_source=True)
    assert calls[-1]==('restore',{'path':'checkpoint'}) and not host.undo_stack


def source_host(tmp_path):
    host=EditorService();host.source=tmp_path/'source.ms14';host.source.write_bytes(b'original')
    host.source_hash=sha256(host.source);host.working=tmp_path/'working.ms14'
    paths=[]
    def call(op,args=None):
        if op=='inspect':return {'projectPath':str(host.working)}
        assert op=='setProjectPath';paths.append(args['path']);return True
    host.call=call
    def save(output_path,verify):
        assert verify is True
        Path(output_path).write_bytes(b'verified native output')
        return {'path':output_path,'verification':{'passed':True},'backup':None}
    host.save_copy=save
    return host,paths


def test_explicit_source_save_backs_up_original_and_updates_hash(tmp_path):
    host,paths=source_host(tmp_path)
    result=host._save_source()
    assert host.source.read_bytes()==b'verified native output'
    assert Path(result['backup']).read_bytes()==b'original'
    assert result['saved_to_source'] and result['sha256']==host.source_hash==sha256(host.source)
    assert paths==[str(host.source)] and not list(tmp_path.glob('save-source-*'))


@pytest.mark.parametrize('during_save',[False,True])
def test_external_source_changes_are_never_overwritten(tmp_path,during_save):
    host,paths=source_host(tmp_path)
    if during_save:
        original=host.save_copy
        def save(*args,**kwargs):
            result=original(*args,**kwargs);host.source.write_bytes(b'external edit');return result
        host.save_copy=save
    else:host.source.write_bytes(b'external edit')
    with pytest.raises(RuntimeError,match='Source changed'):host._save_source()
    assert host.source.read_bytes()==b'external edit'
    assert not list(tmp_path.glob('*.bak')) and not list(tmp_path.glob('save-source-*'))


def test_failed_native_save_or_path_update_preserves_source(tmp_path):
    host,paths=source_host(tmp_path)
    host.save_copy=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('verify failed'))
    with pytest.raises(RuntimeError,match='verify failed'):host._save_source()
    assert host.source.read_bytes()==b'original'
    host,paths=source_host(tmp_path);original=host.call
    host.call=lambda op,args=None:False if op=='setProjectPath' and args['path']==str(host.source) else original(op,args)
    with pytest.raises(RuntimeError,match='document path'):host._save_source()
    assert host.source.read_bytes()==b'original' and sha256(host.source)==host.source_hash
