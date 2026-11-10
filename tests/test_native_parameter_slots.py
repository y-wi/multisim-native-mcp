"""Cross-check virtual resistor slots against native SPICE and RAW output."""
import json
from pathlib import Path
import re

import pytest

from multisim_native_mcp.service import EditorService


pytestmark = pytest.mark.native


def test_value_slot_controls_native_resistance_and_current(tmp_path):
    host = EditorService()
    try:
        host.create('Parameter slot comparison')
        operations = []
        for name, ref, x, y, index, value in [
            ('DC_POWER', 'V1', 108, 108, 1, 12),
            ('RESISTOR_VIRTUAL', 'R1', 306, 108, 0, 1000),
            ('RESISTOR_VIRTUAL', 'R2', 504, 108, 0, 1000),
            ('GROUND', '0', 108, 306, None, None),
        ]:
            args = {'name': name, 'ref': ref, 'x': x, 'y': y}
            if index is not None:
                args['parameters'] = [{'index': index, 'value': value}]
            operations.append({'operation': 'place', 'arguments': args})
        for a, ap, b, bp in [
            ('V1', '1', 'R1', '1'), ('R1', '2', 'R2', '1'),
            ('R2', '2', 'V1', '2'), ('V1', '2', '0', '1'),
        ]:
            operations.append({'operation': 'wire', 'arguments': {
                'source': {'ref': a, 'pin': ap}, 'target': {'ref': b, 'pin': bp}}})
        placed = host.batch(operations, include_state=True)
        resistors = [c for c in placed['state']['components'] if c['ref'] in ('R1', 'R2')]
        value_slots = {}
        for resistor in resistors:
            parameters = resistor['parameters']
            assert next(p for p in parameters if p['index'] == 0)['role'] == 'model_option'
            primary = next(p for p in parameters if p.get('role') == 'value')
            assert primary['name'] == 'resistance' and primary['unit'] == 'Ohm'
            value_slots[resistor['ref']] = primary['index']

        def analyze():
            result = host.run_analysis('op')
            source = Path(result['netlist_path']).read_text(encoding='utf-8')
            resistances = {ref: float(re.search(
                rf'^r{ref}\s+\S+\s+\S+\s+(\S+)', source, re.MULTILINE).group(1))
                for ref in ('R1', 'R2')}
            current = next(v for v in result['vectors'] if v['name'] == 'I(V1)')
            raw = Path(result['raw_path']).read_text(encoding='utf-8')
            lines = raw.split('Values:', 1)[1].strip().splitlines()
            native_current = float(lines[current['index']].split()[-1])
            assert current['unit'] == 'A' and result['unit_system'] == 'SI'
            assert current['first'] == native_current
            return {'resistances': resistances, 'current': current,
                    'raw_current': native_current, 'result': result}

        wrong_slot = analyze()
        assert wrong_slot['resistances'] == {'R1': 0, 'R2': 0}
        assert abs(wrong_slot['raw_current']) > 1e9
        host.batch([{'operation': 'setParameter', 'arguments': {
            'ref': ref, 'index': index, 'value': 1000}}
            for ref, index in value_slots.items()])
        correct_slot = analyze()
        assert correct_slot['resistances'] == {'R1': 1000, 'R2': 1000}
        assert correct_slot['raw_current'] == pytest.approx(-0.006, abs=1e-10)
        (tmp_path / 'parameter-slot-comparison.json').write_text(
            json.dumps({'model_option_only': wrong_slot, 'value_slot_set': correct_slot}, indent=2),
            encoding='utf-8')
    finally:
        host.close()
