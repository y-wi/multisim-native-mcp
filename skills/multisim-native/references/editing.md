# Native editing contracts

For complete circuit tasks, prefer staged workflows in [workflows.md](workflows.md). Individual tools and edit batches remain useful for local changes and older servers.

## State and parameters

Create directly in the task workspace with `native_create_circuit(output_path, title)` and edit existing sources with `native_open_circuit`. Both return an initial `state`. `native_list_projects` attaches a single running Multisim process when no session is attached; runtime status distinguishes `running` from `session_attached`. `native_get_circuit_state` omits parameter metadata and net names by default; `include_parameters: true` adds indexed parameters, and `include_nets: true` attaches wire net names and pin SPICE signal names (`V(...)`). Use `native_get_connectivity()` for sheet-wide wire/pin net mappings and `native_resolve_signal(component_ref, pin)` to resolve one pin's SPICE vector name.

`native_search_library` returns `Manufacturer_Name`, `Model_Name` and `Simulatable` alongside family/group categories, ranks exact name matches first, and supports `manufacturer` and `simulatable_only` filters.

For a component already present, call `native_get_parameters(component_ref)` and select its electrical-value descriptor by `role`, `name` and `unit`. Common parts (including `RESISTOR_VIRTUAL`, `CAPACITOR_VIRTUAL`, `INDUCTOR_VIRTUAL`, `DC_POWER`, `DC_CURRENT`, `AC_POWER`, `AC_VOLTAGE`, `CLOCK_VOLTAGE`, `PULSE_VOLTAGE`, `OPAMP_3T_VIRTUAL`, `VDD`/`VCC`/`VSS`/`VEE` and `LED` parts) expose named descriptors, so `native_set_parameter` can omit `index` (defaulting to the unique `role: "value"` slot) or select by `name`/`role`, and `native_place_component` accepts `params` (for example `{"frequency": "1k", "ac_magnitude": 1}`). Write either a numeric `value` or an `expression`, never both:

```json
{"component_ref":"R1","value":1000}
```

Or select a named slot explicitly:

```json
{"component_ref":"V1","name":"frequency","expression":"1k"}
```

When using `index` directly, index 1 applies specifically to `RESISTOR_VIRTUAL` (index 0 is a model option, not resistance). Numeric values use the descriptor's unit; SPICE expressions such as `1k` can be supplied through `expression`.

`POTENTIOMETER_VIRTUAL` and `POTENTIOMETER_RATED` expose total `resistance` and `wiper_step` (percent per adjustment). The rated part also exposes `rated_power`. `Potentiometer1_5K` has a fixed 5 kΩ resistance and exposes `wiper_step`. Verify their electrical response with native interactive simulation. The standalone numeric SPICE path can retain these models' placeholder resistors because it does not apply their interactive control code.

## Common parts quick reference (Multisim 14.3)

Sheet snap grid is **9** units (origin top-left, x right, y down, positive `angle` clockwise). `*` marks the primary `role: "value"` slot accepted by `value`/`expression` or index-free `set_parameter`.

| Component | Pins & default offsets (sheet units) | Named `params` (unit) |
| --- | --- | --- |
| `RESISTOR_VIRTUAL` | `1` left, `2` right (`+45, 0`); `angle: 90` puts `1` top → `2` bottom | `resistance*` (Ohm) |
| `CAPACITOR_VIRTUAL` | `1` left, `2` right (`+45, 0`); `angle: 90` puts `1` top → `2` bottom | `capacitance*` (F) |
| `INDUCTOR_VIRTUAL` | `1` left, `2` right (`+45, 0`) | `inductance*` (H) |
| `DC_POWER` | `1` (`+`) top, `2` (`-`) bottom (`0, +36`) | `voltage*` (V) |
| `DC_CURRENT` | `1` top, `2` bottom (`0, +54`) | `current*` (A) |
| `AC_POWER` | `1` top, `2` bottom (`0, +54`) | `voltage_rms*` (V), `frequency` (Hz), `ac_magnitude` (V) |
| `AC_VOLTAGE` | `1` top, `2` bottom (`0, +54`) | `voltage_pk*` (V), `frequency` (Hz), `ac_magnitude` (V) |
| `CLOCK_VOLTAGE` | `1` top, `2` bottom (`0, +54`) | `frequency*` (Hz), `duty_cycle` (%), `voltage` (V), `rise_time` (s), `fall_time` (s) |
| `PULSE_VOLTAGE` | `1` top, `2` bottom (`0, +54`) | `initial_value` (V), `pulsed_value` (V), `rise_time` (s), `fall_time` (s), `pulse_width` (s), `period` (s) |
| `GROUND` | `1` (single pin; net `"0"`) | — |
| `VDD` / `VCC` / `VSS` / `VEE` | Pin name equals symbol (`"VDD"`, `"VCC"`, `"VSS"`, `"VEE"` — **not `"1"`**) | `voltage*` (V) |
| `OPAMP_3T_VIRTUAL` | `IN+` `(0, 0)`, `IN-` `(0, +36)`, `OUT` `(+90, +18)` | `open_loop_gain`, `input_resistance` (Ohm), `output_resistance` (Ohm), `v_pos` (V), `v_neg` (V) |
| `POTENTIOMETER_VIRTUAL` | `3` top `(0, -45)`, `1` bottom `(0, 0)`, wiper `2` left `(-27, -27)` | `resistance*` (Ohm), `wiper_step` (%) |
| `POTENTIOMETER_RATED` | `3` top `(0, -63)`, `1` bottom `(0, 0)`, wiper `2` left `(-36, -36)` | `resistance*` (Ohm), `wiper_step` (%), `rated_power` (W) |
| `LED_red` (and `LED_*`) | `A` (anode) top, `K` (cathode) bottom (`0, +54`) | `on_current*` (A) |
| `SEVEN_SEG_COM_A` / `SEVEN_SEG_COM_K` | Bottom `A`..`G` left-to-right (step `9` units); `COM` directly above `A` (`-117` in y) | — |
| `DCD_HEX` (and `DCD_HEX_*`) | Bottom `4` (MSB) → `3` → `2` → `1` (LSB), left-to-right (step `18` units) | — |
| `PROBE_DIG` (and `PROBE_DIG_*`) | `1` (single pin) | — |

## Virtual instruments quick reference (Instruments toolbar)

Place toolbar instruments with `native_place_instrument` (or batch/workflow `place_instrument`) and configure them with `native_set_instrument_settings` (or `set_instrument_settings`). All 19 active Multisim 14.3 toolbar instruments are supported; aliases (e.g. `scope`, `fgen`, `dmm`, `示波器`, `函数发生器`, `万用表`) are accepted.

| Instrument (`instrument`) | Prefix | Verified `pin_map` | Key friendly `settings` (raw `NI_EWB_*` also accepted) |
| --- | --- | --- | --- |
| `multimeter` | `XMM` | `1`: `+`, `2`: `-` | `mode` (`current`/`voltage`/`resistance`/`db`), `signal` (`AC`/`DC`) |
| `function_generator` | `XFG` | `1`: `+`, `2`: `COM`, `3`: `-` | `waveform` (`sine`/`triangle`/`square`), `frequency_hz`, `duty_cycle_pct`, `amplitude_vp`, `offset_v`, `rise_fall_time_s` |
| `wattmeter` | `XWM` | `1`: `V+`, `2`: `V-`, `3`: `I+`, `4`: `I-` | Live readouts: `power`, `power_factor` |
| `oscilloscope` | `XSC` | `1`: `A+`, `4`: `A-`, `2`: `B+`, `5`: `B-`, `3`: `Ext Trig +`, `6`: `Ext Trig -` | `timebase_mode`, `timebase_scale_s_per_div`, `channel_a_coupling`/`channel_a_scale_v_per_div`/`channel_a_position_div`, `channel_b_*`, `trigger_source`/`trigger_edge`/`trigger_level_v`/`trigger_mode` |
| `oscilloscope_4ch` | `XSC` | `1`: `A`, `2`: `B`, `3`: `C`, `4`: `D`, `5`: `T`, `6`: `G` | `timebase_scale_s_per_div`, `channel_a`..`channel_d` (`coupling`, `scale_v_per_div`, `position_div`, `sign`), `trigger_*` |
| `bode_plotter` | `XBP` | `1`: `IN+`, `2`: `IN-`, `3`: `OUT+`, `4`: `OUT-` | `mode` (`magnitude`/`phase`), `horizontal_scale`/`vertical_scale` (`log`/`lin`), `horizontal_initial_hz`/`horizontal_final_hz`, `vertical_initial_db`/`vertical_final_db`, `resolution_points` |
| `frequency_counter` | `XFC` | `1`: `IN` | `mode`, `coupling`, `sensitivity_vrms`, `trigger_level_v` |
| `word_generator` | `XWG` | `1`..`32`: `Bit 0`..`31`, `33`: `R`, `34`: `T` | `mode`, `frequency_hz`, `level_low_v`, `level_high_v` |
| `logic_converter` | `XLC` | `1`..`8`: `A`..`H`, `9`: `OUT` | `boolean_expression`, `num_variables` |
| `logic_analyzer` | `XLA` | `1`..`16`: `CH1`..`CH16`, `17`: `C`, `18`: `Q`, `19`: `T` | `clock_source`, `clock_edge`, `internal_clock_rate_hz`, `threshold_voltage_v` |
| `iv_analyzer` | `XIV` | `1`, `2`, `3` | `vertical_scale`, `horizontal_scale`, `current_*`, `voltage_*` |
| `distortion_analyzer` | `XDA` | `1`: `IN` | `mode` (`thd`/`sinad`), `display_unit` (`percent`/`db`), `fundamental_frequency_hz`, `harmonics` |
| `spectrum_analyzer` | `XSA` | `1`: `IN`, `2`: `T` | `span_mode`, `start_frequency_hz`, `end_frequency_hz`, `vertical_mode` |
| `network_analyzer` | `XNA` | `1`: `P1`, `2`: `P2` | `start_frequency_hz`, `stop_frequency_hz`, `characteristic_impedance_ohm`, `points`, `sweep_type` |
| `agilent_function_generator` | `XFG` | `1`: `Output`, `2`: `Sync` | `power_on` + raw `NI_EWB_*` |
| `agilent_multimeter` | `XMM` | `1`: `HI`, `2`: `LO`, `3`: `I`, `4`/`5`: `4W Sense` | `power_on`, `mode`, `function` + raw `NI_EWB_*` |
| `agilent_oscilloscope` | `XSC` | `1`: `CH1`, `2`: `CH2`, `3`: `Ext Trig`, `4`: `GND`, `5`: `Sync`, `6`..`21`: `D0`..`D15` | `power_on`, `channel_a_enabled`, `channel_b_enabled`, `trigger_level_*` + raw `NI_EWB_*` |
| `tektronix_oscilloscope` | `XSC` | `1`..`4`: `CH1`..`CH4`, `5`: `T`, `6`: `P`, `7`: `G` | `power_on`, `trigger_level_v`, `channel_1_coupling`..`channel_4_invert` + raw `NI_EWB_*` |
| `current_probe` | `XCP` | `1`: `I+`, `2`: `I-`, `3`: `Vout` | `ratio_v_per_ma` (`1.0` = `1 V/mA` = `1000 V/A`) |

## Placement transforms and displayed values

All placement entry points support `angle` (finite degrees), `mirror_axis` (`horizontal` reverses x, `vertical` reverses y), and either primary `value` or `expression`. The order is rotate, mirror, then translate to the selected `origin`, body `center`, or named `pin` anchor. Positive rotation is clockwise in sheet coordinates (x right, y down). For an LED with A above K, -90 degrees places A on the left; +90 places A on the right. Returned `pins`, `labels` and `placement.pin_offsets` describe the final symbol. Preparation states this convention, with offsets relative to its center anchor.

```json
{"name":"CAPACITOR_VIRTUAL","x":360,"y":180,"anchor":"pin","pin":"1","angle":90,"expression":"1u"}
```

Primary values require one unambiguous value descriptor. Explicit strings such as `1u`, `10n`, `68k` and `1Meg` are preserved. Numeric primary placement values use compact SPICE engineering expressions (`1e-6` becomes `1u`, `10000` becomes `10k`); explicit indexed expressions override formatting. Indexed numeric primary placement parameters receive the same compact formatting. Other slots and later numeric `set_parameter` calls retain their existing behavior. Native numeric caches can remain null until expression evaluation; check generated SPICE or simulation for electrical values.

Omit `reference` / `ref` for repeated power symbols. Duplicate GROUND/VDD/VSS/VCC/VEE/GND/DGND/AGND default network-style references use native-assigned identities and return `reference_auto_assigned` with requested/actual references and a unique component ID. Global supplies can retain shared refs after reopening; use returned IDs or workflow bindings. Custom duplicate references still fail atomically.

## Batch edits

`native_edit_batch` takes a nonempty list of operations as one undo unit. Operations run in order; failure restores the checkpoint. Use standalone selector names (`component_ref`, `wire_id`, `object_id`, `junction_id`); older `ref` and `id` aliases also work. Operation names accept the standalone name with or without `native_`, as well as existing camelCase names. Conflicting selectors fail before a checkpoint or edit.

By default `atomic: true` rolls back this entire batch on failure. Choose `atomic: false` to preserve completed steps and restore only the failing operation. Earlier calls remain committed in either mode. Error results contain the rollback scope, preserved step count, handle invalidation flag and fresh state; consume these before another edit. A first-operation target lookup failure keeps handles intact.

```json
{
  "operations": [
    {"operation":"place_component","arguments":{"name":"RESISTOR_VIRTUAL","reference":"R1","x":306,"y":108,"parameters":[{"index":1,"value":1000}]}},
    {"operation":"place_component","arguments":{"name":"RESISTOR_VIRTUAL","reference":"R2","x":504,"y":108,"parameters":[{"index":1,"value":1000}]}},
    {"operation":"connect_endpoints","arguments":{"source":{"component_ref":"R1","pin":"2"},"target":{"component_ref":"R2","pin":"1"}}}
  ],
  "include_state": true
}
```

This is a resistor-chain fragment, not a complete simulation circuit. The example's pins `1` and `2` are the known `RESISTOR_VIRTUAL` pins; inspect other parts first.

Common batch operations:

| Operation | Arguments |
| --- | --- |
| `place_component` | `name, reference, x, y`, optional `family, group, manufacturer, parameters, params, anchor, pin, angle, mirror_axis, value, expression` |
| `place_instrument` | `instrument, x, y`, optional `reference, anchor, pin, angle, mirror_axis, settings` |
| `set_instrument_settings` | `component_ref, settings` (friendly setting names or raw `NI_EWB_*` property paths) |
| `set_parameter` | `component_ref`, optional `index, name, role` (defaults to unique `value` slot), exactly one of `value, expression` |
| `connect_endpoints` | `source, target`, optional `points` |
| `move_component` | `component_ref, dx, dy` (relative displacement) |
| `move_component_label` | `component_ref, x, y`, optional `kind: reference | value` (absolute label center) |
| `transform_component` | `component_ref, angle` (finite degrees), or `component_ref, mirror_axis` (`horizontal` / `vertical`) |
| `route_wire` | `wire_id, points` |
| `autoWire` | `wire_id` (Multisim native router, preserving wire ID and electrical endpoints) |
| `connect_touching` | optional `component_refs` list (current sheet if omitted) |
| `rename_component` | `component_ref, new_ref` |
| `add_text`, `update_text` | `text, x, y`; update additionally takes `object_id`, and omitted text/coordinates retain their values |
| `delete_object` | exactly one of `object_id, component_ref` |
| `update_sheet` | supplied `title, page, width, height` fields; omitted fields retain their values |
| `fit_sheet`, `translate_sheet` | `fit_sheet {margin?, resize?}` shifts off-page/negative objects inward and optionally resizes; `translate_sheet {dx, dy}` shifts all sheet items |

Default public results omit unused native parameter slots. `parameter_count` and `parameters_complete` describe the returned metadata; use `include_parameters: true` on placement/preparation/batches, or `native_get_parameters`, when full slots are needed. Experiment values and supplied parameter edits are retained. Higher-level obstacle planning remains available through standalone `native_auto_route_wire(engine: obstacle)`.

## Electrical wires and branches

Shared power symbols may have identical `ref` and `local_ref`. Use their current component IDs in `component_ref`. Physical wire ownership is determined by connector IDs; shared net names do not identify a specific placed symbol. Wire endpoints include `component_id`. A controlled refresh reports changed handles in `id_map`, unresolved handles in `unresolved_ids`, and current state. Apply mappings before the next standalone edit; workflow bindings do this automatically. Rollback errors return fresh state.

Use `native_connect_endpoints` with `{"component_ref":"R1","pin":"2"}` or `{"junction_id":"<current junction ID>"}`. `ref` remains accepted inside endpoints. Repeating an existing connection reuses its wire and does not dirty the topology. `wire` and `native_connect_pins` are compatibility forms of this same connection engine. `native_connect_touching` is for discovering physical contacts rather than selecting explicit endpoints.

- Read actual wire routes with `native_list_wires` or the current state. Wire vertices and pin positions share sheet units.
- `native_route_wire(wire_id, points)` replaces the route. Each point is `{"x":integer,"y":integer}`; first and last points must match the native electrical connectors exactly.
- For a branch, split the existing wire with `native_split_wire` at a point on its route, then connect to the returned `junction_id` with `native_connect_endpoints`.
- Use `native_reconnect_wire` to change electrical endpoints; adding text or editing vertices does not replace an endpoint connection.
- `native_configure_wiring` reads or sets native `autowire_on_connection`, `autowire_on_move`, `connect_touching` and `move_connection_limit` options. Settings restore on close or `reset: true`. Moves below the limit reroute through Multisim; other moves preserve attachments and route shape.
- With `connect_touching` enabled, placement and movement connect contacts automatically. `native_connect_touching` also processes existing contacts. Interior wire contacts create native branch junctions; ambiguous crossings of different nets return an error. Consume returned state after wire splitting.
- `native_auto_route_wire` defaults to Multisim's native router, preserving the wire ID and electrical endpoints. Native routing requires endpoints inside the actual sheet. `native_plan_wire_route` previews the MCP obstacle planner; choose `engine: obstacle` to apply its route with `clearance` in sheet units.
- `native_label_wire(wire_id, name)` sets the electrical net name; empty names and net names already owned by a distinct net on the same sheet, flat sibling sheets or global power/ground rails are rejected cleanly (connect with a wire, junction, power symbol or On-Page connector instead).
- Inspect `native_check_layout` for missing connector attachment, invisible wire pens, overlapping symbols and obstructed routes. Then inspect the exported schematic for presentation issues.

## Sheets and hierarchy

Select a sheet using its current `native_list_sheets` index. `native_create_sheet` creates an independent sheet. `native_create_subcircuit` creates a child sheet and parent symbol; select the child and add `native_create_hierarchical_port` connectors before wiring the parent. Read the newly returned parent pin names after adding ports.

`native_update_sheet(title, page, width, height)` edits the selected sheet in one transaction. `native_update_hierarchical_port(object_id, name, x, y)` renames/moves an existing child connector and updates its parent symbol. Existing component move/transform/rename tools also apply to subcircuit symbols; use the port updater for its electrical connector name. `native_move_junction(junction_id, x, y)` preserves branch connections and reroutes their ends. Coordinates returned by the native engine reflect grid snapping.

Native root window captions follow the filename after reopening; use `page` for a persistent root page name. Embedded child titles and page names are separate native fields. Sheet renames retain hierarchical component references.

## Free text

Read `state.texts` or `native_list_texts` for independent notes, including IDs, content, insertion coordinates, transform and bounds. Use `native_update_text(object_id, text?, x?, y?)` to change content and/or absolute insertion position while retaining formatting and ID. Omitted fields retain their values; `text: ""` clears the note. Use `native_delete_object(object_id)` to remove it. Ordinary free-text deletion preserves electrical handles. Component reference/value labels and generated wire net labels are separate objects with separate editing tools.

Batch/workflow forms include `update_text {object_id,text?,x?,y?}`, `delete_object {object_id}`, `update_sheet {title?,page?,width?,height?}`, `update_hierarchical_port {object_id,name?,x?,y?}` and `move_junction {junction_id,x,y}`. Existing camelCase and `id` selectors remain accepted. Bind `add_text` results and use `{"$ref":"note.id"}` in later edits. Controlled refreshes report ID maps; workflow bindings rebind automatically. Save normally to persist all edits.

Embedded model text may be shared by several components. `native_set_model_text` returns affected references across the project; inspect these before treating it as a single-instance change.

## Fit the saved sheet

`fit_content` and `region` affect image framing only. They restore the original page geometry after rendering. A correctly cropped image can therefore accompany an `.ms14` whose circuit is still outside its sheet.

For a finished schematic:

1. Read `page.bounds` and the complete `content_bounds` after placing, routing and adding text. Require `content.left >= page.left + margin`, `content.top >= page.top + margin`, `content.right <= page.right - margin` and `content.bottom <= page.bottom - margin`. A margin of 18–36 sheet units is usually sufficient. Repeat on each edited sheet.
2. For a new modest circuit, lay it out inside the initial sheet rather than placing it thousands of units away. If an existing layout has negative coordinates or exceeds the sheet bounds, call `native_fit_sheet(margin=36, resize=True)` (or batch `fitSheet`) to shift all components, junctions, wire routes and free text inward by a grid-aligned offset and optionally resize the sheet in one undoable edit. If you only need more space on the right or bottom, you can also resize explicitly with `sheetSize`:

   ```json
   {"operations":[{"operation":"sheetSize","arguments":{"width":1200,"height":900}}],"include_state":true}
   ```

   Compute dimensions from actual content bounds and margin; these numbers are an example. Resizing alone preserves positions and connections and does not fix negative left/top coordinates (use `native_fit_sheet` or `translateSheet` for that).
3. Consume the returned state to check containment. Save with native readback enabled and inspect `page_check` and `verification`. A passing independently reopened copy already verifies persistence; close and reopen manually only when investigating a readback failure or when explicitly requested. Select the relevant sheet for a multi-sheet export.
4. Export the verified sheet with `fit_content: false` and no `region`. Inspect this full-page image before producing any optional cropped image. If the user will verify simulation themselves, this geometry check does not require starting a simulation.

An intentionally off-page layout or an image-only task can use content fitting directly when that matches the user's request.

## Image export

Example whole-page arguments for `native_export_image` after the saved-sheet check:

```json
{"output_path":"C:/Circuits/divider.png","dpi":192,"fit_content":false}
```

Use an existing absolute output directory. PNG and BMP are supported. `dpi` and `scale` are positive values without MCP maxima. Bitmap format and available memory determine actual rendering capacity. Rendering uses the native engine and synchronizes connector graphics before export; electrical attachments and sheet dimensions are preserved. Use `native_repair_wire_geometry` for an explicit undoable correction, then save normally; native readback already verifies persistence.

Default `show_frame: false` and `show_grid: false` produce a clean report image. Set `show_frame: true` for sheet border/title block, and `show_grid: true` for the dot grid. These choices are temporary rendering options; the original display settings are restored.

For a detail image, use `fit_content: true` with optional `padding`, or `region: {"left":100,"top":80,"right":700,"bottom":500}` in absolute sheet units. `region` and `fit_content` are mutually exclusive. If a whole-page image omits circuit content, repair the saved sheet before accepting the schematic deliverable; a cropped export alone only fixes the image framing.

Move an overlapping reference with `native_move_component_label(component_ref, x, y)`. Coordinates specify the absolute label center; read `state.components[].labels` for actual bounds. Grid snapping can affect symbol placement, so use returned positions rather than requested coordinates when checking alignment.

Normal saves update the current workspace/source file using `native_save_source`. A workflow `save` without output_path does the same. Save As changes the current document path. Source saves verify native readback by default. An explicit `verify:false` skips reopen verification, including saving to the current path; external-change checks and backups still apply. Closing saves pending edits by default; skip saving only when the task calls for it. Backups and checkpoints are internal, not extra deliverables. `native_open_copy` is for explicit comparisons and creates its editable file in the chosen workspace.

Prepared pin offsets are relative to the returned center anchor, not the native placement origin. Use the returned `anchor`, `pin_offsets_relative_to` and `placement`; each placed component also returns `placement.pin_offsets` for its actual anchor. Symbol `body_bounds` excludes external pin leads; use returned pin coordinates for wiring. Batch `remove` accepts `object_id`/`id` or `component_ref`/`ref`, matching the standalone deletion selectors.

Layout issues retain `component_overlap` and `wire_crosses_component` for body collisions and add `collision_target: "body"`. Pure text collisions return `label_overlap` or `wire_overlaps_label`, `collision_target: "label"`, label kinds/IDs and `suggestion: "move_component_label"`. Wires attached to a symbol can still overlap its labels.
