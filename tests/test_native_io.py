from pathlib import Path

import pytest

from multisim_native_mcp import bridge,service
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_unicode_session_outputs_and_verified_saved_copy(tmp_path,monkeypatch):
    data=tmp_path/'中文会话';data.mkdir()
    monkeypatch.setattr(bridge,'DATA_DIR',data);monkeypatch.setattr(service,'DATA_DIR',data)
    host=EditorService()
    try:
        host.create('Unicode paths')
        host.batch([{'operation':'place','arguments':{'name':name,'ref':ref,'x':x,'y':y,'anchor':'pin','pin':'1',
                    **({'parameters':[{'index':1,'value':value}]} if value is not None else {})}}
                    for name,ref,x,y,value in [('DC_POWER','V1',90,90,12),('RESISTOR_VIRTUAL','R1',360,90,1000),
                                               ('RESISTOR_VIRTUAL','R2',540,90,1000),('GROUND','0',90,360,None)]])
        host.batch([{'operation':'wire','arguments':{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}}}
                    for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]])
        host.netlist()
        picture=host.export_image(str(tmp_path/'中文电路.png'))
        assert Path(picture['path']).is_file() and not list(host.folder().glob('native-image-*.bmp'))
        numeric=host.run_analysis('op')
        assert next(v for v in numeric['vectors'] if v['name']=='I(V1)')['last']==pytest.approx(-.006,abs=1e-8)
        host.edit('createSheet',{'title':'Second sheet'})
        host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R10','x':180,'y':180})
        ids=host.call('components');projects=host.call('projects')
        output=tmp_path/'已存在的工程.ms14';output.write_bytes(b'old target')
        result=host.save_copy(str(output),True)
        assert result['verification']['passed'] and result['verification']['sheets']==2
        assert host.call('components')['components']==ids['components']
        assert [p['id'] for p in host.call('projects')['projects']]==[p['id'] for p in projects['projects']]
        assert Path(result['backup']).read_bytes()==b'old target'
        assert not list(host.folder().glob('verify-*.ms14'))
        host.close();host.open_copy(str(output))
        assert len(host.call('sheets'))==2
    finally:host.close()
