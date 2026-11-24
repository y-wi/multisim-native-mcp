"""Unit tests for virtual instrument catalog, setting translation, persistence filters, and contracts."""
from __future__ import annotations

import asyncio
import unittest

from multisim_native_mcp import (
    bridge,
    edit_contracts,
    instruments,
    persistence,
    server,
    workflow_contracts,
)


class VirtualInstrumentsTests(unittest.TestCase):
    def test_instrument_catalog_complete_and_unique(self):
        self.assertEqual(len(instruments.INSTRUMENT_CATALOG), 19)
        keys = [entry['instrument'] for entry in instruments.INSTRUMENT_CATALOG]
        self.assertEqual(len(keys), len(set(keys)))
        for entry in instruments.INSTRUMENT_CATALOG:
            self.assertTrue(entry['dll'].endswith('.dll'))
            self.assertTrue(entry['pin_map'], f"Missing pin_map for {entry['instrument']}")

    def test_resolve_instrument_aliases(self):
        cases = [
            ('oscilloscope', 'oscilloscope'),
            ('scope', 'oscilloscope'),
            ('XSC', 'oscilloscope'),
            ('示波器', 'oscilloscope'),
            ('双通道示波器', 'oscilloscope'),
            ('scope_4ch', 'oscilloscope_4ch'),
            ('四通道示波器', 'oscilloscope_4ch'),
            ('function_generator', 'function_generator'),
            ('fgen', 'function_generator'),
            ('函数发生器', 'function_generator'),
            ('multimeter', 'multimeter'),
            ('dmm', 'multimeter'),
            ('万用表', 'multimeter'),
            ('wattmeter', 'wattmeter'),
            ('bode_plotter', 'bode_plotter'),
            ('波特图仪', 'bode_plotter'),
            ('frequency_counter', 'frequency_counter'),
            ('word_generator', 'word_generator'),
            ('logic_converter', 'logic_converter'),
            ('logic_analyzer', 'logic_analyzer'),
            ('iv_analyzer', 'iv_analyzer'),
            ('distortion_analyzer', 'distortion_analyzer'),
            ('spectrum_analyzer', 'spectrum_analyzer'),
            ('network_analyzer', 'network_analyzer'),
            ('33120a', 'agilent_function_generator'),
            ('34401a', 'agilent_multimeter'),
            ('54622d', 'agilent_oscilloscope'),
            ('tds2024', 'tektronix_oscilloscope'),
            ('电流探针', 'current_probe'),
            ('imeter', 'current_probe'),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(instruments.resolve_instrument(query)['instrument'], expected)

    def test_resolve_unknown_instrument_raises(self):
        with self.assertRaisesRegex(ValueError, 'Unknown virtual instrument'):
            instruments.resolve_instrument('nonexistent_widget')

    def test_compile_friendly_and_nested_settings(self):
        fgen = instruments.resolve_instrument('function_generator')
        writes = instruments.compile_instrument_settings(
            fgen,
            {
                'waveform': 'square',
                'frequency_hz': 1000,
                'duty_cycle_pct': 40,
                'amplitude_vp': 5,
                'offset_v': 2.5,
            },
        )
        by_path = {tuple(w['path']): w['value'] for w in writes}
        self.assertEqual(by_path[('NI_EWB_WAVE_MODE',)], 2)
        self.assertEqual(by_path[('NI_EWB_FREQUENCY_VALUE',)], 1000.0)
        self.assertEqual(by_path[('NI_EWB_DEPUTY_CYCLE_VALUE',)], 40.0)
        self.assertEqual(by_path[('NI_EWB_AMPLITUDE_VALUE',)], 5.0)
        self.assertEqual(by_path[('NI_EWB_OFFSET_VALUE',)], 2.5)

        scope4 = instruments.resolve_instrument('oscilloscope_4ch')
        writes4 = instruments.compile_instrument_settings(
            scope4,
            {
                'channel_a': {'coupling': 'AC', 'scale_v_per_div': 1.25},
                'channel_b_scale_v_per_div': 2.5,
                'NI_EWB_4CH_SCOPE_CHANNELS[2].NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE': 0.5,
            },
        )
        by_path4 = {tuple(w['path']): w['value'] for w in writes4}
        self.assertEqual(by_path4[('NI_EWB_4CH_SCOPE_CHANNELS', 0, 'NI_EWB_4CH_SCOPE_CHANNELMODE')], 0)
        self.assertEqual(by_path4[('NI_EWB_4CH_SCOPE_CHANNELS', 0, 'NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE')], 1.25)
        self.assertEqual(by_path4[('NI_EWB_4CH_SCOPE_CHANNELS', 1, 'NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE')], 2.5)
        self.assertEqual(by_path4[('NI_EWB_4CH_SCOPE_CHANNELS', 2, 'NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE')], 0.5)

    def test_compile_invalid_settings_rejected(self):
        fgen = instruments.resolve_instrument('function_generator')
        with self.assertRaisesRegex(ValueError, 'positive'):
            instruments.compile_instrument_settings(fgen, {'frequency_hz': -5})
        with self.assertRaisesRegex(ValueError, 'Unknown value'):
            instruments.compile_instrument_settings(fgen, {'waveform': 'chirp'})
        with self.assertRaisesRegex(ValueError, 'Unknown setting'):
            instruments.compile_instrument_settings(fgen, {'bogus_knob': 1})
        with self.assertRaisesRegex(ValueError, 'Duplicate setting target'):
            instruments.compile_instrument_settings(fgen, {'frequency_hz': 100, 'NI_EWB_FREQUENCY_VALUE': 200})

    def test_filter_persistent_props_strips_volatile_fields(self):
        raw = {
            'NI_EWB_SHOW_WINDOW_STATUS': {'type': 'uint', 'native_type': 2, 'value': 1},
            'NI_EWB_DIALOG_STATUS': {'type': 'array', 'native_type': 4, 'value': []},
            'NI_EWB_CIRCUIT_NAME': {'type': 'string', 'native_type': 5, 'value': 'temp'},
            'NI_EWB_CURRENTDISPLAYDATA_VALUE': {'type': 'string', 'native_type': 5, 'value': '1.5 V'},
            'NI_EWB_PIN_COLORS': {'type': 'array', 'native_type': 4, 'value': []},
            'NI_EWB_TIMEBASE_SCALE_VALUE': {'type': 'double', 'native_type': 3, 'value': 0.0005},
            'NI_EWB_A_CHANNEL_MODE': {'type': 'int', 'native_type': 1, 'value': 2},
        }
        filtered = instruments.filter_persistent_instrument_props(raw)
        self.assertEqual(
            filtered,
            {
                'NI_EWB_TIMEBASE_SCALE_VALUE': 0.0005,
                'NI_EWB_A_CHANNEL_MODE': 2,
            },
        )

    def test_edit_contracts_and_workflow_plan_accept_instruments(self):
        norm_place = edit_contracts.normalize_edit({
            'operation': 'native_place_instrument',
            'arguments': {'name': '示波器', 'reference': 'XSC1', 'x': 300, 'y': 200},
        })
        self.assertEqual(
            norm_place,
            {'operation': 'placeInstrument', 'arguments': {'instrument': '示波器', 'ref': 'XSC1', 'x': 300, 'y': 200}},
        )

        norm_set = edit_contracts.normalize_edit({
            'operation': 'set_instrument_settings',
            'arguments': {'component_ref': 'XSC1', 'settings': {'timebase_scale_s_per_div': 0.001}},
        })
        self.assertEqual(
            norm_set,
            {'operation': 'setInstrumentSettings', 'arguments': {'ref': 'XSC1', 'settings': {'timebase_scale_s_per_div': 0.001}}},
        )

        plan = workflow_contracts.WorkflowPlan.model_validate({
            'steps': [
                {
                    'id': 'build',
                    'kind': 'edit',
                    'operations': [
                        {'operation': 'place_instrument', 'bind': 'osc', 'arguments': {'instrument': 'oscilloscope', 'x': 400, 'y': 200}},
                        {'operation': 'set_instrument_settings', 'arguments': {'component_ref': {'$ref': 'osc.component.id'}, 'settings': {'channel_a_scale_v_per_div': 2.0}}},
                    ],
                }
            ]
        })
        self.assertEqual([op.operation for op in plan.steps[0].operations], ['placeInstrument', 'setInstrumentSettings'])

    def test_server_and_persistence_tool_parity(self):
        caps = persistence.persistence_capabilities()
        persisted = {t['tool'] for t in caps['tools']}
        registered = {t.name for t in server.server._tool_manager.list_tools()}
        listed = {t.name for t in asyncio.run(server.server.list_tools())}
        self.assertEqual(registered, persisted)
        self.assertEqual(caps['registered_tool_count'], len(registered))
        self.assertEqual(caps['tool_count'], len(listed))
        self.assertTrue({
            'native_list_instruments',
            'native_place_instrument',
            'native_get_instrument_settings',
            'native_set_instrument_settings',
            'native_export_instrument_data',
        } <= listed)
        self.assertIn('function placeInstrument', bridge.editor_script())


if __name__ == '__main__':
    unittest.main()
