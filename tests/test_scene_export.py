import pytest
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.waveforms import parse_raw,export_csv


@pytest.mark.parametrize('options',[
    {'dpi':0},{'scale':float('nan')},{'scale':0},{'dpi':600,'scale':8},
    {'padding':-1},{'region':{},'fit_content':True},
])
def test_invalid_export_options_fail_before_native_calls(options):
    host=EditorService()
    host.call=lambda *args:pytest.fail('Invalid options reached the native host')
    with pytest.raises(ValueError):host.export_image('unused.png',**options)


def test_raw_current_units_are_amperes_without_rescaling(tmp_path):
    raw=tmp_path/'current.raw'
    raw.write_text('No. Variables: 2\nNo. Points: 1\nVariables:\n0 voltage voltage V(1)\n1 current current I(V1)\nValues:\n0 12\n-6000000000000\n')
    data=parse_raw(raw)
    assert data['variables'][1]['unit']=='A' and data['rows'][0][1]==-6e12
    assert data['unit_system']=='SI'
    csv=tmp_path/'current.csv';export_csv(data,csv)
    assert 'I(V1) [A]' in csv.read_text(encoding='utf-8-sig')


@pytest.mark.parametrize('parameters',[
    [{'index':1}], [{'index':1,'value':1,'expression':'1'}],
    [{'index':1,'value':float('inf')}], [{'index':1,'expression':'x\0invalid'}],
])
def test_inline_parameter_validation(parameters):
    with pytest.raises(ValueError):EditorService.validate('place',{'parameters':parameters})
