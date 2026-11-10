import math
import pytest
from multisim_native_mcp.measurements import measure


def data(rows,complex=False):
    return {'rows':rows,'complex':complex,'variables':[{'index':i,'name':n,'native_name':n} for i,n in enumerate(['time','out','in'])]}


def test_adaptive_time_weighting_and_window():
    d=data([[0,0],[.1,.1],[1,1]])
    r=measure(d,[{'metric':m,'signal':'out','start':.2,'stop':.8} for m in ['mean','rms','peak_to_peak']])
    assert [v['value'] for v in r]==pytest.approx([.5,math.sqrt(.28),.6])


def test_crossings_duty_and_frequency():
    d=data([[i/4,v] for i,v in enumerate([0,1,0,1,0,1,0])])
    r=measure(d,[{'metric':m,'signal':'out','threshold':.5} for m in ['frequency','duty_cycle']])
    assert [v['value'] for v in r]==pytest.approx([2,.5])


def test_complex_transfer():
    d=data([[[100,0],[.5,-.5],[1,0]]],True)
    r=measure(d,[{'metric':m,'signal':'out','reference':'in','frequency_hz':100} for m in ['gain_db','phase_deg']])
    assert [v['value'] for v in r]==pytest.approx([-3.01029995664,-45])


@pytest.mark.parametrize('req',[
    {'metric':'unknown','signal':'out'}, {'metric':'mean','signal':'absent'},
    {'metric':'mean','signal':'out','start':-1}, {'metric':'frequency','signal':'out'},
])
def test_reject_unmeasurable_requests(req):
    with pytest.raises(ValueError):measure(data([[0,0],[1,1]]),[req])
