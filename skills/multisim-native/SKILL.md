---
name: multisim-native
description: "Create, edit, wire, simulate, verify and save native NI Multisim (.ms14) circuits in the task workspace through the multisim_native MCP server (原理图绘制、连线、OP/DC/AC/瞬态/交互仿真、波形测量与 Bode/PNG 绘图)."
license: MIT
compatibility: "Windows 10/11 with 32-bit NI Multisim 14.3 and the multisim_native MCP server"
metadata:
  version: "0.5.4"
---

# Multisim Native

Use `multisim_native` for editable Multisim objects and native simulation. Tool names below omit the client prefix.

## Work on the actual document

- **New circuit**: pick an unused `.ms14` path in the task directory (normally CWD, or the user's requested path) and pass that absolute `output_path` to `native_create_circuit` or a workflow `session` (`mode: create`). Never deliver files from AppData, recovery folders or packaged templates.
- **Existing / open circuit**: use `native_open_circuit(source_path)` (or workflow `mode: open`) to edit the real source directly; reopening the active direct path reuses its in-memory state and handles. Use `native_list_projects` to attach the sole running Multisim window, or `native_attach(pid, project_index)` when multiple exist.
- **Save & close**: update the current document with `native_save_source` (or workflow `save` without `output_path`). Use `native_save_copy(output_path)` for Save As (it becomes the active document in direct mode). `native_close_copy` and workflow `close` save pending edits by default (`save_changes: false` skips saving; detached user windows stay open).
- **Isolated copies**: use `native_open_copy` / `session.isolated_copy: true` only for explicit comparisons or preserving an untouched original—never merely as edit rollback protection (native checkpoints handle rollback automatically).

## Choose a suitable execution shape

- **Complete circuit tasks**: prefer one `native_run_workflow` plan covering session, edits, layout/netlist, analysis/criteria, save and export. See [references/workflows.md](references/workflows.md) and the reusable templates in `assets/` (`workflow_divider.json`, `workflow_rc_ac_filter.json`, `workflow_interactive_indicators.json`).
- **Local adjustments & offline analysis**: use standalone tools or `native_edit_batch`. Batch/workflow selectors accept standalone names (`component_ref`, `wire_id`, `object_id`, `junction_id`) as well as `ref`/`id`, and operation names accept standalone names (with or without `native_`) or camelCase.
- **Minimize round trips**: reuse returned `state`, `pins`, `placement.pin_offsets` and `bind` results instead of re-querying after every step. Use `native_prepare_components` only for unfamiliar parts whose pins/parameters are not listed in [references/editing.md](references/editing.md); standard parts can be placed directly.
- **Handle refreshes**: netlist refresh, preparation, undo/redo and `replace`/`createSubcircuit` report `handles_invalidated`, `id_map`, `unresolved_ids` and fresh `state`. Apply `id_map` to retained standalone handles; workflow bindings rebind automatically.
- **No artificial quotas**: the MCP imposes no runtime, operation-count, coordinate, sample or pixel caps. Set `max_runtime` only when the user requests a deadline.

## Native details that affect correctness

- **Coordinates & geometry**: origin is top-left, 96 sheet units/inch, snap grid is 9 units, blank sheet is 960 × 720. Placement applies `angle` (positive = clockwise), then `mirror_axis` (`horizontal` flips x, `vertical` flips y), then `anchor` (`origin` default, `center`, or `pin`). Use `native_fit_sheet` (or `fitSheet`) to shift negative/off-page contents inward and resize the actual sheet; `fit_content` only crops exported images.
- **Pins, nets & power symbols**: visible contact does not guarantee attachment—connect actual native pins and check `native_get_connectivity` or `native_get_circuit_state(include_nets: true)`. Resolve SPICE vector names with `native_resolve_signal(component_ref, pin)` (or pass `{"component_ref", "pin"}` directly to `native_measure_waveform` / `native_verify_waveform` while the circuit is open). Note that `VDD`/`VCC`/`VSS`/`VEE` pins are named after the symbol (`"VDD"`, etc.), not `"1"`. Omit `ref` for repeated power/ground symbols and reference them by returned component ID or workflow `bind`.
- **Unique net labels**: `native_label_wire` rejects empty names and names already owned by a distinct net on the same sheet, flat sibling sheets or global power/ground rails (join nets with a wire, junction, power symbol or On-Page connector instead).
- **Named parameters & library search**: common parts expose named descriptors (see the cheat sheet in [references/editing.md](references/editing.md)), so `native_place_component` accepts `params` (e.g. `{"frequency": "1k", "ac_magnitude": 1}`) and `native_set_parameter` can select by `name`/`role` or omit `index` for the unique primary `value` slot. Numeric values use SI units; for `RESISTOR_VIRTUAL`, index `1` is resistance (`0` is model option). Filter searches with `manufacturer` and `simulatable_only: true`. Note: potentiometers (`POTENTIOMETER_VIRTUAL`/`POTENTIOMETER_RATED`/`Potentiometer1_5K`) adjust dynamically in **interactive** simulation; standalone SPICE numeric analysis retains placeholder resistors.
- **Virtual instruments (right-hand Instruments toolbar)**: use `native_list_instruments`, `native_place_instrument`, `native_get_instrument_settings`, `native_set_instrument_settings` and `native_export_instrument_data` for Multimeter (`XMM`), Function Generator (`XFG`), Wattmeter (`XWM`), 2-Ch/4-Ch Oscilloscope (`XSC`), Bode Plotter (`XBP`), Frequency Counter (`XFC`), Word Generator (`XWG`), Logic Converter (`XLC`), Logic Analyzer (`XLA`), IV Analyzer (`XIV`), Distortion Analyzer (`XDA`), Spectrum Analyzer (`XSA`), Network Analyzer (`XNA`), Agilent/Tektronix instruments, and Current Probe (`XCP`). Instruments support wiring via `native_connect_endpoints`, batch/workflow operations (`place_instrument`, `set_instrument_settings`), interactive readouts via `native_interactive_status(include_displays: true)` / `native_get_instrument_settings`, native `.scp`/`.bod` trace export, and full save-reopen verification. See [references/editing.md](references/editing.md) for verified instrument pin maps and friendly setting names.
- **Hidden global rails & diagnostics**: mixed-signal parts (e.g. `4017BD_5V`) may require global `VDD`/`VSS` rails (ordinary `GROUND` does not define `VSS`; a `VSS` source defaults to 0 V). Check `native_check_netlist().diagnostics`. For self-starting oscillators (e.g. 555 astable), consider transient `use_initial_conditions: true` (UIC) when startup requires it.
- **Analysis, plots & live indicators**: use `native_run_dc_sweep` (or workflow `analysis: "dc"`) for DC transfer sweeps; `native_measure_waveform` / `native_verify_waveform` support timing/step (`period`, `rise_time`, `fall_time`, `overshoot`, `settling_time`, `value_at`), digital plots (`plot_index`) and AC metrics (`gain_db`, `phase_deg`, `magnitude`, `bandwidth_3db`, `phase_margin`); `native_plot_waveform` exports SVG or PNG traces (`overlay: true` for same-unit comparison, `reference` for dual-panel AC Bode plots). During interactive simulation, `native_interactive_status(include_displays: true)` and `native_export_interactive_image` read `SEVEN_SEG_COM_A`/`K`, `DCD_HEX*` (`0`–`F`), `LED_*`/`LED_*_RATED` and `PROBE_DIG*`. Stop interactive simulation before edits or numeric analysis.
- **Layout & annotations**: `native_check_layout` distinguishes `collision_target: "body"` from `"label"`; fix label overlap with `native_move_component_label`. Manage free text via `state.texts` / `native_update_text` / `native_delete_object`, multi-sheet plans via `select_sheet`, and hierarchy via `native_update_hierarchical_port` / `native_move_junction`.

For detailed contracts read [references/editing.md](references/editing.md) (including the **22-part pin/parameter/span cheat sheet**), [references/workflows.md](references/workflows.md) and [references/analysis.md](references/analysis.md).

## Persistent configuration & delivery

- `native_simulation_settings` edits existing `interactive` and `analysis` profiles (and typed `solver_options`) using `expected_revision` for indexed paths. `native_configure_interactive` persists into the document by default (`persist: false` for temporary overrides); numeric runs keep explicit arguments per-run unless `persist: true` or `use_saved_settings: true` (OP/AC/TRAN). `native_configure_sheet_display` persists sheet display preferences; `native_configure_wiring(persist: true)` commits application-wide preferences. Use `native_persistence_capabilities` to inspect exact ownership.
- **Deliver**: report the actual saved workspace `.ms14` path, exported images/plots and verification evidence (and visually inspect exported PNGs when practical). Do not substitute cached/recovery copies or create unrequested extra files.
