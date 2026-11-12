---
name: multisim-native
description: "Create, edit, wire, simulate and save native Multisim circuits in the task workspace through the multisim_native MCP server."
---

# Multisim Native

Use `multisim_native` for editable Multisim objects and native simulation. Tool names below omit the client prefix.

## Work on the actual document

- For a new circuit, determine the output directory from the current task context (normally the current working directory), choose an unused `.ms14` filename, and pass the absolute `output_path` to `native_create_circuit(output_path, title)` or a workflow `session` with `mode: create`. Use a user-specified path when provided. The MCP operates on file paths; it has no global project/workspace directory. Never use AppData, a recovery directory or a packaged template as the deliverable.
- For an existing circuit use `native_open_circuit(source_path)` or a workflow `session` with `mode: open`. This edits the actual source. A single existing Multisim window is reused. Use `native_attach` to select a specific process/document when needed; attached windows stay open on detach.
- Save the requested circuit changes. Use `native_save_source` or a workflow `save` stage without an output path to update the current document. Closing through `native_close_copy` or a workflow `close` stage also saves pending changes by default; `save_changes: false` skips saving (detached user windows retain unsaved edits).
- Use `native_save_copy(output_path)` for a requested Save As. In direct mode that output becomes the current document. Saving the current path routes to normal source save without an additional overwrite flag. Backups, checkpoints, logs and verification copies are managed internally.
- Use `native_open_copy` / `session.isolated_copy: true` only for a requested comparison, diagnostic or preserved-original experiment. Pass an explicit `output_path` in the current task directory for its comparison file. Never choose copy mode merely because an ordinary edit might fail; native checkpoints handle recovery.

## Choose a suitable execution shape

For a complete circuit task, prefer one `native_run_workflow` plan for the known stages; read [references/workflows.md](references/workflows.md) for schemas and examples. For a local adjustment use the corresponding tool or edit batch. Reuse returned state and prepared metadata rather than querying all objects between every operation.

Group related edits, bind results and refer to actual returned pins/IDs. Prepare unfamiliar library types when their pin names or parameter slots are uncertain. Known parts can be placed directly. Include analysis and numeric criteria when the task calls for electrical verification; use saved native readback for persistence verification. A successful save does not need another manual close/open cycle. Inspect the requested export for visual acceptance.

Use `native_workflow_status` waits for ongoing work. Failed or interrupted work is unfinished; inspect the failed stage, correct the cause and resume its tail. Rollback, undo, redo and controlled native refreshes can invalidate IDs; use returned current state or workflow bindings. Internal checkpoints preserve the actual workspace/source identity during recovery.

The MCP imposes no task runtime, operation-count, coordinate-area, sample-count or image-pixel quotas. Use `max_runtime` only for a user-requested deadline; it is disabled by default. Status waits and pagination are response options, not execution ceilings. Native data types and actual simulator/allocator failures still apply.

## Native details that affect correctness

- Coordinates are top-left sheet units, 96 per inch. The blank sheet is 960 by 720; inspect actual bounds before layout. `fit_content` crops an export and does not resize the document. Choose sheet size and export framing for the requested result. Off-page content saves normally and its bounds remain visible in diagnostics.
- A visible touching line is not sufficient evidence of electrical attachment. Connect actual native pins and verify geometry/connectivity when relevant. VCC/VEE symbols can share references; use current component IDs or bound placement results to distinguish them.
- For `RESISTOR_VIRTUAL`, resistance is parameter index 1; index 0 is a model option. Prefer returned value descriptors for other types. Native values use SI units; a 12 V, two 1 kilohm divider has 6 V midpoint and source current -0.006 A.
- Choose time steps for the fastest relevant signal and check the resulting waveform when changing accuracy. Low-frequency LED circuits can use 1 ms steps; multiplexed displays may need smaller steps. Capture actual display frames rather than synthesizing animation states. Native edits/configuration require a stopped simulator.

For detailed editing/geometry contracts read [references/editing.md](references/editing.md); for analysis and display verification read [references/analysis.md](references/analysis.md).

## Persistent configuration in 0.5.0

`native_simulation_settings` discovers existing analysis types, typed scalar paths, solver options and revision before editing. It supports independent `interactive` and `analysis` scopes and native custom/default solver selection. Use `solver_options` for tolerances, integration, convergence, temperature and flags; null/false disables an override. Integer path tokens select duplicate labels and require the returned `expected_revision`. Existing scalar fields are editable; the API does not create empty native lists or new analysis instances. Numeric execution supports OP/AC/TRAN; other profile settings can be saved for native Multisim use.

`native_configure_interactive` and workflow interactive stages retain configuration in the native document by default. Use `persist: false` only for an intentionally temporary run. Configuration changes are written to disk by normal save/close; `save_to_source: true` saves a single configuration transaction immediately. `saved_to_file: false` means that call performed no disk save.

Numeric analysis tools keep explicit run arguments local by default. Use `persist: true` to retain a run's analysis profile, or `use_saved_settings: true` to execute its stored analysis and solver options. RAW/CSV results remain external. Use `native_configure_sheet_display` for saved grid, border and bounds. `native_configure_wiring(persist: true)` commits application-wide preferences rather than circuit content.

`native_persistence_capabilities` explains every tool's ownership. Runtime clock/animation phase, undo stacks, export flags and experiment/workflow records have session/external ownership. Title-block presence follows native title-block objects after loading; the export rendering flag is not a portable document boolean.

## Deliver

Report the actual saved workspace/source path, requested exports and relevant verification. Do not substitute a cached copy or create extra versions the user did not request.
