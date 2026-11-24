# Simulation and verification

For analysis plus acceptance, put measurements and criteria on a workflow `analysis` stage. For existing samples use `verify`. The tools below support individual analysis and diagnosis; see [workflows.md](workflows.md) for combined execution.

## Analysis and raw data

- `native_run_analysis(analysis: "op")` runs a DC operating point. For transient analysis use `analysis: "tran"`, `step` and `stop` in seconds. Time and sample counts have no MCP workload ceiling; use finite positive values with step no larger than stop.
- `use_initial_conditions: true` selects transient UIC; choose it based on circuit startup requirements, not as an automatic response to every convergence failure.
- `native_run_ac_sweep` takes `sweep: "lin" | "dec" | "oct"`, `points`, `start_hz` and `stop_hz`. `lin` uses a total point count; the others use points per decade or octave. Configure the source's AC magnitude first.
- `native_run_dc_sweep(source, start, stop, step)` sweeps an independent voltage or current source (such as `V1`) across DC values and exports RAW/CSV artifacts.
- `native_resolve_signal(component_ref, pin)` resolves a pin to its exact SPICE vector name (`V(...)`).
- Results include `vectors`, `raw_path`, `csv_path`, `netlist_path` and `diagnostic_path`. Inspect actual source values and waveform metadata when results disagree with circuit expectations. Preserve raw numeric values; do not scale large currents to force a match.
- `native_read_waveform` accepts `offset`, `limit` and `plot_index`. Appended digital-node plots contain transition records `[time, rising, falling]`, not ordinary voltage samples.
- `native_plot_waveform` writes SVG or PNG based on `output_path`. Use `overlay: true` for same-unit traces on one axis, or `reference` for a dual-panel AC Bode plot (dB and degrees vs. frequency).
- For longer multi-stage work, use a workflow and wait with `native_workflow_status(wait_timeout: 30)`. When controlling an individual analysis independently, use `native_start_analysis`, then `native_analysis_status`. `native_control_analysis` requests `pause`, `resume` or `stop`; verify the resulting state instead of treating the acknowledgment as completion.

## Measurement and acceptance schema

Pass the analysis's actual `raw_path` to `native_verify_waveform`:

```json
{
  "raw_path": "C:/Circuits/results/analysis.raw",
  "measurements": [
    {"id":"output","metric":"mean","signal":"V(2)","start":0.001,"stop":0.01},
    {"id":"supply_current","metric":"mean","signal":"I(V1)","start":0.001,"stop":0.01}
  ],
  "criteria": [
    {"id":"output","target":6,"absolute_tolerance":0.01},
    {"id":"supply_current","target":-0.006,"absolute_tolerance":0.00001}
  ]
}
```

This example assumes a 12 V divider with two 1 kΩ resistors and a transient run covering the window. Replace `V(2)` with the actual output vector and respect the source-current sign convention. For an operating point, omit the time window.

Measurements require `id`, `metric` and `signal`. Real/time metrics are `min`, `max`, `mean`, `rms`, `peak_to_peak`, `frequency`, `duty_cycle`, `period`, `rise_time` (10%–90%), `fall_time` (90%–10%), `overshoot` (%) and `value_at` (requires `at`). Optional fields include `start`, `stop`, crossing `threshold`, and `plot_index` (which also supports digital-node event plots); duty cycle is a fraction from 0 to 1. Mean and RMS use the actual adaptive time grid. `native_measure_waveform` computes measurements without acceptance criteria.

`settling_time` measures seconds from the transient window start to the last entry into the settling band. Set `tolerance` as a fraction of the step size (default `0.02`) and optionally set `final_value`; the default target is the last sample. With the RAW-generating circuit open, both standalone measurement and verification accept `{"component_ref":"R2","pin":"1"}` for `signal` or `reference`. Vector names work offline.

Criteria use the same `id` as measurements and specify `min` / `max`, or `target` with `absolute_tolerance` / `relative_tolerance`. The older criterion key `measurement` is also accepted. AC metrics `gain_db`, `phase_deg` and `magnitude` need `frequency_hz` (`gain_db`/`phase_deg` also need `reference`; `magnitude` accepts optional `reference`), while `bandwidth_3db` (-3 dB cutoff Hz) and `phase_margin` (unity-gain phase margin in degrees) require `reference`:

```json
{"id":"gain","metric":"gain_db","signal":"V(2)","reference":"V(1)","frequency_hz":1000}
```

## Scanned seven-segment displays

Use `native_decode_seven_segment` with `digits` in display order. Each digit has `label`, seven `segments` vector names in **a,b,c,d,e,f,g** order, and a `select` vector. Derive vectors, thresholds and active polarities from the actual circuit; segment-current thresholds are in amperes, voltage thresholds in volts.

Set `start` and `stop` to include multiple complete scan cycles. `settling` skips the beginning of each selection interval; `min_dwell` sets the minimum accumulated duration of a sustained pattern. Pass the requested string through `expected`, then inspect per-digit patterns, durations and selection conflicts. A single correct frame is not proof of stable scanning.

## Parameter sweeps and persistent experiments

Use `native_run_parameter_sweep` for synchronous work or `native_start_experiment` for a persisted background job. Input shape:

```json
{
  "parameters":[{"ref":"R1","index":1,"values":[500,1000,2000]}],
  "analysis":{"analysis":"op"},
  "measurements":[{"id":"output","metric":"mean","signal":"V(2)"}],
  "criteria":[{"id":"output","min":4,"max":8}],
  "objective":{"measurement":"output","goal":"target","target":6}
}
```

Resolve the component's real value index before sweeping, or supply `name` / `role` instead of `index` (`component_ref` is accepted as an alias for `ref`). Analysis supports `op`, `tran`, `ac` and `dc` (`dc_source`, `dc_start`, `dc_stop`, `dc_step`). Parameter and Cartesian trial counts have no MCP ceiling. Goals are `min`, `max` and `target` (using `id` or `measurement`); `result.best` is the zero-based index of the best feasible trial. Original numeric values and expressions are restored after execution; applying the selected candidate is a separate edit.

While a background experiment is active, inspect it with `native_experiment_status` or `native_list_experiments`, or request cancellation with `native_cancel_experiment`. Wait for terminal status and parameter restoration before editing. Save the source circuit before running a job that must be retryable. To retry, save any desired current edits, close the active session, then call `native_retry_experiment`; it opens the saved source in a new copy and returns a new ID linked by `retry_of`.

## Experiment reports

`native_export_experiment_report` accepts a saved completed `experiment_id`, an existing absolute `output_directory`, `language: "zh" | "en"`, optional `title` and the requested `signals`. It exports standalone HTML, Markdown, measurement CSV, native schematic PNG and waveform SVG. A normal analysis call does not create a persistent experiment record for this tool.

## Interactive simulation

`native_control_interactive` accepts `start`, `pause`, `resume`, `stop` and `wait_timeout` (any finite nonnegative duration). Use `transition_confirmed` to check actual completion. `simulation_time_s` comes from the native status bar and may be rounded. `native_interactive_status(include_displays: true)` reads seven-segment and `DCD_HEX` segments and decoded digits, LED `lit` and `state`, `PROBE_DIG` logic `level` (`0`, `1`, or `null` when unconnected), and live `instrument_readouts` from placed virtual instruments (Multimeter, Wattmeter, Distortion Analyzer). Use `native_get_instrument_settings` during or after simulation to read live instrument readouts, and `native_export_instrument_data` to export `.scp` (2-Ch/4-Ch Oscilloscope) or `.bod` (Bode Plotter) trace files after running interactive simulation.

`native_configure_interactive(time_step: 0.001, max_time_step: 0.001, real_time: true)` writes native document settings by default; use persist:false for temporary overrides. Document settings persist on normal save/close; subsequent `native_save_copy` preserves them for ordinary Multisim starts after reopening. Read document settings with `persist: true` and no values. To save immediately, add `save_to_source: true` to back up and replace it after independent native reopen verification. `saved_to_file: false` indicates that only the editable document was changed. Source conflicts stop replacement. `persist: true, reset: true` restores automatic steps and real-time pacing in the document; save it to retain the reset. Numeric analysis definitions and other solver options are preserved. Persistent changes clear temporary overrides so they cannot mask the document values.

Capture the current native runtime image with `native_export_interactive_image`; it shares the static export's region, DPI and frame options. Set `active_component` to wait for that display's lit scan phase. The result includes the actual `display_states`, `simulation` and `capture_mode: instantaneous`. No display states are synthesized. Resume a paused simulation before waiting for a different phase. Stop interactive simulation before numeric analysis, netlist generation or circuit edits.

## Persistent native analysis settings

Read `native_simulation_settings(scope: analysis, analysis_type: TRAN)` to discover actual native scalar paths, types, solver-option enabled states and revision. Use `scope: interactive` for interactive/instrument defaults. `changes` edits existing fields; `solver_options` enables typed tolerances, integration, convergence, temperature and flags while selecting native custom options. Use null/false to disable an option. Integer path tokens select duplicate labels and require `expected_revision`. The API does not create empty native lists or new analysis instances.

`native_run_analysis`, `native_start_analysis` and `native_run_ac_sweep` accept `persist:true` to retain explicit run settings, with optional `save_to_source:true` to back up and verify-save before execution. Alternatively `use_saved_settings:true` runs stored OP/AC/TRAN settings using native-compiled solver commands; it is exclusive with persist. RAW/CSV results remain external files. `native_save_source` saves all current native edits, including configured settings; plain catalog reads return `saved_to_file:false` because they do not save. The root window caption follows the filename; the native page name is persisted separately.

Use `native_persistence_capabilities` for exact ownership of every tool. Application wiring preferences, runtime state, export rendering flags and MCP experiment/workflow records are not circuit-file simulation settings.

Hidden CMOS/TTL bridge power nodes are checked in generated SPICE. `native_check_netlist` adds structured `diagnostics` for missing external rail connections or provably floating DC rail networks, naming the rail and dependent components. A plain ground does not automatically define VSS. The native VSS power source defaults to 0 V and defines that global rail without an extra ground wire. Connect the appropriate global power symbols/net labels to the intended supply. Numeric analysis stops at `power-rail-preflight` for these missing connections, before starting the native solver. Floating DC-network warnings remain advisory for transient circuits with initial conditions; numeric results retain them in `diagnostics`.

Failed numeric analyses retain original integer command/status codes and add `error_details` with the actual shell command and stage. Empty native `error_text` is filled with netlist evidence or a readable stage/command summary. Original native status codes are retained alongside readable command context. For a self-starting oscillator (for example a 555 astable), consider `use_initial_conditions: true` (UIC) with appropriate startup conditions, then verify sustained oscillation; UIC skips the DC operating point.
