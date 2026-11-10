# Native editing contracts

## State and parameters

Creation and opening return an initial `state`. `native_get_circuit_state(include_parameters: true)` returns current page bounds, sheet selection, component refs and pins, wire routes, labels, content bounds and indexed parameters.

For a component already present, call `native_get_parameters(component_ref)` and select its electrical-value descriptor by `role`, `name` and `unit`. Write either a numeric `value` or an `expression`, never both:

```json
{"component_ref":"R1","index":1,"value":1000}
```

Here index 1 applies specifically to `RESISTOR_VIRTUAL`. Its index 0 is a model option, not resistance. Numeric values use the descriptor's unit; SPICE expressions such as `1k` can be supplied through `expression`.

## Batch edits

`native_edit_batch` takes 1–100 operations as one undo unit. Operations run in order; failure restores the checkpoint. Batch arguments use native operation keys, which differ from standalone tool parameter names:

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
| `place` | `name, ref, x, y`, optional `family, group, manufacturer, parameters` |
| `setParameter` | `ref, index`, exactly one of `value, expression` |
| `wire`, `connectEndpoint` | `source, target`, optional `points` for `connectEndpoint` |
| `move` | `ref, dx, dy` (relative displacement) |
| `moveLabel` | `ref, x, y` (absolute label center) |
| `transform` | `ref, angle` (multiples of 90), or `ref, axis` (`horizontal` / `vertical`) |
| `route` | `id, points` |
| `rename` | `ref, new_ref` |
| `addText` | `text, x, y` |
| `sheetSize` | `width, height` (96–8192 sheet units) |

For other batch operations, consult the installed implementation or use the corresponding standalone tool with its published schema. Do not infer internal argument keys from tool names.

## Electrical wires and branches

Standalone `native_connect_pins` accepts `source_ref, source_pin, target_ref, target_pin`. Endpoint tools accept `{"ref":"R1","pin":"2"}` or `{"junction_id":"<current junction ID>"}`.

- Read actual wire routes with `native_list_wires` or the current state. Wire vertices and pin positions share sheet units.
- `native_route_wire(wire_id, points)` replaces the route. Each point is `{"x":integer,"y":integer}`; first and last points must match the native electrical connectors exactly.
- For a branch, split the existing wire with `native_split_wire` at a point on its route, then connect to the returned `junction_id` with `native_connect_endpoints`.
- Use `native_reconnect_wire` to change electrical endpoints; adding text or editing vertices does not replace an endpoint connection.
- `native_plan_wire_route` previews an obstacle-aware orthogonal path. `native_auto_route_wire` applies a path to one selected wire as an undoable edit. `clearance` is in sheet units.
- Inspect `native_check_layout` for missing connector attachment, invisible wire pens, overlapping symbols and obstructed routes. Then inspect the exported schematic for presentation issues.

## Sheets and hierarchy

Select a sheet using its current `native_list_sheets` index. `native_create_sheet` creates an independent sheet. `native_create_subcircuit` creates a child sheet and parent symbol; select the child and add `native_create_hierarchical_port` connectors before wiring the parent. Read the newly returned parent pin names after adding ports.

Embedded model text may be shared by several components. `native_set_model_text` returns affected references across the project; inspect these before treating it as a single-instance change.

## Image export

Example arguments for `native_export_image`:

```json
{"output_path":"C:/Circuits/divider.png","dpi":192,"fit_content":true,"padding":36}
```

Use an existing absolute output directory. PNG and BMP are supported. `dpi` is 36–600, `scale` applies additional scaling, and the pixel budget is 32 million. Rendering uses the native engine and leaves the schematic geometry unchanged.

For a crop, replace `fit_content` with `region: {"left":100,"top":80,"right":700,"bottom":500}` in absolute sheet units. `region` and `fit_content` are mutually exclusive. If whole-page export is blank because components are outside the page, read the page and content bounds, then choose content fitting, a region, or a deliberate layout edit.

Move an overlapping reference with `native_move_component_label(component_ref, x, y)`. Coordinates specify the absolute label center; read `state.components[].labels` for actual bounds. Grid snapping can affect symbol placement, so use returned positions rather than requested coordinates when checking alignment.
