"""Native NI Multisim virtual instrument catalog, setting translation, and persistence filters."""
from __future__ import annotations

import math
import re
from typing import Any


def _enum(mapping: dict[int, str], aliases: dict[str, int] | None = None) -> dict[str, Any]:
    to_int: dict[str, int] = {}
    for code, label in mapping.items():
        to_int[label.casefold()] = code
    if aliases:
        for alias, code in aliases.items():
            to_int[alias.casefold()] = code
    return {'by_code': mapping, 'to_code': to_int}


_SCOPE_COUPLING = _enum(
    {0: 'AC', 1: 'GND', 2: 'DC'},
    {'0': 1, 'ground': 1, 'gnd': 1, 'zero': 1},
)
_SCOPE_TRIGGER_EDGE = _enum(
    {0: 'rising', 1: 'falling'},
    {'positive': 0, 'pos': 0, 'up': 0, 'negative': 1, 'neg': 1, 'down': 1},
)
_SCOPE_TRIGGER_MODE = _enum(
    {0: 'auto', 1: 'single', 2: 'normal', 3: 'none'},
    {'sing': 1, 'norm': 2},
)
_SCOPE_SIGN = _enum(
    {1: 'normal', -1: 'invert'},
    {'+': 1, 'positive': 1, 'false': 1, '-': -1, 'inverted': -1, 'negative': -1, 'true': -1},
)
_SCOPE_2CH_TIMEBASE_MODE = _enum(
    {0: 'Y/T', 1: 'Add', 2: 'B/A', 3: 'A/B'},
    {'yt': 0, 'y_t': 0, 'sum': 1, 'a+b': 1, 'ba': 2, 'b_a': 2, 'ab': 3, 'a_b': 3},
)
_SCOPE_2CH_TRIGGER_SOURCE = _enum(
    {0: 'A', 1: 'B', 2: 'Ext'},
    {'ch_a': 0, 'channel_a': 0, 'ch_b': 1, 'channel_b': 1, 'external': 2},
)
_SCOPE_4CH_TIMEBASE_MODE = _enum(
    {0: 'Y/T', 1: 'A/B', 2: 'A+B'},
    {'yt': 0, 'y_t': 0, 'ab': 1, 'a_b': 1, 'sum': 2, 'add': 2},
)
_SCOPE_4CH_CHANNEL_INDEX = _enum(
    {0: 'A', 1: 'B', 2: 'C', 3: 'D'},
    {'ch_a': 0, 'channel_a': 0, 'ch_b': 1, 'channel_b': 1, 'ch_c': 2, 'channel_c': 2, 'ch_d': 3, 'channel_d': 3},
)
_SCOPE_4CH_TRIGGER_SOURCE = _enum(
    {0: 'channel', 1: 'ext'},
    {'internal': 0, 'external': 1},
)
_FGEN_WAVEFORM = _enum(
    {0: 'sine', 1: 'triangle', 2: 'square'},
    {'sin': 0, 'sinusoid': 0, 'tri': 1, 'triangular': 1, 'sawtooth': 1, 'rect': 2, 'pulse': 2, 'sq': 2},
)
_MM_MODE = _enum(
    {0: 'current', 1: 'voltage', 2: 'resistance', 3: 'db'},
    {'a': 0, 'amp': 0, 'amps': 0, 'ammeter': 0, 'v': 1, 'volt': 1, 'volts': 1, 'voltmeter': 1,
     'ohm': 2, 'ohms': 2, 'ohmmeter': 2, 'r': 2, 'decibel': 3, 'decibels': 3},
)
_SIGNAL_AC_DC = _enum({0: 'AC', 1: 'DC'})
_BODE_MODE = _enum({0: 'magnitude', 1: 'phase'}, {'mag': 0, 'gain': 0})
_SCALE_LOG_LIN = _enum({0: 'log', 1: 'lin'}, {'logarithmic': 0, 'linear': 1})
_FC_MODE = _enum(
    {0: 'frequency', 1: 'period', 2: 'pulse_width', 3: 'rise_fall'},
    {'freq': 0, 'pulse': 2, 'rise/fall': 3},
)
_DISTOR_MODE = _enum({0: 'thd', 1: 'sinad'})
_DISTOR_DISPLAY = _enum({0: 'percent', 1: 'db'}, {'%': 0})
_DISTOR_FORMULA = _enum({0: 'ieee', 1: 'ansi_iec'}, {'ansi': 1, 'iec': 1})
_SPEC_SPAN_MODE = _enum({0: 'set_span', 1: 'zero_span', 2: 'full_span'}, {'span': 0, 'zero': 1, 'full': 2})
_SPEC_VERT_MODE = _enum({0: 'db', 1: 'dbm', 2: 'lin'}, {'linear': 2})
_SPEC_TRIG_SOURCE = _enum({0: 'internal', 1: 'external'}, {'int': 0, 'ext': 1})
_SPEC_TRIG_MODE = _enum({0: 'continuous', 1: 'single'}, {'cont': 0})
_WGEN_MODE = _enum({0: 'step', 1: 'burst', 2: 'cycle'})
_WGEN_DISPLAY = _enum({0: 'hex', 1: 'dec', 2: 'binary', 3: 'ascii'}, {'bin': 2})
_LA_CLOCK_MODE = _enum({0: 'external', 1: 'internal'}, {'ext': 0, 'int': 1})
_LA_CLOCK_EDGE = _enum({0: 'positive', 1: 'negative', 2: 'both'}, {'rising': 0, 'pos': 0, 'falling': 1, 'neg': 1})
_NETAN_SWEEP = _enum({0: 'linear', 1: 'log'}, {'lin': 0, 'logarithmic': 1})


def _setting(
    name: str,
    path: list[str | int],
    kind: str,
    *,
    unit: str | None = None,
    enum: dict[str, Any] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    positive: bool = False,
    description: str = '',
) -> dict[str, Any]:
    spec: dict[str, Any] = {'name': name, 'path': path, 'kind': kind}
    if unit:
        spec['unit'] = unit
    if enum:
        spec['enum'] = enum
    if min_value is not None:
        spec['min'] = min_value
    if max_value is not None:
        spec['max'] = max_value
    if positive:
        spec['positive'] = True
    if description:
        spec['description'] = description
    return spec


def _scope_4ch_channel_settings(letter: str, index: int) -> list[dict[str, Any]]:
    prefix = f'channel_{letter.lower()}_'
    return [
        _setting(prefix + 'coupling', ['NI_EWB_4CH_SCOPE_CHANNELS', index, 'NI_EWB_4CH_SCOPE_CHANNELMODE'], 'enum', enum=_SCOPE_COUPLING, description=f'Channel {letter} input coupling (AC, GND/0, DC)'),
        _setting(prefix + 'scale_v_per_div', ['NI_EWB_4CH_SCOPE_CHANNELS', index, 'NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE'], 'number', unit='V/div', positive=True, description=f'Channel {letter} vertical scale in V/div'),
        _setting(prefix + 'position_div', ['NI_EWB_4CH_SCOPE_CHANNELS', index, 'NI_EWB_4CH_SCOPE_CHANNELPOSITIONVALUE'], 'number', unit='div', description=f'Channel {letter} vertical offset in divisions'),
        _setting(prefix + 'sign', ['NI_EWB_4CH_SCOPE_CHANNELS', index, 'NI_EWB_4CH_SCOPE_CHANNELSIGNVALUE'], 'enum', enum=_SCOPE_SIGN, description=f'Channel {letter} polarity (normal or invert)'),
    ]


INSTRUMENT_CATALOG: list[dict[str, Any]] = [
    {
        'instrument': 'multimeter',
        'display_name': 'Multimeter',
        'zh_name': '万用表',
        'dll': 'mulmeter.dll',
        'manager': 'Mulmeter',
        'native_type': 'MULMETER',
        'res_id': 5,
        'flags': 0x250000,
        'create_kind': 'standard',
        'default_prefix': 'XMM',
        'aliases': ['mulmeter', 'dmm', 'xmm', 'voltmeter', 'ammeter', 'ohmmeter', '万用表', '数字万用表'],
        'pin_map': {'1': '+', '2': '-'},
        'readout_keys': {'display_value': 'NI_EWB_CURRENTDISPLAYDATA_VALUE'},
        'settings': [
            _setting('mode', ['NI_EWB_MEASUREMENT_MODE'], 'enum', enum=_MM_MODE, description='Measurement mode (current/A, voltage/V, resistance/Ohm, db)'),
            _setting('signal', ['NI_EWB_SIGNAL_MODE'], 'enum', enum=_SIGNAL_AC_DC, description='Signal coupling (AC or DC)'),
            _setting('ammeter_resistance_ohm', ['NI_EWB_INTERNAL_SETTINGS', 0], 'number', unit='Ohm', positive=True, description='Internal shunt resistance in Ammeter mode'),
            _setting('voltmeter_resistance_ohm', ['NI_EWB_INTERNAL_SETTINGS', 1], 'number', unit='Ohm', positive=True, description='Internal input resistance in Voltmeter mode'),
            _setting('ohmmeter_current_a', ['NI_EWB_INTERNAL_SETTINGS', 2], 'number', unit='A', positive=True, description='Internal test current in Ohmmeter mode'),
            _setting('db_reference_v', ['NI_EWB_INTERNAL_SETTINGS', 3], 'number', unit='V', positive=True, description='0 dB reference voltage'),
        ],
    },
    {
        'instrument': 'function_generator',
        'display_name': 'Function Generator',
        'zh_name': '函数发生器',
        'dll': 'fgen.dll',
        'manager': 'fgen',
        'native_type': 'FGEN',
        'res_id': 5,
        'flags': 0x1E0000,
        'create_kind': 'standard',
        'default_prefix': 'XFG',
        'aliases': ['fgen', 'funcgen', 'signal_generator', 'xfg', '函数发生器', '信号发生器'],
        'pin_map': {'1': '+', '2': 'COM', '3': '-'},
        'settings': [
            _setting('waveform', ['NI_EWB_WAVE_MODE'], 'enum', enum=_FGEN_WAVEFORM, description='Output waveform shape (sine, triangle, square)'),
            _setting('frequency_hz', ['NI_EWB_FREQUENCY_VALUE'], 'number', unit='Hz', positive=True, description='Signal frequency in Hz'),
            _setting('duty_cycle_pct', ['NI_EWB_DEPUTY_CYCLE_VALUE'], 'number', unit='%', min_value=1, max_value=99, description='Duty cycle percentage (1..99)'),
            _setting('amplitude_vp', ['NI_EWB_AMPLITUDE_VALUE'], 'number', unit='Vp', min_value=0, description='Peak amplitude in volts (measured from COM to + or -)'),
            _setting('offset_v', ['NI_EWB_OFFSET_VALUE'], 'number', unit='V', description='DC offset voltage in volts'),
            _setting('rise_fall_time_s', ['NI_EWB_RISETIMESETTING'], 'number', unit='s', positive=True, description='Square-wave rise/fall time in seconds'),
        ],
    },
    {
        'instrument': 'wattmeter',
        'display_name': 'Wattmeter',
        'zh_name': '功率表',
        'dll': 'wattmetr.dll',
        'manager': 'Wattmtr',
        'native_type': 'WATTMTR',
        'res_id': 2710,
        'flags': 0x2D0000,
        'create_kind': 'standard',
        'default_prefix': 'XWM',
        'aliases': ['wattmtr', 'power_meter', 'xwm', '功率表', '瓦特表'],
        'pin_map': {'1': 'V+', '2': 'V-', '3': 'I+', '4': 'I-'},
        'readout_keys': {'power': 'NI_EWB_CURRENTDISPLAYDATAVALUE', 'power_factor': 'NI_EWB_CURRENTDISPLAYDATAFACTOR'},
        'settings': [],
    },
    {
        'instrument': 'oscilloscope',
        'display_name': 'Oscilloscope (2-Channel)',
        'zh_name': '双通道示波器',
        'dll': 'scope.dll',
        'manager': 'scope',
        'native_type': 'SCOPE',
        'res_id': 6,
        'flags': 0x2F0000,
        'create_kind': 'standard',
        'default_prefix': 'XSC',
        'aliases': ['scope', 'oscilloscope_2ch', '2ch_oscilloscope', '2ch_scope', 'xsc', '示波器', '双通道示波器'],
        'pin_map': {'1': 'A+', '4': 'A-', '2': 'B+', '5': 'B-', '3': 'Ext Trig +', '6': 'Ext Trig -'},
        'export_data_formats': ['.scp'],
        'settings': [
            _setting('timebase_mode', ['NI_EWB_TIMEBASE_MODE'], 'enum', enum=_SCOPE_2CH_TIMEBASE_MODE, description='Timebase display mode (Y/T, Add, B/A, A/B)'),
            _setting('timebase_scale_s_per_div', ['NI_EWB_TIMEBASE_SCALE_VALUE'], 'number', unit='s/div', positive=True, description='Horizontal scale in seconds per division'),
            _setting('timebase_range_s', ['NI_EWB_TIMEBASE_RANGE_VALUE'], 'number', unit='s', positive=True, description='Horizontal range in seconds'),
            _setting('timebase_position_div', ['NI_EWB_TIMEBASE_POSITION_VALUE'], 'number', unit='div', description='Horizontal X position in divisions'),
            _setting('channel_a_coupling', ['NI_EWB_A_CHANNEL_MODE'], 'enum', enum=_SCOPE_COUPLING, description='Channel A coupling (AC, GND/0, DC)'),
            _setting('channel_a_scale_v_per_div', ['NI_EWB_A_CHANNEL_SCALE_VALUE'], 'number', unit='V/div', positive=True, description='Channel A vertical scale in V/div'),
            _setting('channel_a_position_div', ['NI_EWB_A_CHANNEL_POSITION_VALUE'], 'number', unit='div', description='Channel A vertical offset in divisions'),
            _setting('channel_b_coupling', ['NI_EWB_B_CHANNEL_MODE'], 'enum', enum=_SCOPE_COUPLING, description='Channel B coupling (AC, GND/0, DC)'),
            _setting('channel_b_scale_v_per_div', ['NI_EWB_B_CHANNEL_SCALE_VALUE'], 'number', unit='V/div', positive=True, description='Channel B vertical scale in V/div'),
            _setting('channel_b_position_div', ['NI_EWB_B_CHANNEL_POSITION_VALUE'], 'number', unit='div', description='Channel B vertical offset in divisions'),
            _setting('channel_b_sign', ['NI_EWB_B_CHANNEL_SIGN_VALUE'], 'enum', enum=_SCOPE_SIGN, description='Channel B polarity (normal or invert)'),
            _setting('trigger_source', ['NI_EWB_TRIGGERBASE_SOURCE_MODE'], 'enum', enum=_SCOPE_2CH_TRIGGER_SOURCE, description='Trigger source (A, B, Ext)'),
            _setting('trigger_edge', ['NI_EWB_TRIGGERBASE_TRIGGER_EDGE'], 'enum', enum=_SCOPE_TRIGGER_EDGE, description='Trigger edge (rising or falling)'),
            _setting('trigger_level_v', ['NI_EWB_TRIGGERBASE_TRIGGERLEVEL'], 'number', unit='V', description='Trigger threshold voltage in volts'),
            _setting('trigger_mode', ['NI_EWB_TRIGGERBASE_TRIGGER_MODE'], 'enum', enum=_SCOPE_TRIGGER_MODE, description='Trigger sweep mode (auto, single, normal, none)'),
        ],
    },
    {
        'instrument': 'oscilloscope_4ch',
        'display_name': 'Four Channel Oscilloscope',
        'zh_name': '四通道示波器',
        'dll': 'scope_4ch.dll',
        'manager': 'scope_4ch',
        'native_type': 'SCOPE_4CH',
        'res_id': 7,
        'flags': 0x270000,
        'create_kind': 'standard',
        'default_prefix': 'XSC',
        'aliases': ['scope_4ch', 'four_channel_oscilloscope', '4ch_oscilloscope', '4ch_scope', '四通道示波器'],
        'pin_map': {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'T (Ext Trig)', '6': 'G (GND)'},
        'export_data_formats': ['.scp'],
        'settings': [
            _setting('timebase_mode', ['NI_EWB_4CH_SCOPE_TIMEBASE_MODE'], 'enum', enum=_SCOPE_4CH_TIMEBASE_MODE, description='Timebase display mode (Y/T, A/B, A+B)'),
            _setting('timebase_scale_s_per_div', ['NI_EWB_4CH_SCOPE_TIMEBASE_SCALE_VALUE'], 'number', unit='s/div', positive=True, description='Horizontal scale in seconds per division'),
            _setting('timebase_range_s', ['NI_EWB_4CH_SCOPE_TIMEBASE_RANGE_VALUE'], 'number', unit='s', positive=True, description='Horizontal range in seconds'),
            _setting('timebase_position_div', ['NI_EWB_4CH_SCOPE_TIMEBASE_POSITION_VALUE'], 'number', unit='div', description='Horizontal X position in divisions'),
            _setting('selected_channel', ['NI_EWB_4CH_SCOPE_CURRENTCHANNEL'], 'enum', enum=_SCOPE_4CH_CHANNEL_INDEX, description='Active channel selector (A, B, C, D)'),
            *_scope_4ch_channel_settings('A', 0),
            *_scope_4ch_channel_settings('B', 1),
            *_scope_4ch_channel_settings('C', 2),
            *_scope_4ch_channel_settings('D', 3),
            _setting('trigger_source', ['NI_EWB_4CH_SCOPE_TRIGGERBASE_SOURCE_MODE'], 'enum', enum=_SCOPE_4CH_TRIGGER_SOURCE, description='Trigger source type (channel or ext)'),
            _setting('trigger_channel', ['NI_EWB_4CH_SCOPE_CURRENTTRIGERCHANNEL'], 'enum', enum=_SCOPE_4CH_CHANNEL_INDEX, description='Trigger channel when trigger_source is channel (A, B, C, D)'),
            _setting('trigger_edge', ['NI_EWB_4CH_SCOPE_TRIGGERBASE_TRIGGER_EDGE'], 'enum', enum=_SCOPE_TRIGGER_EDGE, description='Trigger edge (rising or falling)'),
            _setting('trigger_level_v', ['NI_EWB_4CH_SCOPE_TRIGGERBASE_TRIGGERLEVEL'], 'number', unit='V', description='Trigger threshold voltage in volts'),
            _setting('trigger_mode', ['NI_EWB_4CH_SCOPE_TRIGGERBASE_TRIGGER_MODE'], 'enum', enum=_SCOPE_TRIGGER_MODE, description='Trigger sweep mode (auto, single, normal, none)'),
        ],
    },
    {
        'instrument': 'bode_plotter',
        'display_name': 'Bode Plotter',
        'zh_name': '波特图仪',
        'dll': 'bode.dll',
        'manager': 'bode',
        'native_type': 'BODE',
        'res_id': 2702,
        'flags': 0x200000,
        'create_kind': 'standard',
        'default_prefix': 'XBP',
        'aliases': ['bode', 'xbp', '波特图仪', '伯德图仪'],
        'pin_map': {'1': 'IN+', '2': 'IN-', '3': 'OUT+', '4': 'OUT-'},
        'export_data_formats': ['.bod'],
        'settings': [
            _setting('mode', ['NI_EWB_BODE_CONTROL_MODE'], 'enum', enum=_BODE_MODE, description='Plot mode (magnitude or phase)'),
            _setting('horizontal_scale', ['NI_EWB_HORIZONTAL_MODE'], 'enum', enum=_SCALE_LOG_LIN, description='Horizontal frequency axis scale (log or lin)'),
            _setting('vertical_scale', ['NI_EWB_VERTICAL_MODE'], 'enum', enum=_SCALE_LOG_LIN, description='Vertical axis scale (log or lin)'),
            _setting('horizontal_initial_hz', ['NI_EWB_HORZ_INITIAL_VALUE'], 'number', unit='Hz', positive=True, description='Start frequency in Hz'),
            _setting('horizontal_final_hz', ['NI_EWB_HORZ_FINAL_VALUE'], 'number', unit='Hz', positive=True, description='Stop frequency in Hz'),
            _setting('vertical_initial_db', ['NI_EWB_VERT_INITIAL_LOG_VALUE'], 'number', unit='dB', description='Vertical lower bound in log magnitude mode (dB)'),
            _setting('vertical_final_db', ['NI_EWB_VERT_FINAL_LOG_VALUE'], 'number', unit='dB', description='Vertical upper bound in log magnitude mode (dB)'),
            _setting('vertical_initial_lin', ['NI_EWB_VERT_INITIAL_LIN_VALUE'], 'number', description='Vertical lower bound in linear magnitude mode'),
            _setting('vertical_final_lin', ['NI_EWB_VERT_FINAL_LIN_VALUE'], 'number', description='Vertical upper bound in linear magnitude mode'),
            _setting('vertical_initial_phase_deg', ['NI_EWB_VERT_INITIAL_PHASE_VALUE'], 'number', unit='deg', description='Vertical lower bound in phase mode (degrees)'),
            _setting('vertical_final_phase_deg', ['NI_EWB_VERT_FINAL_PHASE_VALUE'], 'number', unit='deg', description='Vertical upper bound in phase mode (degrees)'),
            _setting('resolution_points', ['NI_EWB_RESOLUTION_POINTS'], 'int', min_value=2, max_value=100000, description='Sweep resolution point count'),
        ],
    },
    {
        'instrument': 'frequency_counter',
        'display_name': 'Frequency Counter',
        'zh_name': '频率计',
        'dll': 'freqcounter.dll',
        'manager': 'FreqCounter',
        'native_type': 'FREQCOUNTER',
        'res_id': 2,
        'flags': 0x1C0000,
        'create_kind': 'standard',
        'default_prefix': 'XFC',
        'aliases': ['freqcounter', 'freq_counter', 'xfc', '频率计'],
        'pin_map': {'1': 'IN'},
        'settings': [
            _setting('mode', ['NI_EWB_FCOUNTER_MEASUREMENT_MODE'], 'enum', enum=_FC_MODE, description='Measurement mode (frequency, period, pulse_width, rise_fall)'),
            _setting('coupling', ['NI_EWB_FCOUNTER_SIGNAL_MODE'], 'enum', enum=_SIGNAL_AC_DC, description='Input coupling (AC or DC)'),
            _setting('sensitivity_vrms', ['NI_EWB_SENSITIVITYVALUE'], 'number', unit='Vrms', min_value=0, description='RMS sensitivity voltage'),
            _setting('trigger_level_v', ['NI_EWB_TRIGGLELEVELVALUE'], 'number', unit='V', description='Trigger threshold voltage'),
            _setting('slow_signal', ['NI_EWB_PROCESSSLOWSIGNAL'], 'int', min_value=0, max_value=1, description='Slow-change signal processing flag (0 or 1)'),
            _setting('compression_rate', ['NI_EWB_COMPRESSRATE'], 'int', min_value=1, description='Slow-signal compression rate'),
        ],
    },
    {
        'instrument': 'word_generator',
        'display_name': 'Word Generator',
        'zh_name': '字信号发生器',
        'dll': 'wgen.dll',
        'manager': 'wgen',
        'native_type': 'WGEN',
        'res_id': 2713,
        'flags': 0x2E0000,
        'create_kind': 'standard',
        'default_prefix': 'XWG',
        'aliases': ['wgen', 'xwg', '字信号发生器', '字发生器'],
        'pin_map': {
            **{str(i): f'Bit {i - 1}' for i in range(1, 33)},
            '33': 'R (Ready)',
            '34': 'T (Trigger)',
        },
        'settings': [
            _setting('mode', ['NI_EWB_WGENMODE'], 'enum', enum=_WGEN_MODE, description='Run mode (step, burst, cycle)'),
            _setting('frequency_hz', ['NI_EWB_FREQUENCYVALUE'], 'number', unit='Hz', positive=True, description='Output clock frequency in Hz'),
            _setting('initial_address', ['NI_EWB_INITIALADDRESS'], 'int', min_value=0, description='Start buffer address'),
            _setting('final_address', ['NI_EWB_FINALADDRESS'], 'int', min_value=0, description='Final buffer address'),
            _setting('trigger_source', ['NI_EWB_TRIGGERSETTINGTRIGGERMODE'], 'enum', enum=_SPEC_TRIG_SOURCE, description='Trigger source (internal or external)'),
            _setting('trigger_edge', ['NI_EWB_TRIGGERSETTINGTRIGGEREDGE'], 'enum', enum=_SCOPE_TRIGGER_EDGE, description='External trigger edge (rising or falling)'),
            _setting('display_format', ['NI_EWB_CURRENTDISPLAYDATADISPLAYTYPE'], 'enum', enum=_WGEN_DISPLAY, description='Pattern display radix (hex, dec, binary, ascii)'),
            _setting('level_low_v', ['NI_EWB_LEVEL_LOW'], 'number', unit='V', description='Logic low output voltage'),
            _setting('level_high_v', ['NI_EWB_LEVEL_HIGH'], 'number', unit='V', description='Logic high output voltage'),
        ],
    },
    {
        'instrument': 'logic_converter',
        'display_name': 'Logic Converter',
        'zh_name': '逻辑转换仪',
        'dll': 'logconv.dll',
        'manager': 'logconv',
        'native_type': 'LOGCONV',
        'res_id': 8,
        'flags': 0x300000,
        'create_kind': 'standard',
        'default_prefix': 'XLC',
        'aliases': ['logconv', 'xlc', '逻辑转换仪', '逻辑转换器'],
        'pin_map': {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E', '6': 'F', '7': 'G', '8': 'H', '9': 'OUT'},
        'settings': [
            _setting('boolean_expression', ['NI_EWB_BOOL_STR'], 'string', description='Boolean expression string'),
            _setting('num_variables', ['NI_EWB_TRUTH_NUM_VARS'], 'int', min_value=0, max_value=8, description='Number of truth-table input variables'),
        ],
    },
    {
        'instrument': 'logic_analyzer',
        'display_name': 'Logic Analyzer',
        'zh_name': '逻辑分析仪',
        'dll': 'logican.dll',
        'manager': 'logican',
        'native_type': 'LOGICAN',
        'res_id': 3,
        'flags': 0x230000,
        'create_kind': 'standard',
        'default_prefix': 'XLA',
        'aliases': ['logican', 'xla', '逻辑分析仪'],
        'pin_map': {
            **{str(i): f'CH{i}' for i in range(1, 17)},
            '17': 'C (Ext Clock)',
            '18': 'Q (Clock Qualifier)',
            '19': 'T (Trigger Qualifier)',
        },
        'settings': [
            _setting('clock_source', ['NI_EWB_LOGIC_CLOCKMODE'], 'enum', enum=_LA_CLOCK_MODE, description='Sampling clock source (external or internal)'),
            _setting('clock_edge', ['NI_EWB_LOGIC_CLOCKEDGE'], 'enum', enum=_LA_CLOCK_EDGE, description='Trigger clock edge (positive, negative, both)'),
            _setting('internal_clock_rate_hz', ['NI_EWB_LOGIC_INTERNALCLOCKRATE'], 'number', unit='Hz', positive=True, description='Internal clock rate in Hz'),
            _setting('clocks_per_division', ['NI_EWB_LOGIC_TICKSPERDIVISION'], 'int', min_value=1, description='Clocks per display division'),
            _setting('pre_trigger_samples', ['NI_EWB_LOGIC_PRETRIGGERSAMPLECOUNT'], 'int', min_value=0, description='Pre-trigger sample count'),
            _setting('post_trigger_samples', ['NI_EWB_LOGIC_POSTTRIGGERSAMPLECOUNT'], 'int', min_value=1, description='Post-trigger sample count'),
            _setting('threshold_voltage_v', ['NI_EWB_LOGIC_THRESHOLDVOLTAGE'], 'number', unit='V', description='Logic input threshold voltage in volts'),
        ],
    },
    {
        'instrument': 'iv_analyzer',
        'display_name': 'IV Analyzer',
        'zh_name': '伏安特性分析仪',
        'dll': 'iv_analyzer.dll',
        'manager': 'IV_Analyzer',
        'native_type': 'IV_ANALYZER',
        'res_id': 9,
        'flags': 0x220000,
        'create_kind': 'standard',
        'default_prefix': 'XIV',
        'aliases': ['iv', 'iv_curve', 'xiv', '伏安特性分析仪', 'IV分析仪'],
        'pin_map': {'1': 'Terminal 1', '2': 'Terminal 2', '3': 'Terminal 3'},
        'settings': [
            _setting('vertical_scale', ['NI_EWB_IV_ANALYZER_VERTICAL_AXIS_TYPE'], 'enum', enum=_SCALE_LOG_LIN, description='Current axis scale (log or lin)'),
            _setting('horizontal_scale', ['NI_EWB_IV_ANALYZER_HORIZONTAL_AXIS_TYPE'], 'enum', enum=_SCALE_LOG_LIN, description='Voltage axis scale (log or lin)'),
            _setting('current_initial_a', ['NI_EWB_IV_ANALYZER_VERTICALINITIALLINVALUE'], 'number', unit='A', description='Current axis lower bound'),
            _setting('current_final_a', ['NI_EWB_IV_ANALYZER_VERTICALFINALLINVALUE'], 'number', unit='A', description='Current axis upper bound'),
            _setting('voltage_initial_v', ['NI_EWB_IV_ANALYZER_HORIZONTAL_INITIAL_VALUE'], 'number', unit='V', description='Voltage axis lower bound'),
            _setting('voltage_final_v', ['NI_EWB_IV_ANALYZER_HORIZONTAL_FINIAL_VALUE'], 'number', unit='V', description='Voltage axis upper bound'),
            _setting('component_model_index', ['NI_EWB_IV_ANALYZER_CURRENTMODELINDEX'], 'int', min_value=0, description='Selected device test configuration index'),
        ],
    },
    {
        'instrument': 'distortion_analyzer',
        'display_name': 'Distortion Analyzer',
        'zh_name': '失真分析仪',
        'dll': 'distor.dll',
        'manager': 'distor',
        'native_type': 'DISTOR',
        'res_id': 3,
        'flags': 0x1B0000,
        'create_kind': 'standard',
        'default_prefix': 'XDA',
        'aliases': ['distor', 'thd', 'thd_analyzer', 'xda', '失真分析仪', '谐波失真分析仪'],
        'pin_map': {'1': 'IN'},
        'readout_keys': {
            'distortion_value': 'NI_EWB_CURRENTDISPLAYDATA_DISTORTIONVALUE',
            'resolution': 'NI_EWB_CURRENTDISPLAYDATA_RESOLUTION',
        },
        'settings': [
            _setting('mode', ['NI_EWB_CONTROL_MODE'], 'enum', enum=_DISTOR_MODE, description='Measurement mode (thd or sinad)'),
            _setting('display_unit', ['NI_EWB_DISPLAY_MODE'], 'enum', enum=_DISTOR_DISPLAY, description='Display unit (percent or db)'),
            _setting('fundamental_frequency_hz', ['NI_EWB_FREQUENCY_FUNDAMENTAL'], 'number', unit='Hz', positive=True, description='Fundamental frequency in Hz'),
            _setting('thd_formula', ['NI_EWB_THD_FORMULA'], 'enum', enum=_DISTOR_FORMULA, description='THD formula standard (ieee or ansi_iec)'),
            _setting('harmonics', ['NI_EWB_HARMONIC_SETTING'], 'int', min_value=2, max_value=100, description='Number of harmonics included'),
            _setting('fft_points', ['NI_EWB_MAX_INTERVALSPERPERIOD'], 'int', min_value=16, description='Maximum FFT points per period'),
        ],
    },
    {
        'instrument': 'spectrum_analyzer',
        'display_name': 'Spectrum Analyzer',
        'zh_name': '频谱分析仪',
        'dll': 'spec_an.dll',
        'manager': 'spec_an',
        'native_type': 'SPEC_AN',
        'res_id': 5,
        'flags': 0x2B0000,
        'create_kind': 'standard',
        'default_prefix': 'XSA',
        'aliases': ['spec_an', 'spectrum', 'xsa', '频谱分析仪'],
        'pin_map': {'1': 'IN', '2': 'T (Trigger)'},
        'settings': [
            _setting('span_mode', ['NI_EWB_SPEC_ANALYZER_SPANMODE'], 'enum', enum=_SPEC_SPAN_MODE, description='Frequency span mode (set_span, zero_span, full_span)'),
            _setting('start_frequency_hz', ['NI_EWB_SPEC_ANALYZER_FREQUENCYSTARTVALUE'], 'number', unit='Hz', min_value=0, description='Start frequency in Hz'),
            _setting('end_frequency_hz', ['NI_EWB_SPEC_ANALYZER_FREQUENCYENDVALUE'], 'number', unit='Hz', positive=True, description='End frequency in Hz'),
            _setting('resolution_frequency_hz', ['NI_EWB_SPEC_ANALYZER_RESOLUTIONFREQUENCYVALUE'], 'number', unit='Hz', positive=True, description='Resolution bandwidth frequency in Hz'),
            _setting('vertical_mode', ['NI_EWB_SPEC_ANALYZER_VERTICALMODE'], 'enum', enum=_SPEC_VERT_MODE, description='Amplitude scale mode (db, dbm, lin)'),
            _setting('range_db', ['NI_EWB_SPEC_ANALYZER_DIVISIONVALUELOG'], 'number', unit='dB/div', positive=True, description='Log vertical division value in dB'),
            _setting('range_lin', ['NI_EWB_SPEC_ANALYZER_DIVISIONVALUELIN'], 'number', unit='V/div', positive=True, description='Linear vertical division value in V'),
            _setting('reference_level', ['NI_EWB_SPEC_ANALYZER_LEVELVALUE'], 'number', description='Reference level'),
            _setting('trigger_source', ['NI_EWB_SPEC_ANALYZER_TRIGGERSOURCE'], 'enum', enum=_SPEC_TRIG_SOURCE, description='Trigger source (internal or external)'),
            _setting('trigger_mode', ['NI_EWB_SPEC_ANALYZER_TRIGGERMODE'], 'enum', enum=_SPEC_TRIG_MODE, description='Trigger mode (continuous or single)'),
            _setting('threshold_voltage_v', ['NI_EWB_SPEC_ANALYZER_THRESHOLDVOLTAGE'], 'number', unit='V', description='External trigger threshold voltage'),
            _setting('fft_points', ['NI_EWB_SPEC_ANALYZER_MAXINTERVALSPERPERIOD'], 'int', min_value=16, description='FFT point count'),
        ],
    },
    {
        'instrument': 'network_analyzer',
        'display_name': 'Network Analyzer',
        'zh_name': '网络分析仪',
        'dll': 'netan.dll',
        'manager': 'netan',
        'native_type': 'NETAN',
        'res_id': 3,
        'flags': 0x260000,
        'create_kind': 'standard',
        'default_prefix': 'XNA',
        'aliases': ['netan', 'vna', 'xna', '网络分析仪'],
        'pin_map': {'1': 'P1 (Port 1)', '2': 'P2 (Port 2)'},
        'settings': [
            _setting('start_frequency_hz', ['NI_EWB_STARTFREQ'], 'number', unit='Hz', positive=True, description='Sweep start frequency in Hz'),
            _setting('stop_frequency_hz', ['NI_EWB_STOPFREQ'], 'number', unit='Hz', positive=True, description='Sweep stop frequency in Hz'),
            _setting('characteristic_impedance_ohm', ['NI_EWB_ZO'], 'number', unit='Ohm', positive=True, description='Reference port impedance Z0 in ohms'),
            _setting('points', ['NI_EWB_NOOFPOINTS'], 'int', min_value=2, description='Number of sweep points'),
            _setting('sweep_type', ['NI_EWB_SWEEPTYPE'], 'enum', enum=_NETAN_SWEEP, description='Frequency sweep type (linear or log)'),
        ],
    },
    {
        'instrument': 'agilent_function_generator',
        'display_name': 'Agilent Function Generator (33120A)',
        'zh_name': '安捷伦函数发生器',
        'dll': 'fgen_at.dll',
        'manager': 'fgen_AT',
        'native_type': 'FGEN_AT',
        'res_id': 27,
        'flags': 0x1D0000,
        'create_kind': 'standard',
        'default_prefix': 'XFG',
        'aliases': ['fgen_at', 'agilent_fgen', '33120a', 'agilent_33120a', '安捷伦函数发生器'],
        'pin_map': {'1': 'Output', '2': 'Sync'},
        'settings': [
            _setting('power_on', ['NI_EWB_POWERBUTTON_ON'], 'int', min_value=0, max_value=1, description='Front-panel power button state (0=off, 1=on)'),
        ],
    },
    {
        'instrument': 'agilent_multimeter',
        'display_name': 'Agilent Multimeter (34401A)',
        'zh_name': '安捷伦万用表',
        'dll': 'mulmeter_at.dll',
        'manager': 'Mulmeter_AT',
        'native_type': 'MULMETER_AT',
        'res_id': 3,
        'flags': 0x240000,
        'create_kind': 'standard',
        'default_prefix': 'XMM',
        'aliases': ['mulmeter_at', 'agilent_dmm', '34401a', 'agilent_34401a', '安捷伦万用表'],
        'pin_map': {'1': 'HI (V/Ohm/Freq)', '2': 'LO (COM)', '3': 'I (Amps)', '4': '4W Sense HI', '5': '4W Sense LO'},
        'readout_keys': {
            'dc_voltage': 'NI_EWB_DC_VOLTAGE',
            'ac_voltage': 'NI_EWB_AC_VOLTAGE',
            'frequency': 'NI_EWB_FREQ_VALUE',
        },
        'settings': [
            _setting('power_on', ['NI_EWB_POWERBUTTONON'], 'int', min_value=0, max_value=1, description='Front-panel power state (0=off, 1=on)'),
            _setting('mode', ['NI_EWB_CURRENTMODE'], 'int', min_value=0, description='Native Agilent 34401A mode index'),
            _setting('function', ['NI_EWB_CURRENTFUNCT'], 'int', min_value=0, description='Native Agilent 34401A function index'),
        ],
    },
    {
        'instrument': 'agilent_oscilloscope',
        'display_name': 'Agilent Oscilloscope (54622D)',
        'zh_name': '安捷伦示波器',
        'dll': 'scope_at.dll',
        'manager': 'scope_AT',
        'native_type': 'SCOPE_AT',
        'res_id': 58,
        'flags': 0x280000,
        'create_kind': 'standard',
        'default_prefix': 'XSC',
        'aliases': ['scope_at', 'agilent_scope', '54622d', 'agilent_54622d', '安捷伦示波器'],
        'pin_map': {
            '1': 'CH1',
            '2': 'CH2',
            '3': 'Ext Trig',
            '4': 'GND',
            '5': 'Probe Comp / Sync',
            **{str(i): f'D{i - 6}' for i in range(6, 22)},
        },
        'settings': [
            _setting('power_on', ['NI_EWB_ATSCOPE_POWERBUTTONON'], 'int', min_value=0, max_value=1, description='Front-panel power state (0=off, 1=on)'),
            _setting('channel_a_enabled', ['NI_EWB_CHANNELENABLETRACEA'], 'int', min_value=0, max_value=1, description='Enable Channel 1 trace (0 or 1)'),
            _setting('channel_b_enabled', ['NI_EWB_CHANNELENABLETRACEB'], 'int', min_value=0, max_value=1, description='Enable Channel 2 trace (0 or 1)'),
            _setting('trigger_level_a_v', ['NI_EWB_TRIGLEVELVALUE_A'], 'number', unit='V', description='Channel 1 trigger level in volts'),
            _setting('trigger_level_b_v', ['NI_EWB_TRIGLEVELVALUE_B'], 'number', unit='V', description='Channel 2 trigger level in volts'),
            _setting('trigger_level_ext_v', ['NI_EWB_TRIGLEVELVALUEEXT'], 'number', unit='V', description='External trigger level in volts'),
            _setting('holdoff_time_s', ['NI_EWB_HOLDOFFTIME'], 'number', unit='s', positive=True, description='Trigger holdoff time in seconds'),
        ],
    },
    {
        'instrument': 'tektronix_oscilloscope',
        'display_name': 'Tektronix Oscilloscope (TDS 2024)',
        'zh_name': '泰克示波器',
        'dll': 'scope_tk.dll',
        'manager': 'scope_tk',
        'native_type': 'SCOPE_TK',
        'res_id': 27,
        'flags': 0x340000,
        'create_kind': 'standard',
        'default_prefix': 'XSC',
        'aliases': ['scope_tk', 'tektronix_scope', 'tek_scope', 'tds2024', 'tektronix', '泰克示波器'],
        'pin_map': {'1': 'CH1', '2': 'CH2', '3': 'CH3', '4': 'CH4', '5': 'T (Ext Trig)', '6': 'P (Probe Comp)', '7': 'G (GND)'},
        'settings': [
            _setting('power_on', ['NI_EWB_TKSCOPE_POWERBUTTONON'], 'int', min_value=0, max_value=1, description='Front-panel power state (0=off, 1=on)'),
            _setting('trigger_level_v', ['NI_EWB_TKSCOPE_TRIGLEVELVALUE'], 'number', unit='V', description='Trigger level in volts'),
            _setting('holdoff_time_s', ['NI_EWB_TKSCOPE_HOLDOFFTIME'], 'number', unit='s', positive=True, description='Trigger holdoff time in seconds'),
            _setting('channel_1_coupling', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_A', 'NI_EWB_GETCOUPLINGTYPE'], 'int', min_value=0, description='Channel 1 coupling mode'),
            _setting('channel_1_invert', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_A', 'NI_EWB_INVERT'], 'int', min_value=0, max_value=1, description='Channel 1 invert flag (0 or 1)'),
            _setting('channel_2_coupling', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_B', 'NI_EWB_GETCOUPLINGTYPE'], 'int', min_value=0, description='Channel 2 coupling mode'),
            _setting('channel_2_invert', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_B', 'NI_EWB_INVERT'], 'int', min_value=0, max_value=1, description='Channel 2 invert flag (0 or 1)'),
            _setting('channel_3_coupling', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_C', 'NI_EWB_GETCOUPLINGTYPE'], 'int', min_value=0, description='Channel 3 coupling mode'),
            _setting('channel_3_invert', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_C', 'NI_EWB_INVERT'], 'int', min_value=0, max_value=1, description='Channel 3 invert flag (0 or 1)'),
            _setting('channel_4_coupling', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_D', 'NI_EWB_GETCOUPLINGTYPE'], 'int', min_value=0, description='Channel 4 coupling mode'),
            _setting('channel_4_invert', ['NI_EWB_TKSCOPE_SAMPLINGDATACOUPLING_D', 'NI_EWB_INVERT'], 'int', min_value=0, max_value=1, description='Channel 4 invert flag (0 or 1)'),
        ],
    },
    {
        'instrument': 'current_probe',
        'display_name': 'Current Probe (Current Clamp)',
        'zh_name': '电流探针',
        'dll': 'imeter.dll',
        'manager': 'IMeter',
        'native_type': 'IMETER',
        'res_id': 1,
        'flags': 0x3F0000,
        'create_kind': 'imeter',
        'default_prefix': 'XCP',
        'aliases': ['imeter', 'current_clamp', 'clamp', 'xcp', '电流探针', '电流钳'],
        'pin_map': {'1': 'I+', '2': 'I-', '3': 'Vout'},
        'settings': [
            _setting('ratio_v_per_ma', ['NI_EWB_RATIOVALUE'], 'number', unit='V/mA', positive=True, description='Output voltage-to-current ratio in V/mA (1.0 = 1 V/mA = 1000 V/A)'),
        ],
    },
]

_BY_KEY: dict[str, dict[str, Any]] = {entry['instrument']: entry for entry in INSTRUMENT_CATALOG}
_BY_MANAGER: dict[str, dict[str, Any]] = {entry['manager'].casefold(): entry for entry in INSTRUMENT_CATALOG}
_BY_NATIVE_TYPE: dict[str, dict[str, Any]] = {entry['native_type'].casefold(): entry for entry in INSTRUMENT_CATALOG}
_BY_LOOKUP: dict[str, dict[str, Any]] = {}
for _entry in INSTRUMENT_CATALOG:
    for _token in (
        _entry['instrument'],
        _entry['display_name'],
        _entry['zh_name'],
        _entry['manager'],
        _entry['native_type'],
        _entry['dll'],
        _entry['dll'].removesuffix('.dll'),
        *_entry.get('aliases', []),
    ):
        _BY_LOOKUP[_token.casefold()] = _entry
        _BY_LOOKUP[re.sub(r'[\s\-]+', '_', _token.strip()).casefold()] = _entry


# Properties that reflect transient GUI geometry, live simulation display values, or
# uninitialized pre-simulation color buffers rather than persistent user configuration.
_VOLATILE_EXACT = {
    'NI_EWB_SHOW_WINDOW_STATUS',
    'NI_EWB_DIALOG_STATUS',
    'NI_EWB_CIRCUIT_NAME',
    'NI_EWB_4CH_SCOPE_CIRCUIT_NAME',
    'NI_EWB_BODE_CIRCUIT_NAME',
    'NI_EWB_SPEC_ANALYZER_BACKFOURIERTRANREPARTS',
    'NI_EWB_SPEC_ANALYZER_HASSERIALIZERESTOREDATA',
    'NI_EWB_PIN_COLORS',
    'NI_EWB_PIN_LABELS',
    'NI_EWB_4CH_SCOPE_PIN_COLORS',
    'NI_EWB_4CH_SCOPE_PIN_LABELS',
    'NI_EWB_PIN_COLOR_MAIN',
    'NI_EWB_LOGIC_PIN_COLORS',
    'NI_EWB_LOGIC_PIN_LABELS',
    'NI_EWB_SPEC_ANALYZER_PIN_COLORS',
    'NI_EWB_SPEC_ANALYZER_PIN_LABELS',
    'NI_EWB_ATMETER_PIN_COLORS',
    'NI_EWB_DC_VOLTAGE',
    'NI_EWB_AC_VOLTAGE',
    'NI_EWB_FREQ_VALUE',
    'NI_EWB_DC_REF_VOLTAGE',
    'NI_EWB_DC_REF_VOLTAGE_DT',
}


def _is_volatile_property(name: str) -> bool:
    if name in _VOLATILE_EXACT:
        return True
    upper = name.upper()
    return (
        'CURRENTDISPLAYDATA' in upper
        or 'CURRENT_DISPLAY_' in upper
        or 'CURSORPOS' in upper
        or 'CURSOR_POS' in upper
    )


def _strip_typed_value(node: Any) -> Any:
    if isinstance(node, dict) and 'native_type' in node and 'value' in node:
        val = node['value']
        if node.get('type') == 'map' and isinstance(val, dict):
            return {k: _strip_typed_value(v) for k, v in val.items()}
        if node.get('type') == 'array' and isinstance(val, list):
            return [_strip_typed_value(v) for v in val]
        return val
    return node


def filter_persistent_instrument_props(raw_props: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep only deterministic configuration properties for reopen verification."""
    if not isinstance(raw_props, dict):
        return None
    cleaned: dict[str, Any] = {}
    for key, val in raw_props.items():
        if _is_volatile_property(key):
            continue
        cleaned[key] = _strip_typed_value(val)
    return cleaned


def resolve_instrument(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not name.strip() or '\0' in name:
        raise ValueError('Instrument name must be a non-empty string')
    key = name.strip().casefold()
    norm = re.sub(r'[\s\-]+', '_', key)
    entry = _BY_LOOKUP.get(key) or _BY_LOOKUP.get(norm)
    if entry is None:
        available = ', '.join(item['instrument'] for item in INSTRUMENT_CATALOG)
        raise ValueError(f'Unknown virtual instrument {name!r}; available instruments: {available}')
    return entry


def lookup_by_native(manager: str | None = None, native_type: str | None = None) -> dict[str, Any] | None:
    if manager and manager.casefold() in _BY_MANAGER:
        return _BY_MANAGER[manager.casefold()]
    if native_type and native_type.casefold() in _BY_NATIVE_TYPE:
        return _BY_NATIVE_TYPE[native_type.casefold()]
    return None


def public_setting_descriptors(entry: dict[str, Any]) -> list[dict[str, Any]]:
    descriptors = []
    for spec in entry.get('settings', []):
        item: dict[str, Any] = {
            'name': spec['name'],
            'type': spec['kind'],
            'native_path': _format_native_path(spec['path']),
        }
        if 'unit' in spec:
            item['unit'] = spec['unit']
        if 'enum' in spec:
            item['values'] = list(spec['enum']['by_code'].values())
        if 'description' in spec:
            item['description'] = spec['description']
        descriptors.append(item)
    return descriptors


def catalog_entry_view(entry: dict[str, Any], *, include_descriptors: bool = True) -> dict[str, Any]:
    view: dict[str, Any] = {
        'instrument': entry['instrument'],
        'display_name': entry['display_name'],
        'zh_name': entry['zh_name'],
        'default_prefix': entry['default_prefix'],
        'dll': entry['dll'],
        'aliases': entry.get('aliases', []),
        'pin_map': entry['pin_map'],
    }
    if entry.get('export_data_formats'):
        view['export_data_formats'] = entry['export_data_formats']
    if entry.get('readout_keys'):
        view['readouts'] = list(entry['readout_keys'].keys())
    if include_descriptors:
        view['settings'] = public_setting_descriptors(entry)
    return view


def search_instruments(query: str = '') -> list[dict[str, Any]]:
    q = (query or '').strip().casefold()
    if not q:
        return [catalog_entry_view(entry) for entry in INSTRUMENT_CATALOG]
    matches = []
    for entry in INSTRUMENT_CATALOG:
        haystack = ' '.join([
            entry['instrument'],
            entry['display_name'],
            entry['zh_name'],
            entry['default_prefix'],
            entry['manager'],
            entry['native_type'],
            entry['dll'],
            *entry.get('aliases', []),
        ]).casefold()
        if q in haystack:
            matches.append(catalog_entry_view(entry))
    return matches


def _format_native_path(path: list[str | int]) -> str:
    out = ''
    for token in path:
        if isinstance(token, int):
            out += f'[{token}]'
        else:
            out = f'{out}.{token}' if out else token
    return out


def parse_native_path(expr: str) -> list[str | int]:
    """Parse 'NI_EWB_4CH_SCOPE_CHANNELS[0].NI_EWB_4CH_SCOPE_CHANNELSCALEVALUE' into tokens."""
    if not isinstance(expr, str) or not expr.strip() or '\0' in expr:
        raise ValueError('Property path must be a non-empty string')
    tokens: list[str | int] = []
    pos = 0
    pattern = re.compile(r'(?:^|\.)([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]')
    for match in pattern.finditer(expr):
        if match.start() != pos:
            raise ValueError(f'Invalid native property path: {expr!r}')
        if match.group(1) is not None:
            tokens.append(match.group(1))
        else:
            tokens.append(int(match.group(2)))
        pos = match.end()
    if pos != len(expr) or not tokens or not isinstance(tokens[0], str):
        raise ValueError(f'Invalid native property path: {expr!r}')
    return tokens


def _get_raw_at_path(raw_props: dict[str, Any], path: list[str | int]) -> Any:
    current: Any = raw_props
    for idx, token in enumerate(path):
        if idx == 0:
            if not isinstance(current, dict) or token not in current:
                return None
            current = current[token]
            continue
        if isinstance(current, dict) and 'native_type' in current and 'value' in current:
            current = current['value']
        if isinstance(token, int):
            if not isinstance(current, list) or not (0 <= token < len(current)):
                return None
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return None
            current = current[token]
    return current


def format_instrument_settings(
    entry: dict[str, Any] | None,
    raw_props: dict[str, Any],
    *,
    include_raw: bool = False,
) -> dict[str, Any]:
    friendly: dict[str, Any] = {}
    readouts: dict[str, Any] = {}
    if entry:
        for spec in entry.get('settings', []):
            node = _get_raw_at_path(raw_props, spec['path'])
            if node is None:
                continue
            raw_val = _strip_typed_value(node)
            if spec['kind'] == 'enum' and 'enum' in spec:
                friendly[spec['name']] = spec['enum']['by_code'].get(raw_val, raw_val)
            else:
                friendly[spec['name']] = raw_val
        for rkey, native_name in entry.get('readout_keys', {}).items():
            node = raw_props.get(native_name)
            if node is not None:
                val = _strip_typed_value(node)
                readouts[rkey] = val.strip() if isinstance(val, str) else val
    result: dict[str, Any] = {
        'settings': friendly,
        'descriptors': public_setting_descriptors(entry) if entry else [],
    }
    if readouts:
        result['readouts'] = readouts
    # Always include raw_properties when requested or when no friendly settings exist for this instrument.
    if include_raw or not (entry and entry.get('settings')):
        result['raw_properties'] = raw_props
    return result


def _coerce_setting_value(spec: dict[str, Any], value: Any) -> Any:
    kind = spec['kind']
    name = spec['name']
    if kind == 'enum':
        enum = spec['enum']
        if isinstance(value, bool):
            key = 'true' if value else 'false'
            if key in enum['to_code']:
                return enum['to_code'][key]
            raise ValueError(f'{name} does not accept boolean {value!r}; expected one of {list(enum["by_code"].values())}')
        if isinstance(value, int):
            if value in enum['by_code']:
                return value
            raise ValueError(f'{name} code {value!r} is invalid; expected one of {list(enum["by_code"].values())} or codes {list(enum["by_code"].keys())}')
        if isinstance(value, str):
            norm = re.sub(r'[\s\-]+', '_', value.strip()).casefold()
            code = enum['to_code'].get(value.strip().casefold())
            if code is None:
                code = enum['to_code'].get(norm)
            if code is not None:
                return code
            raise ValueError(f'Unknown value {value!r} for {name}; expected one of {list(enum["by_code"].values())}')
        raise ValueError(f'Invalid value {value!r} for {name}; expected one of {list(enum["by_code"].values())}')
    if kind == 'number':
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{name} must be a finite number')
        num = float(value)
        if spec.get('positive') and num <= 0:
            raise ValueError(f'{name} must be positive')
        if 'min' in spec and num < spec['min']:
            raise ValueError(f'{name} must be >= {spec["min"]}')
        if 'max' in spec and num > spec['max']:
            raise ValueError(f'{name} must be <= {spec["max"]}')
        return num
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an integer')
        if 'min' in spec and value < spec['min']:
            raise ValueError(f'{name} must be >= {spec["min"]}')
        if 'max' in spec and value > spec['max']:
            raise ValueError(f'{name} must be <= {spec["max"]}')
        return value
    if kind == 'string':
        if not isinstance(value, str) or '\0' in value:
            raise ValueError(f'{name} must be a string without NUL bytes')
        return value
    return value


def _validate_raw_scalar(key: str, value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
        return value
    if isinstance(value, str):
        if '\0' in value:
            raise ValueError(f'{key} must not contain NUL bytes')
        return value
    raise ValueError(f'Unsupported value type for {key}: {type(value).__name__}')


def compile_instrument_settings(entry: dict[str, Any] | None, settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate friendly settings and/or native NI_EWB_* property paths into native writes."""
    if not isinstance(settings, dict) or not settings:
        raise ValueError('settings must be a non-empty mapping')
    by_friendly = {spec['name']: spec for spec in (entry.get('settings', []) if entry else [])}
    writes: list[dict[str, Any]] = []
    seen_paths: set[tuple[str | int, ...]] = set()

    def add_write(path: list[str | int], value: Any, source_key: str) -> None:
        key_tuple = tuple(path)
        if key_tuple in seen_paths:
            raise ValueError(f'Duplicate setting target for {_format_native_path(path)!r}')
        seen_paths.add(key_tuple)
        writes.append({'path': path, 'value': value, 'source_key': source_key})

    def expand_nested_raw(prefix: list[str | int], obj: Any, source_key: str) -> None:
        if isinstance(obj, dict):
            if not obj:
                raise ValueError(f'{source_key} mapping must not be empty')
            for sub_key, sub_val in obj.items():
                if isinstance(sub_key, int):
                    expand_nested_raw([*prefix, sub_key], sub_val, f'{source_key}[{sub_key}]')
                elif isinstance(sub_key, str) and sub_key.isdigit():
                    expand_nested_raw([*prefix, int(sub_key)], sub_val, f'{source_key}[{sub_key}]')
                else:
                    expand_nested_raw([*prefix, str(sub_key)], sub_val, f'{source_key}.{sub_key}')
        elif isinstance(obj, list):
            if not obj:
                raise ValueError(f'{source_key} list must not be empty')
            for idx, item in enumerate(obj):
                expand_nested_raw([*prefix, idx], item, f'{source_key}[{idx}]')
        else:
            add_write(prefix, _validate_raw_scalar(source_key, obj), source_key)

    for raw_key, raw_value in settings.items():
        if not isinstance(raw_key, str) or not raw_key.strip() or '\0' in raw_key:
            raise ValueError('Setting key must be a non-empty string')
        key = raw_key.strip()
        if key in by_friendly:
            spec = by_friendly[key]
            coerced = _coerce_setting_value(spec, raw_value)
            add_write(list(spec['path']), coerced, key)
            continue
        # Support nested convenience objects on 4-channel oscilloscope: channel_a: {scale_v_per_div: 2, coupling: 'DC'}
        if entry and entry['instrument'] == 'oscilloscope_4ch' and key in ('channel_a', 'channel_b', 'channel_c', 'channel_d') and isinstance(raw_value, dict):
            for sub_key, sub_val in raw_value.items():
                full_key = f'{key}_{sub_key}'
                if full_key not in by_friendly:
                    valid_sub = [k.removeprefix(f'{key}_') for k in by_friendly if k.startswith(f'{key}_')]
                    raise ValueError(f'Unknown {key} field {sub_key!r}; available: {", ".join(valid_sub)}')
                spec = by_friendly[full_key]
                add_write(list(spec['path']), _coerce_setting_value(spec, sub_val), full_key)
            continue
        if key.startswith('NI_EWB_'):
            path = parse_native_path(key)
            if isinstance(raw_value, (dict, list)):
                expand_nested_raw(path, raw_value, key)
            else:
                add_write(path, _validate_raw_scalar(key, raw_value), key)
            continue
        available = ', '.join(by_friendly.keys()) or 'native NI_EWB_* property keys (read via native_get_instrument_settings)'
        inst_name = entry['instrument'] if entry else 'instrument'
        raise ValueError(f'Unknown setting {key!r} for {inst_name}; available friendly settings: {available}; raw NI_EWB_* property names are also accepted')

    return writes
