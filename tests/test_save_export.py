import copy
from pathlib import Path

import pytest
from PIL import Image

from multisim_native_mcp.bridge import NativeHost
from multisim_native_mcp.service import EditorService


def test_attached_save_can_overwrite_when_working_path_does_not_exist(tmp_path):
    host=NativeHost();host.working=tmp_path/'attached-session.ms14'
    host.source=tmp_path/'original.ms14';host.source.write_bytes(b'original')
    from multisim_native_mcp.bridge import sha256
    host.source_hash=sha256(host.source)
    output=tmp_path/'output.ms14';output.write_bytes(b'previous output')
    def call(op,args=None):
        if op=='inspect':return {'projectPath':str(host.source)}
        if op=='setProjectPath':return True
        assert op=='save';Path(args['path']).write_bytes(b'native output'*10)
        return {'nativeResult':1,'errorCode':0,'path':args['path']}
    host.call=call
    result=host.save_copy(str(output),True)
    assert Path(result['backup']).read_bytes()==b'previous output'
    assert result['source_unchanged'] and not host.working.exists()
    with pytest.raises(ValueError,match='protected'):host.save_copy(str(host.source),True)
    alias=tmp_path/'alias.ms14';alias.hardlink_to(host.source)
    with pytest.raises(ValueError,match='protected'):host.save_copy(str(alias),True)


def scene(index=0):
    return {'sheet_index':index,'sheets':[{'title':'A'},{'title':'B'}],
            'page':{'width':960,'height':720,'bounds':{'left':0,'top':0,'right':960,'bottom':720}},
            'content_bounds':{'left':90,'top':90,'right':400,'bottom':300},'components':[],'wires':[]}


def saving_host(tmp_path,states):
    host=EditorService();host.working=tmp_path/'working.ms14';calls=[]
    def call(op,args=None):
        calls.append(op)
        if op=='inspect':return {'projectPath':str(host.working)}
        if op=='setProjectPath':return True
        if op=='simulationInfo':return {'state':0}
        if op=='synchronizeGraphics':return {}
        if op=='simulationSettingsText':return 'native simulation settings'
        if op in ('projectCircuitState','verifySavedCopy'):return {'states':copy.deepcopy(states),'simulation_settings':'native simulation settings'}
        if op=='save':
            Path(args['path']).write_bytes(b'Native circuit file'*4)
            return {'nativeResult':1,'errorCode':0,'path':args['path']}
        raise AssertionError(op)
    host.call=call
    return host,calls


def test_save_checks_every_sheet_without_blocking_off_page_content(tmp_path):
    states=[scene(),scene(1)];states[1]['content_bounds']['right']=1200
    host,calls=saving_host(tmp_path,states)
    output=tmp_path/'output.ms14';output.write_bytes(b'previous')
    result=host.save_copy(str(output),True)
    assert not result['page_check']['passed'] and result['verification']['passed']
    assert result['verification']['sheets']==2 and not list(tmp_path.glob('verify-*.ms14'))


def test_failed_readback_restores_existing_output(tmp_path):
    host,calls=saving_host(tmp_path,[scene()]);original=host.call
    def call(op,args=None):
        result=original(op,args)
        if op=='verifySavedCopy':result['states'][0]['page']['width']=100
        return result
    host.call=call;output=tmp_path/'output.ms14';output.write_bytes(b'previous')
    with pytest.raises(RuntimeError,match='differs after native reopen'):host.save_copy(str(output),True)
    assert output.read_bytes()==b'previous' and not list(tmp_path.glob('verify-*.ms14'))


def test_simulation_settings_readback_failure_restores_output(tmp_path):
    host,calls=saving_host(tmp_path,[scene()]);original=host.call
    def call(op,args=None):
        result=original(op,args)
        if op=='verifySavedCopy':result['simulation_settings']='lost settings'
        return result
    host.call=call;output=tmp_path/'output.ms14';output.write_bytes(b'previous')
    with pytest.raises(RuntimeError,match='simulation settings differ'):host.save_copy(str(output),True)
    assert output.read_bytes()==b'previous'


@pytest.mark.parametrize('field',['model_text','annotations','sheet_display','page_name'])
def test_saved_signature_detects_other_persistence_gaps(field):
    expected=scene();expected['sheets'][0]['page']='Saved page'
    expected['components']=[{'ref':'D1','transform':[1,0,0,1,100,100],'pins':[],'model_text':'.model D custom'}]
    expected.update(annotations=[{'text':'Saved note','transform':[1,0,0,1,90,90]}],sheet_display={'Grid ON':0})
    actual=copy.deepcopy(expected)
    if field=='model_text':actual['components'][0]['model_text']='lost'
    elif field=='page_name':actual['sheets'][0]['page']='lost'
    elif field=='annotations':actual['annotations'][0]['text']='lost'
    else:actual['sheet_display']['Grid ON']=1
    assert EditorService.saved_signature([expected])!=EditorService.saved_signature([actual])


def test_saved_label_positions_compare_native_transforms_not_text_cache(tmp_path):
    s=scene()
    s['components']=[{'ref':'VIN','transform':[1,0,0,1,9,234], 'pins':[],
                      'labels':[{'kind':'reference','text':'V1','center':{'x':103,'y':200},
                                 'transform':[1,0,0,1,81,-42]}]}]
    host,calls=saving_host(tmp_path,[s]);original=host.call
    def call(op,args=None):
        result=original(op,args)
        if op=='verifySavedCopy':result['states'][0]['components'][0]['labels'][0]['center']['x']=100
        return result
    host.call=call
    assert host.save_copy(str(tmp_path/'cached-label.ms14'))['verification']['passed']
    before=EditorService.saved_signature([s]);changed=copy.deepcopy(s)
    changed['components'][0]['labels'][0]['transform'][4]+=3
    assert EditorService.saved_signature([changed])!=before
    changed=copy.deepcopy(s);changed['components'][0]['labels'][0]['text']='OTHER'
    assert EditorService.saved_signature([changed])!=before


def test_unicode_analysis_transport_copies_results_and_cleans_on_failure(tmp_path,monkeypatch):
    root=tmp_path/'transport';root.mkdir();monkeypatch.setenv('MULTISIM_NATIVE_IO_DIR',str(root))
    output=tmp_path/'中文';output.mkdir();host=EditorService()
    for failed in (False,True):
        try:
            with host.analysis_transport(output/'analysis') as native:
                assert str(native).isascii()
                native.with_suffix('.cir').write_text('netlist',encoding='utf8')
                native.with_suffix('.raw').write_text('waveform',encoding='utf8')
                if failed:raise RuntimeError('analysis failed')
        except RuntimeError:assert failed
        assert (output/'analysis.cir').read_text()=='netlist'
        assert (output/'analysis.raw').read_text()=='waveform'
        assert not list(root.iterdir())


@pytest.mark.parametrize('failure',[False,True])
def test_image_intermediate_is_removed_after_success_or_native_failure(tmp_path,failure):
    host=EditorService();host.working=tmp_path/'工作副本.ms14'
    s=scene()
    def call(op,args=None):
        if op=='synchronizeGraphics':return {}
        if op=='circuitState':return s
        if op=='exportImage':
            Image.new('RGB',(1032,792),'white').save(args['path'])
            if failure:raise RuntimeError('Native render failed')
            return {}
        raise AssertionError(op)
    host.call=call;output=tmp_path/'电路.png'
    if failure:
        with pytest.raises(RuntimeError,match='render failed'):host.export_image(str(output))
    else:
        host.export_image(str(output));assert output.is_file()
    assert not list(tmp_path.glob('native-image-*.bmp'))
