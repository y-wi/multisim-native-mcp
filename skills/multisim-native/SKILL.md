---
name: multisim-native
description: "Create, edit, wire, simulate and verify editable NI Multisim circuits using the multisim_native MCP server. Use for .ms14 projects, native component placement, named-pin wiring, schematic exports, waveform measurements and parameter experiments."
---

# Multisim Native

Use the `multisim_native` MCP server to edit real Multisim objects and run its simulator. Tool names below are unprefixed; a client may expose them as `mcp__multisim_native__native_*`.

## Start here

- Discover the connected server's tools and schemas. Use `native_runtime_status` when runtime availability or session ownership is unclear. This does not start Multisim.
- For an existing file, use `native_open_copy` with its absolute `.ms14` path. For a new circuit, use `native_create_circuit`. Use `native_attach(pid, project_index)` when the user requests editing a particular running window; closing that session detaches and leaves the window open.
- Owned-host startup requires other Multisim windows to be closed. If blocked, preserve the user's work and resolve the session conflict before retrying.
- Consume the initial `state`, then read only missing information. Current versions offer `native_get_circuit_state` for sheets, components, exact pin names, parameters, labels and wires in one call. Older versions may require the individual list tools.
- Use native tools for circuit editing and simulation. Inspect a native exported image when visual review is needed.

## Choose the capability

| Need | Tools |
| --- | --- |
| Session and diagnosis | `native_runtime_status`, `native_diagnostics`, `native_create_circuit`, `native_open_copy`, `native_attach`, `native_list_projects`, `native_save_copy`, `native_close_copy` |
| Inspect circuit | `native_get_circuit_state`, `native_list_components`, `native_list_wires`, `native_list_sheets`, `native_select_sheet` |
| Find and place parts | `native_search_library`, `native_place_component`, `native_copy_component`, `native_replace_component`, `native_delete_object` |
| Values and models | `native_get_parameters`, `native_set_parameter`, `native_get_model`, `native_set_model_text` |
| Layout and labels | `native_move_component`, `native_transform_component`, `native_rename_component`, `native_move_component_label`, `native_add_text`, `native_label_wire` |
| Electrical connections | `native_connect_pins`, `native_connect_endpoints`, `native_reconnect_wire`, `native_split_wire`, `native_route_wire` |
| Sheets and hierarchy | `native_create_sheet`, `native_create_subcircuit`, `native_create_hierarchical_port` |
| Transactions | `native_edit_batch`, `native_undo`, `native_redo` |
| Netlist and simulation | `native_check_netlist`, `native_run_analysis`, `native_run_ac_sweep`, `native_start_analysis`, `native_analysis_status`, `native_control_analysis` |
| Numeric verification | `native_read_waveform`, `native_measure_waveform`, `native_verify_waveform`, `native_decode_seven_segment` |
| Parameter experiments | `native_run_parameter_sweep`, `native_start_experiment`, `native_experiment_status`, `native_list_experiments`, `native_cancel_experiment`, `native_retry_experiment` |
| Presentation and reports | `native_check_layout`, `native_plan_wire_route`, `native_auto_route_wire`, `native_export_image`, `native_export_experiment_report` |

This map covers the current 60-tool interface; availability and parameter types come from the connected server's schemas.

## Build and edit efficiently

Read [references/editing.md](references/editing.md) for batch argument names, wire branches, hierarchy and image export options.

1. Read `page.width`, `page.height` and `page.bounds` before placing parts. Coordinates start at the top left and use **96 sheet units per inch**. The bundled blank sheet is **960 × 720**; printing-paper dimensions are separate. Placement can snap to the grid, so use returned pin coordinates when routing.
2. Search the real library. Check `Family_Name`, `Group_Name` and the placed model rather than relying on a part's name or reference prefix. An adjustable resistor is `RESISTOR_VIRTUAL`, family `RESISTOR`, group `Basic`; similarly named 3D parts can belong to `3D_VIRTUAL`.
3. Select the electrical value using parameter metadata: **`role: "value"`**, its name and unit. Use that descriptor's `index`. For `RESISTOR_VIRTUAL`, index **1** is `resistance` in ohms; index **0** is `model_option`. Setting index 0 to 1000 does not set a 1 kΩ resistance. For other parts, inspect their descriptors rather than carrying this index over.
4. Connect exact pin names from the current component results. A line touching a symbol visually does not establish a native electrical connection.
5. Group known edits in `native_edit_batch`, with `include_state: true`, instead of rereading after every change. Placement can include indexed parameters. If the part or pin schema is unknown, place and inspect it before constructing dependent edits.
6. After topology edits, check the netlist. If `handles_invalidated: true`, use its returned fresh `state`; if absent, reread the relevant objects. Undo, redo and rollback can also invalidate pointer IDs. Prefer component reference names for subsequent edits.
7. Before saving, compare the complete `content_bounds` with `page.bounds`, including symbols, wires, labels and text. For a normal finished schematic, fit the circuit inside the sheet with a margin. Use a coherent layout edit or the native `sheetSize` batch operation; image cropping does not repair saved page geometry. See the saved-sheet procedure in [references/editing.md](references/editing.md).
8. Save the requested absolute `.ms14` output before closing an owned session. Output directories must exist; existing outputs require `overwrite: true`. After changing sheet size or repairing off-page layout, reopen the saved output as a copy and verify its page and content bounds.

## Verify the electrical result

Read [references/analysis.md](references/analysis.md) for measurement schemas, scanned displays, AC sweeps and persistent experiments.

- Check the generated SPICE source and actual parameter values. A resistor line containing `0.0` represents zero resistance; it is not merely a display format for an unset 1 kΩ value.
- Waveform numbers retain the native simulator's SI values: voltage **V**, current **A**, time **s**, frequency **Hz**. **`-0.006 A` is −6 mA; `-6e12 A` is not −6 mA.** Do not invent an fA conversion to make a result match expectations. Inspect the generated source, raw samples and the selected parameter slot.
- For a 12 V divider with two 1 kΩ resistors, verify both the **6 V midpoint** and the **−0.006 A source current**. A plausible midpoint alone can conceal zero-valued resistors.
- Use vector names returned by the actual analysis, not guessed node numbers. Verify the requested behavior from measurements or decoded samples; a successful tool call or a momentary screenshot is insufficient evidence.
- On failed analysis, inspect `native_diagnostics` and the returned diagnostic file. Recheck topology, values and simulation models before changing analysis settings. Use transient UIC only when appropriate to the requested circuit.

## Finish the requested artifact

Use `native_check_layout` when checking wire attachment or geometry. For overlapping reference labels, use `native_move_component_label` rather than moving the symbol. Validate the saved page with a whole-sheet export (`fit_content: false`, no `region`) at a suitable DPI. An optional content-fitted image or crop can follow; it does not establish that the saved circuit lies inside its sheet. Preserve an intentionally off-page layout when the user explicitly requests it.

Report the saved circuit and requested exports, the measured result and any remaining failed criterion. Keep numeric verification distinct from visual inspection. If the user will validate the simulation themselves, deliver the edited artifact without starting additional experiments.
