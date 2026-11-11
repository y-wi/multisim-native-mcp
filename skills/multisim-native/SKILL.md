---
name: multisim-native
description: "Create, edit, wire, simulate and verify editable NI Multisim circuits through the multisim_native MCP server, using staged workflows for complete circuit tasks."
---

# Multisim Native

Use `multisim_native` for real Multisim objects and native simulation. Tool names below omit the client prefix.

## Choose the execution shape

For a complete circuit task, prefer **one `native_run_workflow` plan** covering the known stages. Read [references/workflows.md](references/workflows.md) for the schema, result references and complete examples. The server prepares component metadata, reads actual pins, refreshes handles and executes dependent steps internally. Return to the agent when library choices, ambiguous objects or failed electrical criteria require a design decision.

For a single adjustment, screenshot or diagnostic, use its individual tool. Do not wrap a one-step task in unnecessary preparation and analysis. Existing clients without workflow tools can use `native_edit_batch`; see [references/editing.md](references/editing.md).

- Use tool schemas already supplied by the client. Discover missing tools once when necessary; do not enumerate capabilities before every phase.
- Open a source with a workflow `session` stage (`mode: open`) or `native_open_copy`. Use `mode: create` for a new circuit and `mode: attach` for an explicitly selected existing window. Owned startup requires other Multisim windows to be closed. Closing an attached session detaches and leaves the user's window open.
- Consume initial state and prior results. Do not separately query runtime status, sheets, all components and all wires when the needed data is already available.
- Use `native_prepare_components` for **unknown component types whose pins or value slots affect the design**. Submit all those types together. Existing prepared metadata is cached for the session. Known indexed parameters and primary `value` placement can go straight into an edit stage.

## Plan once, execute by phase

1. Describe the known components, values, connections, analyses, acceptance criteria and output paths in one plan. Group related edits into a stage; up to 100 edits share a rollback checkpoint. Use `bind` names and `{"$ref":"binding.component.id"}` instead of asking the agent to read intermediate IDs. Results and bounded numeric offsets can feed later steps.
2. Use placement `value: 1000` or `value: "1k"` when the component has exactly one `role: value` slot. The executor resolves its index. For other parameters, select an explicit index or an unambiguous role/name. A resistor's model option is not its resistance.
3. Use exact named pins from known metadata. The executor resolves actual placed connectors and their coordinates before wiring. Unknown pin schemas need one consolidated preparation round, not a query after every placement.
4. Put measurements and criteria directly on the `analysis` stage. A voltage selector can use `{ref, pin}` with a bound component ID; current uses `{current: component}`. This avoids separate netlist, vector lookup, waveform read and verification calls for ordinary acceptance.
5. Follow with `layout`, `save` and `export` stages as requested. Analysis already performs netlist checking. `save` verifies an independently reopened copy by default. After `verification.passed: true`, a second close/open verification is unnecessary. Inspect the requested native export for visual acceptance.
6. For a plan spanning several agent calls, use `native_session_changes` and pass its `revision` as `expected_revision`. Reuse unchanged metadata. The server detects stale plans and rebinds uniquely identifiable objects across controlled native refreshes; ambiguous bindings stop execution.

## Wait and recover at decision boundaries

`native_run_workflow` waits up to 30 seconds by default. Inspect `status`: `complete` is finished; `running` needs `native_workflow_status(workflow_id, wait_timeout: 30)`. Keep a nonzero wait for ongoing work rather than repeatedly polling. `failed`, `needs_input`, `cancelled` and `interrupted` are not successful completion.

The result includes completed stages, the failed stage, diagnostics, key measurements and artifact paths. Fetch `detail: true` only when bindings or full diagnostics are needed. Use `native_control_workflow(action: resume)` to retry the unfinished tail explicitly; `replacement_steps` can replace that tail without rebuilding successful stages. After external edits, inspect the new state and supply its revision. Use `cancel` to interrupt analysis or stop at a native edit-slice boundary.

An edit-stage failure restores that stage, retaining earlier successful stages. Analysis and output failures preserve earlier edits and completed files. Automatic preparation and geometry repair do not justify changing electrical values or solver settings to force acceptance. Change the design when the evidence calls for it.

## Native geometry and values

- Coordinates use top-left sheet units, **96 units per inch**. The blank sheet is **960 × 720**. `anchor: center` or `anchor: pin` describes placement intent; grid snapping can change actual coordinates. Keep the complete drawing inside the actual sheet before saving. `fit_content` changes image framing only.
- Library names can resemble unrelated 3D parts. Check family/group and model metadata. An adjustable resistor is `RESISTOR_VIRTUAL`, family `RESISTOR`, group `Basic`; its primary resistance is index **1**, while index **0** is `model_option`.
- VCC/VEE symbols can share a reference. Bind their individual placement results or select current IDs. Do not treat a shared network name as a unique placed object. Standalone undo, redo and netlist refresh may invalidate raw IDs.
- A visually touching line is not a native electrical connection. Layout checks distinguish electrical attachment from drawn endpoint alignment. Use `repair_geometry` when geometry is defective; preserve electrical connectivity.
- Native samples use SI units: V, A, s and Hz. A 12 V divider with two 1 kΩ resistors should give **6 V and −0.006 A**. Never invent a scaling factor to make an incorrect current agree.

## Interactive displays

A workflow `interactive` stage configures, starts, waits for requested display states, captures several native frames and stops by default. Supply `active_component` and `expected_digit` for each capture. Multiplexed displays light successively; preserve each actual frame and its reported state. Use a `decode` stage on transient data to verify stable scanning over multiple cycles. A single lit frame is not numerical proof of the whole sequence.

Choose time steps for the fastest relevant signal. A 1 ms step with real-time pacing suits low-frequency LED behavior, not every multiplexed circuit. Stop interactive simulation before editing or numeric analysis. For individual controls and waveform details, read [references/analysis.md](references/analysis.md).

For permanent simulation settings, use `native_configure_interactive(persist: true, ...)` and then save, or add `save_to_source: true` when the user explicitly requests updating the original file. Source saves include a backup, external-edit detection and native reopen verification. `saved_to_file: false` means the document configuration still needs saving. Temporary session settings remain the default. A workflow `interactive` stage accepts `persist: true`; follow it with a `save` stage for a persistent output file.

## Deliver

Report the saved circuit and requested exports, measured acceptance and any remaining failed criterion. Distinguish numeric verification from visual inspection. If the user will validate simulation themselves, deliver the edit and requested geometry checks without adding experiments.
