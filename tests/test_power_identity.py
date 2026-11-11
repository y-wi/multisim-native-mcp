from copy import deepcopy

from multisim_native_mcp import server


def test_wire_filter_distinguishes_shared_power_symbol_ids(monkeypatch):
    wires = [
        {'id': 'w1', 'source': {'ref': 'VCC', 'component_id': 'c1'}, 'target': {'ref': 'R1', 'component_id': 'r1'}},
        {'id': 'w2', 'source': {'ref': 'R2', 'component_id': 'r2'}, 'target': {'ref': 'VCC', 'component_id': 'c2'}},
        {'id': 'w3', 'source': {'id': 'j1'}, 'target': {'ref': 'R3', 'component_id': 'r3'}},
    ]
    monkeypatch.setattr(server.host, 'call', lambda name: {'wires': deepcopy(wires)})
    assert server.native_list_wires()['wires'] == wires
    assert server.native_list_wires('VCC')['wires'] == wires[:2]
    assert server.native_list_wires('c1')['wires'] == wires[:1]
    assert server.native_list_wires('c2')['wires'] == wires[1:2]
    assert server.native_list_wires('R2')['wires'] == wires[1:2]
    assert server.native_list_wires('missing')['wires'] == []
