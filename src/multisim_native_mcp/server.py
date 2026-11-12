"""STDIO MCP endpoint. stdout is reserved for JSON-RPC."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from functools import wraps
from pathlib import Path
import re
import json
from typing import Literal
from .service import EditorService,NativeEditError
from mcp.types import CallToolResult,TextContent
from .jobs import ExperimentManager
from . import __version__
from .contracts import MeasurementRequest,AcceptanceCriterion,normalize_measurements,normalize_criteria
from .workflow_contracts import ComponentRequest,WorkflowPlan,WorkflowStage
from .workflows import WorkflowManager,NeedsInput
from .settings import SimulationSettingChange,Scalar

host = EditorService()
experiments = ExperimentManager(host)
workflows = WorkflowManager(host)


def checked(function):
    @wraps(function)
    def execute(*args, **kwargs):
        try:
            if workflows.active and function.__name__ not in {
                'native_runtime_status','native_workflow_status','native_control_workflow',
                'native_read_waveform','native_measure_waveform','native_verify_waveform','native_decode_seven_segment'}:
                raise RuntimeError('A workflow is running; wait with native_workflow_status or cancel it')
            if experiments.active and function.__name__ not in {
                'native_runtime_status','native_experiment_status','native_list_experiments','native_cancel_experiment',
                'native_workflow_status',
                'native_read_waveform','native_measure_waveform','native_verify_waveform','native_decode_seven_segment'}:
                raise RuntimeError('A native experiment is running; inspect or cancel it first')
            return function(*args, **kwargs)
        except NativeEditError as error:
            return CallToolResult(isError=True,structuredContent=error.details,
                content=[TextContent(type='text',text=json.dumps(error.details,ensure_ascii=False))])
        except NeedsInput as error:
            detail={'error':str(error),'needs_input':True,'details':error.result}
            return CallToolResult(isError=True,structuredContent=detail,
                content=[TextContent(type='text',text=json.dumps(detail,ensure_ascii=False))])
        except Exception as error:
            raise ToolError(str(error)) from error
    return execute
server = MCPServer('multisim-native', version=__version__,
                   instructions='Create native circuits in the task workspace and edit existing source files directly. '
                   'Use native_open_circuit or native_create_circuit with explicit file paths from the task context. '
                   'Use native_open_copy only for requested comparisons or diagnostics. Save to the current source; recovery files are internal. '
                   'For complete tasks, prefer native_run_workflow with dependent edits, analysis acceptance, save and export in one plan. '
                   'Use result bindings instead of intermediate ID queries and wait with native_workflow_status rather than frequent polling. '
                   'Read exact pin names before wiring; save results before closing. '
                   'For repeated power references, select a current component ID from the circuit state. '
                   'Undo, redo and netlist refresh can invalidate memory IDs; reread objects afterward. '
                   'Read sheet bounds from the initial state or native_get_circuit_state before placing components. '
                   'Coordinates use top-left sheet units, 96 per inch, and may snap to grid. '
                   'Use individual tools or native_edit_batch for local adjustments and consume returned state. '
                   'Waveform values use SI units; verify source current as well as output voltage. '
                   'Native Multisim schematic editing and analog analysis.')


@server.tool()
@checked
def native_prepare_components(components: list[ComponentRequest], refresh: bool = False) -> dict:
    """Prepare 1-50 library types together in the current session. Resolve exact candidates, probe actual pins and parameter slots, cache session metadata and restore the original drawing. Ambiguities return one consolidated issue list. Probe restoration invalidates native handles; consume the returned revision or use workflow result bindings."""
    return workflows.prepare(components,refresh)


@server.tool()
@checked
def native_run_workflow(plan: WorkflowPlan, wait_timeout: float = 30.) -> dict:
    """Execute a typed circuit workflow: session, prepare, select, edit, wiring, netlist, layout, analysis with measurements/criteria, verify, decode, save, export, interactive captures, close. Result references use {\"$ref\":\"binding.component.id\"}; edit operations bind their result with bind. Native edits run in bounded slices with one rollback checkpoint per edit stage. Waiting is configurable; long jobs return an ID. Return summaries and a detailed record path. Existing single-step tools remain available for local adjustments."""
    return workflows.start(plan,wait_timeout)


@server.tool()
@checked
def native_workflow_status(workflow_id: str, wait_timeout: float = 30., detail: bool = False) -> dict:
    """Wait for the requested duration (30s by default) for workflow completion, failure or a decision boundary. Default returns stage outcomes, acceptance, outputs and call statistics. detail=true reads stored bindings and diagnostics. Use a nonzero wait instead of frequent polling."""
    return workflows.status(workflow_id,wait_timeout,detail)


@server.tool()
@checked
def native_control_workflow(workflow_id: str, action: Literal['cancel','resume'],
        replacement_steps: list[WorkflowStage] | None = None, wait_timeout: float = 30.,
        expected_revision: str | None = None) -> dict:
    """Cancel at a native edit-slice boundary or interrupt analysis. Explicitly resume an unfinished workflow from its failed stage, retaining successful stages. Optional replacement_steps replace the remaining tail. Revision conflicts require a fresh expected_revision. A saved successful phase can be reopened after a service restart."""
    replacements=[s.model_dump(exclude_none=True) for s in replacement_steps] if replacement_steps else None
    return workflows.control(workflow_id,action,replacements,wait_timeout,expected_revision)


@server.tool()
@checked
def native_session_changes(since_revision: str | None = None, include_parameters: bool = False) -> dict:
    """Read a session revision and full or incremental native state. Passing the current revision returns changed=false. A known previous revision returns changed components, removed IDs, current wires and page. Unknown revisions return the full state. Use the revision to reject stale workflow plans."""
    return workflows.session_state(since_revision,include_parameters)


@server.tool()
@checked
def native_runtime_status() -> dict:
    """Read runtime availability and reference-profile hash diagnostics without starting Multisim."""
    return host.runtime_status()


@server.tool()
@checked
def native_persistence_capabilities() -> dict:
    """Audit every MCP tool's persistence ownership: native circuit settings/edits, application preferences, external results/records, runtime state or inspection. Reports exact save mechanisms and saved-document verification coverage without opening Multisim. Runtime execution state and external files are not claimed to be embedded in .ms14."""
    from .persistence import persistence_capabilities
    return persistence_capabilities()


@server.tool()
@checked
def native_diagnostics() -> dict:
    """Read captured native netlist errors, including background Netlist Viewer updates, without a modal dialog."""
    if not host.agent: return {'netlist_errors':[]}
    return host.agent.exports_sync.diagnostics()


@server.tool()
@checked
def native_open_circuit(source_path: str) -> dict:
    """Open an existing .ms14 file directly for editing. Reuse a single running Multisim, selecting/opening the file while preserving other documents. Normal save/close saves this file. Backups and checkpoints stay internal."""
    return {**host.open_circuit(source_path),'state':host.call('circuitState',{'include_parameters':True})}


@server.tool()
@checked
def native_open_copy(source_path: str,output_path: str | None = None) -> dict:
    """Create an explicit comparison copy. output_path is an absolute unused .ms14 filename; when omitted the copy is saved beside the source. Ordinary editing uses native_open_circuit. Normal close saves only this copy."""
    return {**host.open_copy(source_path,output_path),'state':host.call('circuitState',{'include_parameters':True})}


@server.tool()
@checked
def native_list_components() -> dict:
    """Read native component references, transforms, named pin IDs, coordinates and connection counts."""
    return host.call('components')


@server.tool()
@checked
def native_get_circuit_state(include_parameters: bool = True) -> dict:
    """Read page bounds in sheet units, content bounds, components, named pins, wires and optional parameter metadata in one call. Origin is top-left; 96 sheet units per inch. Paper dimensions are separate from sheet dimensions."""
    return host.call('circuitState',{'include_parameters':include_parameters})


@server.tool()
@checked
def native_move_component_label(component_ref: str,x: int,y: int,kind: Literal['reference','value'] = 'reference') -> dict:
    """Move the reference or value label center to absolute sheet coordinates without moving its symbol, pins or wires. Read labels with kind/text/bounds from circuit state."""
    return host.edit('moveLabel',{'ref':component_ref,'x':x,'y':y,'kind':kind})


@server.tool()
@checked
def native_list_wires(component_ref: str | None = None) -> dict:
    """Read actual native wire endpoints and routed vertices. Filter by reference for all matching symbols, or by current component ID for one symbol. Endpoints include component_id."""
    result = host.call('wires')
    if component_ref is not None:
        result['wires'] = [wire for wire in result['wires'] if any(component_ref in (wire[end].get('ref'),wire[end].get('component_id')) for end in ('source', 'target'))]
    return result


@server.tool()
@checked
def native_connect_pins(source_ref: str, source_pin: str, target_ref: str, target_pin: str) -> dict:
    """Create a real native electrical wire between exact named pins through CreateWireBase. Idempotent for a direct existing wire."""
    return host.edit('wire', {'source': {'ref': source_ref, 'pin': source_pin},
                              'target': {'ref': target_ref, 'pin': target_pin}})


@server.tool()
@checked
def native_configure_wiring(autowire_on_connection: bool | None = None, autowire_on_move: bool | None = None,
                            connect_touching: bool | None = None, move_connection_limit: int | None = None,
                            reset: bool = False, persist: bool = False) -> dict:
    """Read/configure native autowiring. Default changes are temporary and restored on close; reset alone restores temporary changes. persist=true commits and reload-verifies Multisim application preferences. These are application-wide native registry settings, not .ms14 content; persisted_in_circuit=false reports this explicitly. Stop simulation before changes."""
    return host.configure_wiring(autowire_on_connection,autowire_on_move,connect_touching,move_connection_limit,reset,persist)


@server.tool()
@checked
def native_connect_touching(component_refs: list[str] | None = None) -> dict:
    """Connect touching pins, existing junctions and wire interiors through native drop/connection factories as one undoable edit. Omit component_refs for the selected sheet. Interior contacts create native branch junctions; ambiguous crossings of different nets return an error. Returns fresh state and changed wire IDs."""
    result=host.batch([{'operation':'connectTouching','arguments':{} if component_refs is None else {'refs':component_refs}}],include_state=True)
    return {**result['results'][0],'state':result['state'],'undo_depth':result['undo_depth']}


@server.tool()
@checked
def native_move_component(component_ref: str, dx: int, dy: int) -> dict:
    """Move a native component by relative sheet units; preserve its native pin attachments. Use a current component ID when power symbols share a reference. Grid snapping applies."""
    return host.edit('move', {'ref': component_ref, 'dx': dx, 'dy': dy})


@server.tool()
@checked
def native_save_copy(output_path: str, overwrite: bool = False, allow_off_page: bool = False, verify: bool = True) -> dict:
    """Save to a specified .ms14 output while stopped. The current source path routes to normal source save without a separate overwrite flag. A different output acts as Save As in direct mode and becomes the current document; explicit copy mode preserves the original. Backups are internal. Native reopen verification is the default; Off-page content is saved; allow_off_page is retained for compatibility. Other existing output files require overwrite=true."""
    return host.save_copy(output_path,overwrite,allow_off_page,verify)


@server.tool()
@checked
def native_save_source(allow_off_page: bool = False) -> dict:
    """Normal save for new workspace circuits and existing source documents. Save ALL current native edits to the actual source .ms14, with internal backup, conflict checks and native reopen verification. Stop simulation first. In explicit copy mode this intentionally updates the original source. Off-page content is saved; allow_off_page is retained for compatibility."""
    return host.save_source(allow_off_page)


@server.tool()
@checked
def native_simulation_settings(scope: Literal['interactive','analysis'] = 'interactive', analysis_type: str = 'TRAN',
    changes: list[SimulationSettingChange] | None = None, solver_options: dict[str,Scalar] | None = None,
    save_to_source: bool = False, expected_revision: str | None = None) -> dict:
    """Read/edit native document simulation settings, including all available analysis families and solver options. Read first to discover actual fields, types, paths, option enabled states and revision. changes=[{path:[\"ANALYSIS\",\"TSTOP\"],value:2}] edits an existing scalar; integers in paths select duplicate native fields by index. TSTEP/TMAX accept null for automatic calculation; IC accepts auto_ic/uic/zero_ic. solver_options={reltol:0.0001,abstol:1e-12,method:\"gear\",itl4:150,temp:35} enables native custom options; null/false disables an option. The API sets native custom/default selector flags so values actually apply. Preserves other fields; invalid paths/types/ranges or stale revisions roll back. Changes are document-owned and survive native_save_copy/native_save_source; add save_to_source=true for verified backed-up original-file replacement. saved_to_file=false means this call did not save to disk. Ordinary Multisim uses settings after reopening. Numeric tools use_saved_settings=true execute saved OP/AC/TRAN with native-compiled solver options."""
    return host.simulation_settings(scope,analysis_type,changes,solver_options,save_to_source,expected_revision)


@server.tool()
@checked
def native_configure_sheet_display(show_grid: bool | None = None, show_border: bool | None = None,
    show_bounds: bool | None = None, save_to_source: bool = False) -> dict:
    """Read/edit persistent native display preferences for the SELECTED sheet: grid, border and bounds. Native readback is verified; save via native_save_copy/native_save_source, or add save_to_source=true for backed-up verified source replacement. Change while stopped. Export rendering flags remain temporary. Title-block presence is derived by Multisim from title-block objects on load; its temporary rendering flag is not represented as a persistent display boolean."""
    return host.configure_sheet_display(save_to_source,show_grid=show_grid,show_border=show_border,
                                        show_bounds=show_bounds)


@server.tool()
@checked
def native_close_copy(save_changes: bool = True) -> dict:
    """Finish the circuit session: save pending edits by default, then close the owned host or detach from the user's existing window. A save failure keeps the session open. Explicit comparison mode saves its working copy. save_changes=false skips saving; a detached user window retains its unsaved edits. Recovery files stay internal."""
    return host.finish(save_changes)


@server.tool()
@checked
def native_attach(pid: int, project_index: int = 0) -> dict:
    """Attach to a specified existing Multisim PID; back up its unsaved native project before editing. Close only detaches; never terminates the user's process."""
    return host.attach(pid, project_index)


@server.tool()
@checked
def native_create_circuit(output_path: str,title: str = 'Circuit') -> dict:
    """Create a real .ms14 file at the supplied absolute output_path. Its parent directory must exist and the filename must be unused. Edit existing files with native_open_circuit. Normal saves update this file; backups and checkpoints stay internal."""
    return {**host.create(title,output_path),'state':host.call('circuitState')}


@server.tool()
@checked
def native_search_library(query: str, limit: int | None = 20, family: str = '', group: str = '') -> dict:
    """Search native component names and IDs with actual family/group categories. Optional family/group filters use exact names; library names alone do not identify symbol or model type."""
    if limit is not None and limit<1: raise ValueError('Invalid search size')
    return host.call('librarySearch', {'query':query,'limit':limit,'family':family,'group':group})


@server.tool()
@checked
def native_place_component(name: str, x: int, y: int, reference: str | None = None, family: str = '', group: str = '', manufacturer: str = '',parameters: list[dict] | None = None,anchor: Literal['origin','center','pin'] = 'origin',pin: str | None = None) -> dict:
    """Place a real library component. anchor=origin preserves the library graphic origin (not symbol center); center anchors the symbol body, pin anchors the exact named pin. Placement returns requested/actual anchor coordinates and body bounds; grid snapping applies. Read returned pins before routing."""
    args={'name':name,'x':x,'y':y,'family':family,'group':group,'manufacturer':manufacturer,'anchor':anchor}
    if pin is not None:args['pin']=pin
    if parameters is not None:args['parameters']=parameters
    if reference is not None: args['ref']=reference
    return host.edit('place',args)


@server.tool()
@checked
def native_copy_component(component_ref: str, new_ref: str, x: int, y: int) -> dict:
    """Copy a library-backed component into a new independent native instance with copied numeric parameters and unique reference."""
    return host.edit('copy',{'ref':component_ref,'new_ref':new_ref,'x':x,'y':y})


@server.tool()
@checked
def native_delete_object(object_id: str | None = None, component_ref: str | None = None) -> dict:
    """Delete a native component, wire, text or junction by current object ID, or a component by its reference. Attached wires are removed by Multisim."""
    if (object_id is None)==(component_ref is None): raise ValueError('Provide exactly one object_id or component_ref')
    return host.edit('remove',{'id':object_id} if object_id else {'ref':component_ref})


@server.tool()
@checked
def native_get_parameters(component_ref: str) -> dict:
    """Read native indexed numeric and expression parameters plus library metadata. Read these before choosing a parameter index."""
    return host.call('parameters',{'ref':component_ref})


@server.tool()
@checked
def native_set_parameter(component_ref: str, index: int, value: float | None = None, expression: str | None = None) -> dict:
    """Set one existing native parameter by index, using either a finite numeric value or a SPICE expression."""
    if (value is None)==(expression is None): raise ValueError('Provide exactly one value or expression')
    return host.edit('setParameter',{'ref':component_ref,'index':index,**({'value':value} if value is not None else {'expression':expression})})


@server.tool()
@checked
def native_replace_component(component_ref: str, name: str, pin_map: dict[str,str] | None = None, family: str = '', group: str = '') -> dict:
    """Replace a component using another real library model; preserve its reference and reconnect matching named pins. Map old pin names to new names when needed."""
    return host.edit('replace',{'ref':component_ref,'name':name,'family':family,'group':group,'pin_map':pin_map or {}})


@server.tool()
@checked
def native_get_model(component_ref: str) -> dict:
    """Read the component's actual embedded native SPICE model and model attribute IDs."""
    return host.call('modelInfo',{'ref':component_ref})


@server.tool()
@checked
def native_set_model_text(component_ref: str, text: str) -> dict:
    """Edit the native embedded SPICE text model. This edits a shared model definition and returns affected component references across all project sheets."""
    if not re.search(r'(?im)^\s*\.(model|subckt)\b',text): raise ValueError('Provide a SPICE .model or .subckt definition')
    return host.edit('setModelText',{'ref':component_ref,'text':text})


@server.tool()
@checked
def native_transform_component(component_ref: str, angle: float | None = None, mirror_axis: str | None = None) -> dict:
    """Rotate a component by the supplied finite angle in degrees or mirror horizontally/vertically; keep wires attached to the same native pins."""
    if (angle is None)==(mirror_axis is None): raise ValueError('Provide angle or mirror_axis')
    return host.edit('transform',{'ref':component_ref,**({'angle':angle} if angle is not None else {'axis':mirror_axis})})


@server.tool()
@checked
def native_rename_component(component_ref: str, new_ref: str) -> dict:
    """Rename the native instance reference through Multisim's hierarchical reference manager."""
    return host.edit('rename',{'ref':component_ref,'new_ref':new_ref})


@server.tool()
@checked
def native_route_wire(wire_id: str, points: list[dict[str,int]]) -> dict:
    """Replace the vertices of a real electrical wire. First and last points must equal its actual connector coordinates."""
    return host.edit('route',{'id':wire_id,'points':points})


@server.tool()
@checked
def native_repair_wire_geometry() -> dict:
    """Synchronize symbol and junction graphics with grid-snapped electrical connectors, then align existing wire endpoints. Repairs the selected sheet as one undoable transaction and preserves every electrical attachment. Returns changed objects, verification and fresh state."""
    result=host.batch([{'operation':'repairWireGeometry','arguments':{}}],include_state=True)
    return {**result['results'][0],'state':result['state'],'undo_depth':result['undo_depth']}


@server.tool()
@checked
def native_split_wire(wire_id: str, x: int, y: int) -> dict:
    """Split a wire at a point on its existing route and create a real electrical junction for a branch."""
    return host.edit('splitWire',{'id':wire_id,'x':x,'y':y})


@server.tool()
@checked
def native_connect_endpoints(source: dict, target: dict, points: list[dict[str,int]] | None = None) -> dict:
    """Connect {ref,pin} or {junction_id} endpoints. Optional route must end at actual connector coordinates."""
    return host.edit('connectEndpoint',{'source':source,'target':target,**({'points':points} if points else {})})


@server.tool()
@checked
def native_reconnect_wire(wire_id: str, source: dict | None = None, target: dict | None = None) -> dict:
    """Replace one or both wire endpoints with {ref,pin} or {junction_id}; validate and reconnect through the electrical wire factory."""
    return host.edit('reconnect',{'id':wire_id,**({'source':source} if source else {}),**({'target':target} if target else {})})


@server.tool()
@checked
def native_add_text(text: str, x: int, y: int) -> dict:
    """Insert editable native schematic text at sheet coordinates."""
    return host.edit('addText',{'text':text,'x':x,'y':y})


@server.tool()
@checked
def native_label_wire(wire_id: str, name: str) -> dict:
    """Set the actual electrical net name and native wire label."""
    return host.edit('labelWire',{'id':wire_id,'name':name})


@server.tool()
@checked
def native_list_sheets() -> dict:
    """List sheet dimensions and top-left bounds in sheet units (96 per inch), titles, pages and selection. Printing-paper dimensions are returned separately."""
    return {'sheets':host.call('sheets')}


@server.tool()
@checked
def native_select_sheet(index: int) -> dict:
    """Select an existing native schematic sheet by its list index."""
    return host.call('selectSheet',{'index':index})


@server.tool()
@checked
def native_create_sheet(title: str, page: str = '') -> dict:
    """Create and initialize an independent native schematic sheet in the current project."""
    return {'sheets':host.edit('createSheet',{'title':title,'page':page})}


@server.tool()
@checked
def native_create_subcircuit(title: str, reference: str, x: int, y: int) -> dict:
    """Create a native embedded child schematic and its editable parent macro symbol. Add ports on the child sheet before connecting the parent pins."""
    return host.edit('createSubcircuit',{'title':title,'ref':reference,'x':x,'y':y})


@server.tool()
@checked
def native_create_hierarchical_port(name: str, x: int, y: int) -> dict:
    """Add a real hierarchical electrical connector on the selected child sheet; update its parent subcircuit symbol pins. Read the exact returned connector pin name before wiring."""
    return host.edit('createPort',{'name':name,'x':x,'y':y})


@server.tool()
@checked
def native_list_projects() -> dict:
    """List open native projects, including their indexes for native_attach."""
    return host.call('projects')


@server.tool()
@checked
def native_edit_batch(operations: list[dict], include_state: bool = True, atomic: bool = True) -> dict:
    """Apply a nonempty batch of edits. Each item has operation and arguments. Default atomic=true rolls back this entire batch on failure, preserving earlier calls. Set atomic=false to keep completed operations and roll back only the failed operation. Failures return an error with rollback_scope, handles_invalidated and fresh state. Operations include wire, move, moveLabel, place, copy, remove, transform, route, autoWire (id), connectTouching (optional refs), setParameter, rename, addText, labelWire, splitWire, connectEndpoint, reconnect, replace, createSheet and sheetSize (positive native width/height)."""
    return host.batch(operations,include_state,atomic)


@server.tool()
@checked
def native_undo() -> dict:
    """Restore the previous native checkpoint. Object IDs change; reread components and wires."""
    return host.history('undo')


@server.tool()
@checked
def native_redo() -> dict:
    """Reapply an undone checkpoint using native save/reopen; reread object IDs afterward."""
    return host.history('redo')


@server.tool()
@checked
def native_check_netlist() -> dict:
    """Generate the SPICE source used by native analysis. Refresh changed topology only; handles_invalidated then includes the refreshed state. Layout and parameter edits keep handles stable. A resistor value of zero in this source is an actual zero resistance."""
    return host.netlist()


@server.tool()
@checked
def native_run_analysis(analysis: str = 'op', step: float = 0.00001, stop: float = 0.01, use_initial_conditions: bool = False,
    persist: bool = False, save_to_source: bool = False, use_saved_settings: bool = False) -> dict:
    """Run real OP/transient analysis and export RAW/CSV. Default arguments apply to this run. persist=true also writes those arguments into native analysis configuration; add save_to_source=true to back up and verify-save the original. Alternatively use_saved_settings=true executes the stored analysis and solver options using native-generated commands. Saved transient and AC execution are supported. Persist and use_saved_settings are exclusive. Results are external artifacts, separate from saved circuit configuration."""
    return host.run_analysis(analysis,step,stop,use_initial_conditions,persist=persist,save_to_source=save_to_source,use_saved_settings=use_saved_settings)


@server.tool()
@checked
def native_run_ac_sweep(sweep: str = 'dec', points: int = 20, start_hz: float = 1., stop_hz: float = 100000.,
    persist: bool = False, save_to_source: bool = False, use_saved_settings: bool = False) -> dict:
    """Run native AC analysis: lin uses total points, dec/oct use points per decade/octave. persist=true retains sweep settings in the document; save_to_source=true additionally back up/verify-saves the original. use_saved_settings=true instead executes saved native AC settings and solver options. Return complex RAW and real/imaginary CSV artifacts."""
    return host.run_analysis('ac',ac_sweep=sweep,ac_points=points,ac_start=start_hz,ac_stop=stop_hz,
                            persist=persist,save_to_source=save_to_source,use_saved_settings=use_saved_settings)


@server.tool()
@checked
def native_start_analysis(analysis: str = 'tran', step: float = 0.00001, stop: float = 0.01, use_initial_conditions: bool = False,
    persist: bool = False, save_to_source: bool = False, use_saved_settings: bool = False) -> dict:
    """Start background native analysis with pause/resume/stop/status. persist=true retains explicit run arguments in native document settings; save_to_source=true additionally backs up and verify-saves the source before running. use_saved_settings=true executes stored analysis and native-compiled solver options instead. Results remain external artifacts."""
    return host.start_analysis(analysis,step,stop,use_initial_conditions,persist=persist,save_to_source=save_to_source,use_saved_settings=use_saved_settings)


@server.tool()
@checked
def native_analysis_status() -> dict:
    """Read the current analysis job state, completed numeric results or native failure, without waiting for the UI thread."""
    return host.analysis_status()


@server.tool()
@checked
def native_interactive_status(include_displays: bool = False) -> dict:
    """Read actual native interactive simulation state, errors and simulated time from the native status bar. Separate from numeric analysis jobs."""
    return host.interactive_status(include_displays)


@server.tool()
@checked
def native_configure_interactive(time_step: float | None = None, max_time_step: float | None = None,
    real_time: bool | None = None, reset: bool = False, persist: bool = True,
    save_to_source: bool = False) -> dict:
    """Read/configure native interactive simulation. Steps are finite positive seconds; real_time enables native pacing. By default persist=true reads/writes native document settings; use persist=false only for an intentional session override. These document settings survive normal save/close and ordinary GUI starts after reopening; saved_to_file=false means a save is still needed. Add save_to_source=true to save immediately with an internal backup and independent native reopen verification; external source changes block replacement. This preserves numeric-analysis and other solver options, and clears temporary overrides. Change options while stopped. reset=true restores automatic steps and real-time pacing for the chosen scope. For low-frequency LEDs, 0.001 s steps may improve speed; verify the fastest relevant signals."""
    return host.configure_interactive(time_step,max_time_step,real_time,reset,persist=persist,save_to_source=save_to_source)


@server.tool()
@checked
def native_control_interactive(action: Literal['start','pause','resume','stop'], wait_timeout: float = 5.0) -> dict:
    """Start, pause, resume or stop the GUI interactive simulator through native application commands, without mouse input. Poll actual state and return transition_confirmed; queued requests alone do not establish completion. Resume continues paused time; start begins a stopped run."""
    return host.control_interactive(action,wait_timeout)


@server.tool()
@checked
def native_export_interactive_image(output_path: str, overwrite: bool = False, dpi: int = 144,
    scale: float = 1.0, region: dict[str,int] | None = None, fit_content: bool = False,
    padding: int = 18, show_frame: bool = False, show_grid: bool = False,
    active_component: str | None = None, wait_timeout: float | None = None) -> dict:
    """Capture the actual instantaneous native interactive display state as PNG/BMP. Optionally wait for active_component (SEVEN_SEG_COM_A) to show a stable decoded digit, useful for multiplexed scans. Capture and readout occur in one UI-thread operation; no segment states are synthesized or accumulated. Returns native segment states and simulation time. Pause preserves the current phase; resume to capture another phase."""
    return host.export_interactive_image(output_path,overwrite,dpi,scale,region,fit_content,padding,show_frame,show_grid,active_component,wait_timeout)


@server.tool()
@checked
def native_control_analysis(action: str) -> dict:
    """Request pause, resume or stop through the native simulator transport. A request acknowledgment is not a confirmed paused state; inspect job status and result artifacts."""
    return host.control_analysis(action)


@server.tool()
@checked
def native_read_waveform(raw_path: str, offset: int = 0, limit: int = 1000, plot_index: int = 0) -> dict:
    """Read native ASCII RAW samples and plot metadata. Select plot_index for appended digital-node plots; their event rows contain time, rising and falling flags."""
    return host.read_waveform(raw_path,offset,limit,plot_index)


@server.tool()
@checked
def native_measure_waveform(raw_path: str, measurements: list[MeasurementRequest]) -> dict:
    """Measure native RAW samples. Each request has id, metric, signal; optional start/stop, threshold. Metrics: min, max, mean, rms, peak_to_peak, frequency, duty_cycle; AC gain_db/phase_deg need reference and frequency_hz."""
    from .waveforms import parse_raw
    from .measurements import measure
    measurements=normalize_measurements(measurements)
    return {'raw_path':raw_path,'measurements':measure(parse_raw(Path(raw_path)),measurements)}


@server.tool()
@checked
def native_verify_waveform(raw_path: str, measurements: list[MeasurementRequest], criteria: list[AcceptanceCriterion]) -> dict:
    """Measure RAW data and check criteria using the same id field as measurements. The legacy criterion key measurement is accepted. Specify min/max or target plus absolute_tolerance/relative_tolerance; malformed requests fail before reading the waveform."""
    from .waveforms import parse_raw
    from .measurements import measure
    from .verification import verify
    measurements=normalize_measurements(measurements)
    criteria=normalize_criteria(criteria,{m['id'] for m in measurements})
    values=measure(parse_raw(Path(raw_path)),measurements)
    return {'raw_path':raw_path,'measurements':values,**verify(values,criteria)}


@server.tool()
@checked
def native_decode_seven_segment(raw_path: str, digits: list[dict], expected: str | None = None,
        start: float | None = None, stop: float | None = None, threshold: float = 2.5,
        active_high: bool = True, select_threshold: float = 2.5, select_active_high: bool = True,
        settling: float = 0.00002, min_dwell: float = 0.00001) -> dict:
    """Decode scanned displays from real samples. Each digit has label, seven segments in abcdefg order, and select signal. Thresholds may be volts or amps according to supplied vectors. Reject conflicting active digits and sustained wrong patterns."""
    from .waveforms import parse_raw
    from .verification import decode_display
    return decode_display(parse_raw(Path(raw_path)),digits,expected,start,stop,threshold,active_high,
                          select_threshold,select_active_high,settling,min_dwell)


@server.tool()
@checked
def native_run_parameter_sweep(parameters: list[dict], analysis: dict, measurements: list[MeasurementRequest],
        criteria: list[AcceptanceCriterion] | None = None, objective: dict | None = None) -> dict:
    """Run a native parameter sweep. Parameters: {ref,index,values}; analysis uses native run options. Constraints use measurement IDs. Optional objective: {measurement,goal:min|max|target,target}. Restore the original circuit after all trials; return feasible candidates and best index."""
    measurements=normalize_measurements(measurements)
    criteria=normalize_criteria(criteria or [],{m['id'] for m in measurements},allow_empty=True)
    return experiments.start(parameters,analysis,measurements,criteria,objective,background=False)


@server.tool()
@checked
def native_start_experiment(parameters: list[dict], analysis: dict, measurements: list[MeasurementRequest],
        criteria: list[AcceptanceCriterion] | None = None, objective: dict | None = None) -> dict:
    """Start a persisted background parameter experiment. Circuit edits are locked until completion or cancellation. Query with its ID."""
    measurements=normalize_measurements(measurements)
    criteria=normalize_criteria(criteria or [],{m['id'] for m in measurements},allow_empty=True)
    return experiments.start(parameters,analysis,measurements,criteria,objective)


@server.tool()
@checked
def native_experiment_status(experiment_id: str) -> dict:
    """Read saved experiment inputs, trials, measurements and final state, including after service restart."""
    return experiments.store.read(experiment_id)


@server.tool()
@checked
def native_list_experiments(limit: int = 20) -> dict:
    """List recent persistent experiments."""
    return {'experiments':experiments.store.list(limit)}


@server.tool()
@checked
def native_cancel_experiment(experiment_id: str) -> dict:
    """Request cancellation, interrupt an active native analysis and restore original parameters before the job finishes."""
    return experiments.cancel(experiment_id)


@server.tool()
@checked
def native_retry_experiment(experiment_id: str) -> dict:
    """Retry saved inputs in a new copy of the saved source circuit. Close the current native session first. Return a new experiment ID linked to the original."""
    return experiments.retry(experiment_id)


@server.tool()
@checked
def native_export_experiment_report(experiment_id: str, output_directory: str, language: str = 'zh',
        title: str | None = None, signals: list[str] | None = None, overwrite: bool = False) -> dict:
    """Export a saved experiment as standalone HTML, Markdown, measurement CSV, native circuit PNG and waveform SVG. Choose zh or en and the requested plotted signals."""
    from .reports import export_report
    return export_report(experiments.store.read(experiment_id),output_directory,language,title,signals,overwrite)


@server.tool()
@checked
def native_check_layout() -> dict:
    """Check native connector attachment, invisible wires, orthogonal segments, graphic bounding-box overlap and wires crossing other component bounds."""
    from .layout import check_layout
    with host.lock:return check_layout(host.call('componentBounds')['components'],host.call('wires')['wires'])


@server.tool()
@checked
def native_plan_wire_route(wire_id: str, clearance: int = 9) -> dict:
    """Plan an orthogonal wire path around native component bounds. Return points without editing; preserve actual electrical connector endpoints."""
    from .layout import plan_wire
    with host.lock:
        wire=next((w for w in host.call('wires')['wires'] if w['id']==wire_id),None)
        if not wire:raise ValueError('Wire not found')
        return plan_wire(host.call('componentBounds')['components'],wire,clearance)


@server.tool()
@checked
def native_auto_route_wire(wire_id: str, clearance: int = 9, engine: Literal['native','obstacle'] = 'native') -> dict:
    """Reroute an existing wire using Multisim's native router by default, preserving its ID and electrical endpoints. engine=obstacle uses the MCP orthogonal planner with clearance in sheet units. One undoable edit. Batch equivalent: autoWire with arguments.id for native routing."""
    if engine not in ('native','obstacle'):raise ValueError('Choose routing engine native or obstacle')
    if engine=='native':return host.edit('autoWire',{'id':wire_id})
    with host.lock:
        plan=native_plan_wire_route(wire_id,clearance)
        result=host.edit('route',{'id':wire_id,'points':plan['points']})
        return {**plan,'wire':result,'routing_engine':'obstacle'}


@server.tool()
@checked
def native_export_image(output_path: str, overwrite: bool = False,dpi: int = 96,scale: float = 1.,region: dict[str,int] | None = None,fit_content: bool = False,padding: int = 18,show_frame: bool = False,show_grid: bool = False) -> dict:
    """Render PNG/BMP natively at the requested positive DPI. Default is a clean circuit image; show_frame enables sheet border/title block, show_grid enables the dot grid. Rendering restores display preferences. Choose region or fit_content for cropping; cropping does not resize the saved sheet."""
    return host.export_image(output_path,overwrite,dpi,scale,region,fit_content,padding,show_frame,show_grid)


def main():
    try:
        server.run(transport='stdio')
    finally:
        workflows.shutdown()
        experiments.shutdown()
        host.close()
