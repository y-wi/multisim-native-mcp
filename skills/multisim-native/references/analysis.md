# Simulation and verification

For analysis plus acceptance, put measurements and criteria on a workflow `analysis` stage. For existing samples use `verify`. The tools below support individual analysis and diagnosis; see [workflows.md](workflows.md) for combined execution.

## Analysis and raw data

- `native_run_analysis(analysis: "op")` runs a DC operating point. For transient analysis use `analysis: "tran"`, `step` and `stop` in seconds. The requested grid is limited to 100,000 steps and `stop` to 100 seconds.
- `use_initial_conditions: true` selects transient UIC; choose it based on circuit startup requirements, not as an automatic response to every convergence failure.
- `native_run_ac_sweep` takes `sweep: "lin" | "dec" | "oct"`, `points`, `start_hz` and `stop_hz`. `lin` uses a total point count; the others use points per decade or octave. Configure the source's AC magnitude first.
- Results include `vectors`, `raw_path`, `csv_path`, `netlist_path` and `diagnostic_path`. Inspect actual source values and waveform metadata when results disagree with circuit expectations. Preserve raw numeric values; do not scale large currents to force a match.
- `native_read_waveform` accepts `offset`, `limit` and `plot_index`. Appended digital-node plots contain transition records `[time, rising, falling]`, not ordinary voltage samples.
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

Measurements require `id`, `metric` and `signal`. Real metrics are `min`, `max`, `mean`, `rms`, `peak_to_peak`, `frequency` and `duty_cycle`. Optional fields include `start`, `stop` and crossing `threshold`; duty cycle is a fraction from 0 to 1. Mean and RMS use the actual adaptive time grid. `native_measure_waveform` computes measurements without acceptance criteria.

Criteria use the same `id` as measurements and specify `min` / `max`, or `target` with `absolute_tolerance` / `relative_tolerance`. The older criterion key `measurement` is also accepted. AC metrics `gain_db` and `phase_deg` also need `reference` and `frequency_hz`:

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

Resolve the component's real value index before sweeping. Up to four parameters and 100 Cartesian combinations are supported. Goals are `min`, `max` and `target`; `result.best` is the zero-based index of the best feasible trial. Original numeric values and expressions are restored after execution; applying the selected candidate is a separate edit.

While a background experiment is active, inspect it with `native_experiment_status` or `native_list_experiments`, or request cancellation with `native_cancel_experiment`. Wait for terminal status and parameter restoration before editing. Save the source circuit before running a job that must be retryable. To retry, save any desired current edits, close the active session, then call `native_retry_experiment`; it opens the saved source in a new copy and returns a new ID linked by `retry_of`.

## Experiment reports

`native_export_experiment_report` accepts a saved completed `experiment_id`, an existing absolute `output_directory`, `language: "zh" | "en"`, optional `title` and up to eight `signals`. It exports standalone HTML, Markdown, measurement CSV, native schematic PNG and waveform SVG. A normal analysis call does not create a persistent experiment record for this tool.

## Interactive simulation

`native_control_interactive` accepts `start`, `pause`, `resume`, `stop` and `wait_timeout` (0–15 seconds). Use `transition_confirmed` to check actual completion. `simulation_time_s` is the native GUI's displayed simulation time; it may have display rounding. Read actual `SEVEN_SEG_COM_A` segments with `native_interactive_status(include_displays: true)`.

`native_configure_interactive(time_step: 0.001, max_time_step: 0.001, real_time: true)` changes temporary session overrides by default. Add `persist: true` to write the native document settings; subsequent `native_save_copy` preserves them for ordinary Multisim starts after reopening. Read document settings with `persist: true` and no values. When explicitly authorized to edit the source, add `save_to_source: true` to back up and replace it after independent native reopen verification. `saved_to_file: false` indicates that only the editable document was changed. Source conflicts stop replacement. `persist: true, reset: true` restores automatic steps and real-time pacing in the document; save it to retain the reset. Numeric analysis definitions and other solver options are preserved. Persistent changes clear temporary overrides so they cannot mask the document values.

Capture the current native runtime image with `native_export_interactive_image`; it shares the static export's region, DPI and frame options. Set `active_component` to wait for that display's lit scan phase. The result includes the actual `display_states`, `simulation` and `capture_mode: instantaneous`. No display states are synthesized. Resume a paused simulation before waiting for a different phase. Stop interactive simulation before numeric analysis, netlist generation or circuit edits.

## Persistent native analysis settings

Read `native_simulation_settings(scope: analysis, analysis_type: TRAN)` to discover actual native scalar paths, types, solver-option enabled states and revision. Use `scope: interactive` for interactive/instrument defaults. `changes` edits existing fields; `solver_options` enables typed tolerances, integration, convergence, temperature and flags while selecting native custom options. Use null/false to disable an option. Integer path tokens select duplicate labels and require `expected_revision`. The API does not create empty native lists or new analysis instances.

`native_run_analysis`, `native_start_analysis` and `native_run_ac_sweep` accept `persist:true` to retain explicit run settings, with optional `save_to_source:true` to back up and verify-save before execution. Alternatively `use_saved_settings:true` runs stored OP/AC/TRAN settings using native-compiled solver commands; it is exclusive with persist. RAW/CSV results remain external files. `native_save_source` saves all current native edits, including configured settings; plain catalog reads return `saved_to_file:false` because they do not save. The root window caption follows the filename; the native page name is persisted separately.

Use `native_persistence_capabilities` for exact ownership of every tool. Application wiring preferences, runtime state, export rendering flags and MCP experiment/workflow records are not circuit-file simulation settings.
