from pathlib import Path
import pytest
from multisim_native_mcp.service import parse_raw, EditorService


def raw_file(tmp_path, content):
    path=tmp_path/'analysis.raw';path.write_text(content, encoding='utf-8');return path


def test_real_sample_grid_and_native_names(tmp_path):
    data=parse_raw(raw_file(tmp_path, '''Title: Divider
Plotname: Transient Analysis
Flags: real
No. Variables: 2
No. Points: 2
Variables:
0 time time
1 v(2) voltage V(2)
Values:
0 0
6
1 0.001
6
'''))
    assert data['rows'] == [[0.0,6.0],[0.001,6.0]]
    assert data['variables'][1]['name'] == 'V(2)'
    assert data['points'] == 2


@pytest.mark.parametrize('count,points',[('0','1'),('1','0'),('-1','1'),('1','-1')])
def test_empty_or_oversized_plots(tmp_path,count,points):
    with pytest.raises(RuntimeError):parse_raw(raw_file(tmp_path,f'No. Variables: {count}\nNo. Points: {points}\nVariables:\n'))


@pytest.mark.parametrize('value',['nan','inf','-inf'])
def test_nonfinite_samples(tmp_path,value):
    text=f'No. Variables: 1\nNo. Points: 1\nVariables:\n0 v(1) voltage\nValues:\n0 {value}\n'
    with pytest.raises(ValueError,match='nonfinite'):parse_raw(raw_file(tmp_path,text))


def test_truncated_waveform(tmp_path):
    text='No. Variables: 2\nNo. Points: 1\nVariables:\n0 time time\n1 v(1) voltage\nValues:\n0 0\n'
    with pytest.raises(ValueError,match='sample count'):parse_raw(raw_file(tmp_path,text))


def test_unexpected_trailing_content(tmp_path):
    text='No. Variables: 1\nNo. Points: 1\nVariables:\n0 time time\nValues:\n0 0\nextra sample\n'
    with pytest.raises(ValueError,match='trailing'):parse_raw(raw_file(tmp_path,text))


@pytest.mark.parametrize('operation,args',[
    ('route',{'points':[{'x':0,'y':0}]}),
    ('route',{'points':[{'x':0,'y':0},{'x':float('inf'),'y':0}]}),
    ('transform',{'angle':float('nan')}),
    ('setParameter',{'index':-1,'value':1}),
    ('setParameter',{'index':1,'value':float('nan')}),
    ('rename',{'ref':'R1\0invalid'}),
    ('sheetSize',{'width':0,'height':100}),
])
def test_invalid_edits(operation,args):
    with pytest.raises(ValueError):EditorService.validate(operation,args)
