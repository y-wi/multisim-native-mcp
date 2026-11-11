import pytest

from multisim_native_mcp.service import EditorService, NativeEditError


pytestmark = pytest.mark.native


def test_shared_power_symbols_move_by_id_without_changing_other_attachments(tmp_path):
    h = EditorService()
    try:
        h.create('Shared power symbol movement')
        h.call('wiringOptions', {'connect_touching': False, 'autowire_on_connection': False})
        for i, x in enumerate((180, 540), 1):
            power = h.edit('place', {'name': 'VCC', 'ref': f'P{i}', 'x': x, 'y': 180,
                                     'anchor': 'center'})['component']
            h.edit('place', {'name': 'RESISTOR_VIRTUAL', 'ref': f'R{i}', 'x': x,
                            'y': 360, 'anchor': 'center',
                            'parameters': [{'index': 1, 'value': 1000 * i}]})
            h.edit('place', {'name': 'GROUND', 'ref': f'G{i}', 'x': x, 'y': 540,
                            'anchor': 'center'})
            h.edit('wire', {'source': {'ref': power['id'], 'pin': power['pins'][0]['name']},
                            'target': {'ref': f'R{i}', 'pin': '1'}})
            ground = next(c for c in h.call('components')['components'] if c['local_ref'] == f'G{i}')
            h.edit('wire', {'source': {'ref': f'R{i}', 'pin': '2'},
                            'target': {'ref': ground['id'], 'pin': ground['pins'][0]['name']}})
        assert not h.netlist()['failed']
        powers = [c for c in h.call('components')['components'] if c['ref'] == 'VCC']
        assert len(powers) == 2
        target, peer = powers
        baseline = h.run_analysis('op')
        baseline_values = {v['name']: v['last'] for v in baseline['vectors']}
        assert any(abs(v - 5) < 1e-8 for k, v in baseline_values.items() if k.startswith('V('))
        peer_pin_ids = {p['id'] for p in peer['pins']}
        original = h.call('wires')['wires']
        peer_wires = [w for w in original if any(w[e]['id'] in peer_pin_ids for e in ('source', 'target'))]
        assert len(peer_wires) == 1
        original_topology = {(w['id'], w['source']['id'], w['target']['id']) for w in original}
        for autowire, touching, limit in [(False, False, 12), (True, False, 12),
                                          (False, True, 12), (True, True, 12), (True, False, 1)]:
            h.call('wiringOptions', {'autowire_on_move': autowire, 'connect_touching': touching,
                                     'move_connection_limit': limit})
            moved = h.edit('move', {'ref': target['id'], 'dx': 9, 'dy': 18})
            assert moved['id'] == target['id'] and moved['updated_wires'] == 1
            assert moved['routing_engine'] == ('multisim-native' if autowire and limit > 1 else 'preserve')
            current = h.call('components')['components']
            assert next(c for c in current if c['id'] == peer['id']) == peer
            links = h.call('wires')['wires']
            assert {(w['id'], w['source']['id'], w['target']['id']) for w in links} == original_topology
            assert [w for w in links if w['id'] == peer_wires[0]['id']] == peer_wires
            for wire in links:
                for end, index in [('source', 0), ('target', -1)]:
                    assert wire['points'][index] == {k: wire[end][k] for k in ('x', 'y')}
                    assert wire[end]['graphics_aligned']
                    assert wire[end]['component_id'] in {c['id'] for c in current}
            h.edit('move', {'ref': target['id'], 'dx': -9, 'dy': -18})
        # Rotation and contact processing must retain the same object identity too.
        h.edit('transform', {'ref': target['id'], 'angle': 180})
        h.edit('transform', {'ref': target['id'], 'angle': 180})
        h.edit('connectTouching', {})
        before = h.call('components')['components']
        with pytest.raises(NativeEditError, match='current component ID') as error:
            h.edit('move', {'ref': 'VCC', 'dx': 9, 'dy': 0})
        assert not error.value.details['handles_invalidated']
        assert h.call('components')['components'] == before
        assert all(c['id'] in str(error.value) for c in powers)
        assert h.save_copy(str(tmp_path / 'shared-power.ms14'))['verification']['passed']
        result = h.run_analysis('op')
        assert {v['name']: v['last'] for v in result['vectors']} == pytest.approx(baseline_values, abs=1e-9)
        # Deleting one symbol removes only its own wire, even with a shared net name.
        powers = [c for c in h.call('components')['components'] if c['ref'] == 'VCC']
        kept = next(c for c in powers if c['transform'] == peer['transform'])
        deleted = next(c for c in powers if c['id'] != kept['id'])
        kept_pins = {p['id'] for p in kept['pins']}
        kept_wires = [w for w in h.call('wires')['wires'] if any(w[e]['id'] in kept_pins for e in ('source', 'target'))]
        h.edit('remove', {'ref': deleted['id']})
        assert [w for w in h.call('wires')['wires'] if w['id'] in {w['id'] for w in kept_wires}] == kept_wires
    finally:
        h.close()
