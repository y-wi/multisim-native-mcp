# Staged workflows

## Tools

- `native_run_workflow(plan, wait_timeout=30)` starts a workflow and waits for a terminal state or decision boundary.
- `native_workflow_status(workflow_id, wait_timeout=30, detail=false)` waits for its result. `detail=true` retrieves stored bindings and diagnostics.
- `native_control_workflow(workflow_id, action, replacement_steps, wait_timeout, expected_revision)` cancels or explicitly resumes an unfinished tail.
- `native_prepare_components(components, refresh=false)` prepares all unknown types in one call in an open session. Probes restore the drawing; raw pointer IDs may change. Workflows rebind their aliases internally.
- `native_session_changes(since_revision, include_parameters=false)` returns a revision and full/incremental state. An unchanged revision produces `changed: false`.

## Plan and references

`plan.steps` contains 1–100 typed stages with unique `id` values. A workflow supports at most 1,000 edits and a configurable runtime limit (`max_runtime`, default 600 s, maximum 7,200 s). The runtime budget requests cancellation; native calls finish or interrupt at their supported boundaries.

| kind | Main fields |
| --- | --- |
| `session` | `mode: create/open/attach`, `title`, `source_path`, `pid`, `project_index`; first stage only |
| `select` | `components: {name: {ref/local_ref/id, pin?, x?, y?}}`; unique native object selection |
| `prepare` | `components: [{name, family, group, manufacturer}]` |
| `wiring` | `autowire_on_connection`, `autowire_on_move`, `connect_touching`, `move_connection_limit` |
| `edit` | `operations: [{operation, arguments, bind?}]`; one rollback unit |
| `netlist` | explicit source inspection; ordinary analysis checks it internally |
| `layout` | `repair_geometry: false`, `require_no_warnings: false` |
| `analysis` | `options`, `measurements`, `criteria` |
| `verify` | `raw_path`, `measurements`, `criteria`; reuse an existing analysis |
| `decode` | `raw_path`, `digits`, `expected`, `options` for scanned-display decoding |
| `save` | absolute `output_path`, `overwrite`, `allow_off_page`, `verify` |
| `export` | absolute `output_path`, `overwrite`, `dpi`, `fit_content`, `show_frame`, `show_grid` |
| `interactive` | time steps, `real_time`, `persist: false`, `captures`, `overwrite`, `stop_after: true` |
| `close` | last stage; detach leaves an attached window open |

`options` on an analysis uses `analysis: op/tran/ac`, `step`, `stop`, `use_initial_conditions`, `ac_sweep`, `ac_points`, `ac_start` and `ac_stop`.

An edit operation's `bind` stores its result; every completed stage also binds its result to its `id`. Use `{"$ref":"lower.component.id"}`, `{"$ref":"split.junction_id"}` or `{"$ref":"dc.raw_path"}`. References must name earlier results. Array indices use dot notation. `{"$add":[value,9]}` and `{"$sub":[value,9]}` compute bounded two-term numeric offsets; they can contain references. No executable code is accepted.

A placement's `arguments.value` selects its unique primary-value slot; a string is a SPICE expression. `setParameter` can use `role: value` and an optional parameter `name` instead of `index`. Ambiguous slots return their descriptors rather than selecting a model option.

Within an edit stage, the executor prepares metadata, resolves dependencies and sends native groups of at most eight operations. The groups yield to Multisim between slices and share the stage's rollback checkpoint. Library selection, actual pin resolution, native handle refresh and subsequent argument binding happen locally.

## Complete divider example

Use the reusable [divider plan](../assets/workflow_divider.json). Create its output directory and replace the two output paths before submitting. It creates a native 12 V divider, checks layout, verifies 6 V and −6 mA, saves with readback, exports and closes. No separate netlist or waveform-read call is required.

The core dependency pattern is:

```json
{"id":"build","kind":"edit","operations":[
  {"operation":"place","bind":"upper","arguments":{"name":"RESISTOR_VIRTUAL","family":"RESISTOR","group":"Basic","ref":"R1","x":360,"y":180,"anchor":"pin","pin":"1","value":"1k"}},
  {"operation":"place","bind":"lower","arguments":{"name":"RESISTOR_VIRTUAL","family":"RESISTOR","group":"Basic","ref":"R2","x":540,"y":180,"anchor":"pin","pin":"1","value":"1k"}},
  {"operation":"wire","arguments":{"source":{"ref":{"$ref":"upper.component.id"},"pin":"2"},"target":{"ref":{"$ref":"lower.component.id"},"pin":"1"}}}
]}
```

This fragment demonstrates binding; the complete file includes its source, ground and return connections.

Analysis selectors avoid guessing vector numbering:

```json
{"id":"dc","kind":"analysis","options":{"analysis":"op"},"measurements":[
  {"id":"midpoint","metric":"mean","signal":{"ref":{"$ref":"lower.component.id"},"pin":"1"}},
  {"id":"supply_current","metric":"mean","signal":{"current":{"$ref":"supply.component.id"}}}
],"criteria":[
  {"id":"midpoint","target":6,"absolute_tolerance":0.01},
  {"id":"supply_current","target":-0.006,"absolute_tolerance":0.00001}
]}
```

Explicit waveform names remain supported. For AC gain/phase, `reference` can also be a `{ref,pin}` selector.

## Shared power symbols and branches

For an existing drawing, a `select` stage can distinguish repeated references by an exact pin name and coordinates; its result is referenced as `selection.components.name.id`. Place each new power symbol with a distinct bind name, then use its result ID even if native netlist refresh normalizes several references to VCC or VEE. Bind a `splitWire` result to connect subsequent branches through `{"junction_id":{"$ref":"branch.junction_id"}}`. A controlled reopen rebinds uniquely identifiable physical objects. Overlapping indistinguishable objects require a selection decision.

## Live capture and recovery

```json
{"id":"live","kind":"interactive","time_step":0.001,"max_time_step":0.001,"real_time":true,"captures":[
  {"output_path":"C:/Circuits/digit-a.png","active_component":"DS1","expected_digit":"8","wait_timeout":15},
  {"output_path":"C:/Circuits/digit-b.png","active_component":"DS2","expected_digit":"3","wait_timeout":15}
]}
```

Each image is a real instantaneous native frame. The executor waits locally for the requested digit and stops after the captures. Set time steps for the circuit's actual signal rates. For numerical scan acceptance, put `decode` after a transient stage and reference its RAW path.

Check `status` before reporting completion. Default results contain key acceptance and output paths; the detailed record retains raw analysis, bindings, completed phases, failure diagnostics and call statistics. `stats.external_calls` counts workflow API calls, not model reasoning turns. `stats.native_calls` counts host RPCs.

On failure, inspect the failed phase and its diagnostics, then resume with a replacement tail. Completed stages are retained. Failed edit stages roll back as one unit; analysis and file-output failures retain earlier successful edits and files. Reuse a failed acceptance run's `failure.details.raw_path` with a `verify` stage when only criteria need correction. A service restart marks unfinished work interrupted; resume can reopen the saved successful phase. Revision conflicts require inspection and the current `expected_revision`.
