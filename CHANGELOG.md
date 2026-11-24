# Changelog

## Unreleased

- Add native support for all 19 right-hand Instruments toolbar virtual instruments (Multimeter, Function Generator, Wattmeter, 2-Ch/4-Ch Oscilloscope, Bode Plotter, Frequency Counter, Word Generator, Logic Converter, Logic Analyzer, IV Analyzer, Distortion Analyzer, Spectrum Analyzer, Network Analyzer, Agilent 33120A/34401A/54622D, Tektronix TDS 2024, and Current Probe) using Multisim's exported C++ APIs without GUI automation or hardcoded RVAs.
- Add 5 dedicated MCP tools (`native_list_instruments`, `native_place_instrument`, `native_get_instrument_settings`, `native_set_instrument_settings`, `native_export_instrument_data`), expanding the default catalog to 91 tools, plus `matching_instruments` hints in `native_search_library`.
- Support virtual instrument placement and configuration inside `native_edit_batch` and `native_run_workflow` (`place_instrument` / `set_instrument_settings`), live `instrument_readouts` in `native_interactive_status(include_displays=true)`, `.scp`/`.bod` trace export, and full `.ms14` save-reopen verification of persistent instrument settings.

## 0.5.4

- Detect installed MCP clients from the Windows installer and register the server in one or more supported clients. Add CLI commands to list clients and install the skill separately.
- Bundle the Multisim skill with the wheel, sync it during client setup, and expose its guides through MCP resources.
- Add a 22-component pin and parameter reference and workflow templates for voltage dividers, RC filter analysis, and live display and LED readouts.
- Rebind component IDs after topology refreshes during waveform measurements and display decoding. Report selectors that can no longer be resolved.
- Check wire net names for conflicts across sheets in the same electrical scope, including conflicts with global power nets.

## 0.5.3

- Sweep an independent voltage or current source with `native_run_dc_sweep` and export RAW and CSV results.
- Trace circuit connectivity with `native_get_connectivity` and map pins to waveform vectors with `native_resolve_signal`. Use pin selectors in standalone waveform measurements and verification.
- Measure transient settling time, signal timing and AC response. Export waveform and Bode plots as SVG or PNG, with overlays for traces that share units.
- Read hexadecimal displays, LED states and digital probe levels during interactive simulation. Capture hexadecimal digits in workflows.
- Filter the component library by manufacturer and availability of a simulation model. Set named parameters when placing or editing components, including supported potentiometers.
- Fit schematic contents to the sheet, plan wire routes around components and select sheets in multi-sheet workflows. Keep reference labels in sync with component edits and distinguish net labels from electrical connections when editing wires.
- Install directly into Antigravity and standard JSON MCP clients. Manage older environments and expired session files with the `cleanup` command.

## 0.5.2

- Release completed numeric simulation sessions before interactive starts, and apply the requested wait timeout to cleanup as well as the start transition.
- Honor workflow cancellation during component preparation and between operations inside native edit slices, rolling back cancelled stages before accepting further edits.
- Place rotated/mirrored symbols with final pin/center anchoring and compact engineering value expressions.
- Reuse an active direct document when opening the same path and assign native identities to repeated default power-symbol references.
- Diagnose missing hidden CMOS/TTL power rails and enrich native simulation failures with command context.
- Distinguish symbol-body collisions from movable text-label collisions.

## 0.5.1

- Preserve valid saved hierarchical circuits when deleting connected ports, including undo and redo.
- Unify standalone, batch and workflow selector names, and use one idempotent explicit-connection engine.
- Keep compatibility aliases callable while presenting a smaller preferred tool catalog.
- Return primary/named parameter slots by default, with explicit full metadata reads.
- Report ID remapping on native refreshes and field-level save differences with expected and actual values.
- List, edit and delete free text in place, including workflow bindings, undo and verified saves.
- Update sheet properties, hierarchical connector names/positions and branch junction positions through dedicated tools.
- Verify persistent wire names and visibility independently of generated node text, and report precise save differences.
- Unify standalone and batch deletion selectors; support generated net-label removal while retaining its wire.
- Honor verification options when saving the current source, including workflow saves.
- Discover running Multisim processes, attach a single existing process when listing projects, and return compact circuit state by default.
- Clarify placement anchors and return pin offsets relative to the actual anchor.

## 0.5.0

- Edit existing `.ms14` sources directly and create new circuits at a specified filename. Normal save and close retain changes in the current document.
- Configure and save 19 native analysis profiles and 44 solver options, with independent interactive and analysis settings.
- Execute saved OP, AC and transient settings, including custom solver options.
- Save grid, border, sheet bounds, embedded models, annotations and page names; retain application wiring preferences separately.
- Reuse an existing Multisim window and manage recovery backups automatically.
- Support fractional rotations, off-page connections and high-resolution exports while preserving native wire attachments.
- Run workflows without a default deadline; remove fixed workload quotas for edits, analysis samples, parameter sweeps and exports.
- Update the MCP interface to 77 tools and refresh the agent skill and circuit examples.

## 0.4.1

- Persist interactive time steps and real-time pacing in native document simulation settings, without mouse automation or circuit binary rewriting.
- Support explicit source-file saves with backups, conflict detection and independent native reopen verification.
- Verify that all document simulation settings survive native saves, preserving numeric-analysis definitions and other solver options.
- Retain temporary session configuration by default; allow workflow interactive stages to persist settings for a later save stage.

## 0.4.0

- Execute typed circuit workflows with dependent edits, native analysis, acceptance criteria, saved-copy verification and exports.
- Bind intermediate results and resolve actual pins and primary-value parameter slots inside the server.
- Prepare library components in batches and cache session metadata.
- Group native edits into responsive UI-thread slices with rollback checkpoints per edit stage.
- Wait for completion, cancel running work and resume unfinished stages with persistent diagnostics.
- Track session revisions, return incremental state and rebind objects across controlled native refreshes.
- Capture multiple requested live display states in one interactive stage.
- Report workflow call counts, native RPC work and stage timings.
- Update the agent skill with complete workflow examples and recovery guidance.

## 0.3.9

- Move and rotate shared-reference power symbols by object ID, updating only their own physical pin attachments.
- Preserve object identity during native rerouting and touching-pin processing.
- Limit symbol deletion to its own attached wires when power references are shared.
- Include component IDs in wire endpoints and support ID-based wire filtering.
- Return candidate IDs for ambiguous edit targets without changing circuit state.
- Verify persisted label transforms instead of cached text extents when reopening saved circuits.

## 0.3.8

- Add native automatic wiring on connection, rerouting on component movement and touching-pin connections.
- Configure session wiring settings and movement connection limits; restore original settings on close.
- Create native branch junctions for pins touching wire interiors and reject ambiguous contacts at crossings.
- Reroute existing wires with Multisim's router while preserving wire IDs, labels and electrical endpoints.
- Support native routing and touching connections in undoable edit batches.
- Reject off-page native routing endpoints before creating clamped wires.

## 0.3.7

- Write native image and netlist files through Unicode Windows paths, and stage SPICE file transfers automatically.
- Remove temporary bitmap and transport files after use.
- Save over existing outputs without native overwrite dialogs; preserve backups and document paths.
- Check every saved sheet for off-page content and verify saved copies through native reopen while retaining active object handles.
- Include native failure details in analysis errors.
- License the project under MIT.

## 0.3.6

- Add configurable native interactive time steps and real-time pacing for low-frequency display circuits.
- Report the effective interactive startup parameters and preserve numeric-analysis settings.

## 0.3.5

- Add native interactive simulation start, pause, resume, stop and observed transition status.
- Expose simulated time and live seven-segment display states.
- Capture actual runtime display frames through the native schematic renderer, with optional scan-phase selection.
- Clean up numeric analysis sessions before entering interactive simulation.
- Prevent circuit edits and netlist regeneration during active interactive simulation.

## 0.3.4

- Repair off-grid symbol and junction graphics together with wire endpoints, preserving electrical attachments.
- Expose drawn connector positions and detect visible gaps in layout checks.
- Preserve unrepaired geometry in undo checkpoints and persist aligned geometry when saving.
- Serialize large native state responses before RPC transport to prevent JsonNode copy crashes.

## 0.3.3

- Unify measurement and criterion IDs, publish nested request schemas and identify invalid fields before execution.
- Refresh native value labels after parameter edits and keep rotated labels upright and separated from symbols.
- Add pin and symbol-center placement anchors with actual-position metadata.
- Return explicit rollback scope and refreshed state; support keeping completed batch operations.
- Add independent frame and grid controls for schematic image export.
- Distinguish actual analysis errors from cumulative native status records.

## 0.3.2

- Guide agents to fit and reopen saved sheets before accepting cropped schematic images.
- Add a portable agent skill for native editing, simulation and numeric verification.
- Expose sheet and printing-paper dimensions, content bounds and complete circuit state.
- Keep automatic wire routes attached to actual pin coordinates outside page boundaries.
- Add library family/group filters, model metadata and primary-parameter descriptions.
- Support inline placement parameters and batch state results.
- Preserve object handles after geometry and parameter changes; return refreshed state after topology updates.
- Render native high-resolution images with DPI, scale, region and content fitting.
- Add native reference-label positioning.
- Report waveform and CSV units explicitly in SI.

## 0.3.1

- Add DeepSeek Harness profile installation and configuration export.
- Update existing MCP entries without duplicating connections; preserve profile settings and comments.
- Reuse compatible installed environments and verify the STDIO connection.
- Align rotated and copied symbol graphics with their electrical pins before saving and exporting.

## 0.3.0 — 2026-11-10

- Install upgrades into independent environments while an existing MCP server is running.
- Add native AC linear, decade and octave sweeps with complex RAW/CSV output.
- Record analysis command stages, explicit transient initial conditions and mixed analog/digital plots.
- Add time-weighted measurements, numeric criteria and scanned seven-segment decoding.
- Add bounded parameter sweeps, constraints, candidate ranking and parameter restoration.
- Persist background experiments, cancellation, restart state and explicit checkpoint replay.
- Export Chinese or English HTML, Markdown, CSV, circuit PNG and waveform SVG reports.
- Check native connector attachment and layout; plan and apply obstacle-aware wire routes.

## 0.2.2 — 2026-11-10

- Make reference-profile hash and version comparisons informational during startup and process attachment.
- Determine installation readiness from runtime availability.
- Keep module comparisons in runtime diagnostics.

## 0.2.1 — 2026-11-10

- Publish 44 native MCP tools for Multisim 14.3.
- Add Python packaging, a Windows installer and MCP client configuration commands.
- Preserve wire drawing attributes when splitting connections and creating branches.
- Use the V8 script runtime and wait for application readiness before native initialization.
- Store working copies and session artifacts in the user's application data directory.
- Add English and Simplified Chinese documentation, examples and automated tests.
