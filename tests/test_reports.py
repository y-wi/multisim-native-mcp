import json
from pathlib import Path
import pytest
from PIL import Image
from multisim_native_mcp.reports import export_report,waveform_svg


def test_reports_escape_text_preserve_measurements_and_protect_outputs(tmp_path):
    raw=tmp_path/'data.raw';raw.write_text('No. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 out voltage\nValues:\n0 0\n1\n1 1\n2\n')
    image=tmp_path/'source.png';Image.new('RGB',(10,10)).save(image)
    record={'id':'a'*32,'status':'complete','schematic_path':str(image),'result':{'best':0,'trials':[
        {'index':0,'status':'complete','parameters':[{'ref':'R1','index':1,'value':1000}],
         'analysis':{'raw_path':str(raw)},'measurements':[{'id':'m','value':1.5,'unit':'V'}],
         'feasible':True,'acceptance':{'passed':True}}]}}
    for lang in ['zh','en']:
        out=tmp_path/lang;out.mkdir()
        result=export_report(record,str(out),lang,'<test>')
        html=(out/'report.html').read_text(encoding='utf-8')
        assert '&lt;test&gt;' in html and '<test>' not in html
        assert 'data:image/png;base64,' in html and '<svg ' in html and '1.5' in html
        assert len(result['files'])==5 and all(Path(p).is_file() for p in result['files'].values())
        with pytest.raises(FileExistsError):export_report(record,str(out),lang)
