# Changelog

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
