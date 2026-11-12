# Native editing contracts

For complete circuit tasks, prefer staged workflows in [workflows.md](workflows.md). Individual tools and edit batches remain useful for local changes and older servers.

## State and parameters

Create directly in the task workspace with `native_create_circuit(output_path, title)` and edit existing sources with `native_open_circuit`. Both return an initial `state`. `native_list_projects` attaches a single running Multisim process when no session is attached; runtime status distinguishes `running` from `session_attached`. `native_get_circuit_state` omits parameter metadata by default; `include_parameters: true` returns current page bounds, sheet selection, component refs and pins, wire routes, labels, content bounds and indexed parameters.

For a component already present, call `native_get_parameters(component_ref)` and select its electrical-value descriptor by `role`, `name` and `unit`. Write either a numeric `value` or an `expression`, never both:

```json
{"component_ref":"R1","index":1,"value":1000}
```

Here index 1 applies specifically to `RESISTOR_VIRTUAL`. Its index 0 is a model option, not resistance. Numeric values use the descriptor's unit; SPICE expressions such as `1k` can be supplied through `expression`.

## Batch edits

`native_edit_batch` takes a nonempty list of operations as one undo unit. Operations run in order; failure restores the checkpoint. Batch arguments use native operation keys, which differ from standalone tool parameter names:

By default `atomic: true` rolls back this entire batch on failure. Choose `atomic: false` to preserve completed steps and restore only the failing operation. Earlier calls remain committed in either mode. Error results contain the rollback scope, preserved step count, handle invalidation flag and fresh state; consume these before another edit. A first-operation target lookup failure keeps handles intact.

```json
{
  "operations": [
    {"operation":"place","arguments":{"name":"RESISTOR_VIRTUAL","ref":"R1","x":306,"y":108,"parameters":[{"index":1,"value":1000}]}},
    {"operation":"place","arguments":{"name":"RESISTOR_VIRTUAL","ref":"R2","x":504,"y":108,"parameters":[{"index":1,"value":1000}]}},
    {"operation":"wire","arguments":{"source":{"ref":"R1","pin":"2"},"target":{"ref":"R2","pin":"1"}}}
  ],
  "include_state": true
}
```

This is a resistor-chain fragment, not a complete simulation circuit. The example's pins `1` and `2` are the known `RESISTOR_VIRTUAL` pins; inspect other parts first.

Common batch operations:

| Operation | Arguments |
| --- | --- |
| `place` | `name, ref, x, y`, optional `family, group, manufacturer, parameters, anchor, pin` |
| `setParameter` | `ref, index`, exactly one of `value, expression` |
| `wire`, `connectEndpoint` | `source, target`, optional `points` for `connectEndpoint` |
| `move` | `ref, dx, dy` (relative displacement) |
| `moveLabel` | `ref, x, y`, optional `kind: reference | value` (absolute label center) |
| `transform` | `ref, angle` (finite degrees), or `ref, axis` (`horizontal` / `vertical`) |
| `route` | `id, points` |
| `autoWire` | `id` (Multisim native router, preserving wire ID and electrical endpoints) |
| `connectTouching` | optional `refs` list (current sheet if omitted) |
| `rename` | `ref, new_ref` |
| `addText` | `text, x, y` |
| `sheetSize` | `width, height` (positive native dimensions; the converted CUTRect work area must fit signed 32-bit fields) |

For other batch operations, consult the installed implementation or use the corresponding standalone tool with its published schema. Do not infer internal argument keys from tool names.

## Electrical wires and branches

Shared power symbols may have identical `ref` and `local_ref`. Use their current component IDs in `component_ref` or batch/endpoint `ref`. Physical wire ownership is determined by connector IDs; shared net names do not identify a specific placed symbol. Wire endpoints include `component_id`. Read fresh IDs after netlist refresh, undo, redo or rollback.

Standalone `native_connect_pins` accepts `source_ref, source_pin, target_ref, target_pin`. Endpoint tools accept `{"ref":"R1","pin":"2"}` or `{"junction_id":"<current junction ID>"}`.

- Read actual wire routes with `native_list_wires` or the current state. Wire vertices and pin positions share sheet units.
- `native_route_wire(wire_id, points)` replaces the route. Each point is `{"x":integer,"y":integer}`; first and last points must match the native electrical connectors exactly.
- For a branch, split the existing wire with `native_split_wire` at a point on its route, then connect to the returned `junction_id` with `native_connect_endpoints`.
- Use `native_reconnect_wire` to change electrical endpoints; adding text or editing vertices does not replace an endpoint connection.
- `native_configure_wiring` reads or sets native `autowire_on_connection`, `autowire_on_move`, `connect_touching` and `move_connection_limit` options. Settings restore on close or `reset: true`. Moves below the limit reroute through Multisim; other moves preserve attachments and route shape.
- With `connect_touching` enabled, placement and movement connect contacts automatically. `native_connect_touching` also processes existing contacts. Interior wire contacts create native branch junctions; ambiguous crossings of different nets return an error. Consume returned state after wire splitting.
- `native_auto_route_wire` defaults to Multisim's native router, preserving the wire ID and electrical endpoints. Native routing requires endpoints inside the actual sheet. `native_plan_wire_route` previews the MCP obstacle planner; choose `engine: obstacle` to apply its route with `clearance` in sheet units.
- Inspect `native_check_layout` for missing connector attachment, invisible wire pens, overlapping symbols and obstructed routes. Then inspect the exported schematic for presentation issues.

## Sheets and hierarchy

Select a sheet using its current `native_list_sheets` index. `native_create_sheet` creates an independent sheet. `native_create_subcircuit` creates a child sheet and parent symbol; select the child and add `native_create_hierarchical_port` connectors before wiring the parent. Read the newly returned parent pin names after adding ports.

`native_update_sheet(title, page, width, height)` edits the selected sheet in one transaction. `native_update_hierarchical_port(object_id, name, x, y)` renames/moves an existing child connector and updates its parent symbol. Existing component move/transform/rename tools also apply to subcircuit symbols; use the port updater for its electrical connector name. `native_move_junction(junction_id, x, y)` preserves branch connections and reroutes their ends. Coordinates returned by the native engine reflect grid snapping.

Native root window captions follow the filename after reopening; use `page` for a persistent root page name. Embedded child titles and page names are separate native fields. Sheet renames retain hierarchical component references.

## Free text

Read `state.texts` or `native_list_texts` for independent notes, including IDs, content, insertion coordinates, transform and bounds. Use `native_update_text(object_id, text?, x?, y?)` to change content and/or absolute insertion position while retaining formatting and ID. Omitted fields retain their values; `text: ""` clears the note. Use `native_delete_text(object_id)` or `native_delete_object(object_id)` to remove it. Component reference/value labels and generated wire net labels are separate objects with separate editing tools.

Batch/workflow operations are `updateText {id,text?,x?,y?}`, `deleteText {id}`, `updateSheet {title?,page?,width?,height?}`, `updatePort {id,name?,x?,y?}`, and `moveJunction {id,x,y}`. Text selectors also accept `object_id`. Bind `addText` results and use `{"$ref":"note.id"}` in later edits. Undo, rollback and native reopen can change IDs; use current state after these operations. Save normally to persist all edits.

Embedded model text may be shared by several components. `native_set_model_text` returns affected references across the project; inspect these before treating it as a single-instance change.

## Fit the saved sheet

`fit_content` and `region` affect image framing only. They restore the original page geometry after rendering. A correctly cropped image can therefore accompany an `.ms14` whose circuit is still outside its sheet.

For a finished schematic:

1. Read `page.bounds` and the complete `content_bounds` after placing, routing and adding text. Require `content.left >= page.left + margin`, `content.top >= page.top + margin`, `content.right <= page.right - margin` and `content.bottom <= page.bottom - margin`. A margin of 18–36 sheet units is usually sufficient. Repeat on each edited sheet.
2. For a new modest circuit, lay it out inside the initial sheet rather than placing it thousands of units away. If an existing layout just needs more space on the right or bottom, resize the real sheet with `native_edit_batch`:

   ```json
   {"operations":[{"operation":"sheetSize","arguments":{"width":1200,"height":900}}],"include_state":true}
   ```

   Compute the required dimensions from the actual content bounds and margin; these numbers are an example. Resizing the sheet preserves component positions and electrical connections. Merely increasing width and height does not fix negative left/top coordinates. Such a layout requires moving its complete contents inward, including text, branches and wire routes; moving only the components can leave other objects behind.
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
