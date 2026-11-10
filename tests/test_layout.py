from multisim_native_mcp.layout import orthogonal_path,intersects,check_layout,plan_wire


def test_route_around_blocked_direct_path():
    obstacle={'left':20,'right':40,'top':-10,'bottom':10}
    route=orthogonal_path({'x':0,'y':0},{'x':60,'y':0},[obstacle])
    assert route[0]=={'x':0,'y':0} and route[-1]=={'x':60,'y':0}
    assert all(a['x']==b['x'] or a['y']==b['y'] for a,b in zip(route,route[1:]))
    assert not any(intersects(a,b,obstacle) for a,b in zip(route,route[1:]))


def test_detect_electrical_endpoint_mismatch_and_hidden_wire():
    components=[{'ref':'R1','bounds':{'left':10,'top':10,'right':30,'bottom':30},
                 'pins':[{'id':'p','x':10,'y':20}]}]
    wires=[{'id':'w','source':{'id':'p','ref':'R1'},'target':{'id':'j','x':50,'y':20},
            'points':[{'x':9,'y':20},{'x':50,'y':20}],'has_pen':False}]
    result=check_layout(components,wires)
    assert result['errors']==2
    assert {i['kind'] for i in result['issues']}=={'detached_endpoint','invisible_wire'}


def test_detect_graphic_gap_even_when_electrical_endpoint_matches():
    wires=[{'id':'w','source':{'id':'p','x':270,'y':423,'graphic_position':{'x':269,'y':420}},
            'target':{'id':'j','x':315,'y':423,'graphic_position':{'x':315,'y':423}},
            'points':[{'x':270,'y':423},{'x':315,'y':423}]}]
    result=check_layout([],wires)
    assert result['errors']==1
    assert result['issues'][0]['kind']=='graphic_endpoint_mismatch'
    assert result['issues'][0]['end']=='source'
