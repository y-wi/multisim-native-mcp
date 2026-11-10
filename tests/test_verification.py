import pytest
from multisim_native_mcp.verification import verify,decode_display,SEGMENTS


def test_acceptance_and_failure():
    measurements=[{'id':'v','value':6}]
    assert verify(measurements,[{'measurement':'v','target':6.01,'absolute_tolerance':.02}])['passed']
    assert not verify(measurements,[{'measurement':'v','max':5.99}])['passed']
    for criteria in [[],[{'measurement':'missing','min':0}],[{'measurement':'v'}]]:
        with pytest.raises(ValueError):verify(measurements,criteria)


def fixture(wrong=False,conflict=False):
    names=['time']+[f's{i}' for i in range(7)]+['d0','d1']
    rows=[]
    for n in range(41):
        digit=(n//10)%2;number='1' if digit==0 else ('3' if wrong else '2')
        pattern=next(k for k,v in SEGMENTS.items() if v==number)
        rows.append([n*.001]+[5*int(v) for v in pattern]+[5 if digit==0 or conflict else 0,5 if digit==1 or conflict else 0])
    data={'complex':False,'rows':rows,'variables':[{'index':i,'name':n,'native_name':n} for i,n in enumerate(names)]}
    digits=[{'segments':names[1:8],'select':f'd{i}'} for i in range(2)]
    return data,digits


def test_decode_stable_scanned_display_and_wrong_or_conflicting_selection():
    for wrong,conflict,passed in [(False,False,True),(True,False,False),(False,True,False)]:
        data,digits=fixture(wrong,conflict)
        result=decode_display(data,digits,'12',settling=.002,min_dwell=.001)
        assert result['passed']==passed
