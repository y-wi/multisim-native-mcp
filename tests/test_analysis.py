import json
import threading
import pytest
from multisim_native_mcp.service import EditorService
from multisim_native_mcp.waveforms import parse_raw, summarize, export_csv


def test_complex_and_digital_plots(tmp_path):
    raw=tmp_path/'mixed.raw'
    raw.write_text('''Title: RC
Plotname: AC Analysis
Flags: complex
No. Variables: 2
No. Points: 1
Variables:
0 frequency frequency
1 n2 voltage V(2)
Values:
0 100,0
0.5,-0.5

Plotname: Transient Analysis Digital Node
DigitalFlags: Yes
Flags: real
No. Variables: 2
No. Points: 2
Variables:
0 time time
1 n3 voltage D(3)
Values:
0,0,0
0.001,1,0
''')
    data=parse_raw(raw)
    assert data['additional_plots'][0]['rows'][1]==[0.001,1,0]
    assert summarize(data)[1]['max']==pytest.approx(2**-.5)
    csv=tmp_path/'ac.csv';export_csv(data,csv)
    assert 'V(2).imag' in csv.read_text(encoding='utf-8-sig')


def test_failure_records_stage_without_export(tmp_path):
    host=EditorService();host.working=tmp_path/'working.ms14'
    host.netlist=lambda: {'failed':False,'handles_invalidated':False}
    calls=[]
    def call(op,args):
        calls.append(op)
        return {'failed':True,'stage':'load-netlist','trace':[{'stage':'load-netlist','errors':[{'code':4}]}]}
    host.call=call
    with pytest.raises(RuntimeError,match='load-netlist'):host.run_analysis()
    assert calls==['simulate']
    record=json.loads(next(tmp_path.glob('analysis-*.json')).read_text())
    assert record['status']=='failed' and record['native']['trace'][0]['errors']


def test_netlist_failure_is_also_persisted(tmp_path):
    host=EditorService();host.working=tmp_path/'working.ms14'
    host.netlist=lambda:{'failed':True,'messages':'floating pin','content':'native source'}
    with pytest.raises(RuntimeError,match='floating pin'):host.run_analysis()
    record=json.loads(next(tmp_path.glob('analysis-*.json')).read_text())
    assert record['status']=='failed' and record['netlist']['messages']=='floating pin'


@pytest.mark.parametrize('options',[
    {'ac_sweep':'dec;quit'}, {'ac_points':0}, {'ac_start':0}, {'ac_stop':float('inf')},
    {'ac_sweep':'oct','ac_points':100000}, {'use_initial_conditions':True},
])
def test_invalid_ac_sweeps(options):
    with pytest.raises(ValueError):EditorService().run_analysis('ac',**options)
