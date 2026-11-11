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

host = EditorService()
experiments = ExperimentManager(host)


def checked(function):
    @wraps(function)
    def execute(*args, **kwargs):
        try:
            if experiments.active and function.__name__ not in {
                'native_runtime_status','native_experiment_status','native_list_experiments','native_cancel_experiment',
                'native_read_waveform','native_measure_waveform','native_verify_waveform','native_decode_seven_segment'}:
                raise RuntimeError('A native experiment is running; inspect or cancel it first')
            return function(*args, **kwargs)
        except NativeEditError as error:
            return CallToolResult(isError=True,structuredContent=error.details,
                content=[TextContent(type='text',text=json.dumps(error.details,ensure_ascii=False))])
        except Exception as error:
            raise ToolError(str(error)) from error
    return execute
server = MCPServer('multisim-native', version=__version__,
                   instructions='Edit native Multisim objects in isolated copies or explicitly attached existing windows. '
                   'Read exact pin names before wiring; save results before closing. '
                   'Undo, redo and netlist refresh can invalidate memory IDs; reread objects afterward. '
                   'Read sheet bounds from the initial state or native_get_circuit_state before placing components. '
                   'Coordinates use top-left sheet units, 96 per inch, and may snap to grid. '
                   'Use native_edit_batch for construction and consume its returned state. '
                   'Waveform values use SI units; verify source current as well as output voltage. '
                   'Native Multisim schematic editing and analog analysis.')


@server.tool()
@checked
def native_runtime_status() -> dict:
    """Read runtime availability and reference-profile hash diagnostics without starting Multisim."""
    return host.runtime_status()


@server.tool()
@checked
def native_diagnostics() -> dict:
    """Read captured native netlist errors, including background Netlist Viewer updates, without a modal dialog."""
    if not host.agent: return {'netlist_errors':[]}
    return host.agent.exports_sync.diagnostics()


@server.tool()
@checked
def native_open_copy(source_path: str) -> dict:
    """Start an isolated hidden Multisim process on a copy of an existing absolute .ms14 path."""
    return {**host.open_copy(source_path),'state':host.call('circuitState',{'include_parameters':True})}


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
    """Read actual native wire endpoints and routed vertices, optionally filtering by component reference."""
    result = host.call('wires')
    if component_ref is not None:
        result['wires'] = [wire for wire in result['wires'] if any(wire[end].get('ref') == component_ref for end in ('source', 'target'))]
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
                            reset: bool = False) -> dict:
    """Read or configure native Multisim autowiring for connections, moves and touching pins. A move reroutes only below move_connection_limit; other moves preserve attachments and route shape. Changes last for this session and restore on close. Use reset alone to restore original settings. Stop simulation before changes."""
    options={key:value for key,value in locals().items() if value is not None and key!='reset'}
    if reset:
        if options: raise ValueError('Use reset alone to restore wiring options')
        options={'reset':True}
    if move_connection_limit is not None and (isinstance(move_connection_limit,bool) or not 1<=move_connection_limit<=10000):
        raise ValueError('move_connection_limit must be an integer from 1 to 10000')
    with host.lock:
        if options and host.call('simulationInfo')['state'] in (1,2):raise RuntimeError('Stop interactive simulation before changing wiring options')
        return host.call('wiringOptions',options)


@server.tool()
@checked
def native_connect_touching(component_refs: list[str] | None = None) -> dict:
    """Connect touching pins, existing junctions and wire interiors through native drop/connection factories as one undoable edit. Omit component_refs for the selected sheet. Interior contacts create native branch junctions; ambiguous crossings of different nets return an error. Returns fresh state and changed wire IDs."""
    result=host.batch([{'operation':'connectTouching','arguments':{} if component_refs is None else {'refs':component_refs}}],include_state=True)
    return {**result['results'][0],'state':result['state'],'undo_depth':result['undo_depth']}


@server.tool()
@checked
def native_move_component(component_ref: str, dx: int, dy: int) -> dict:
    """Move a native component by relative sheet units; preserve its native pin attachments. Grid snapping applies."""
    if max(abs(dx), abs(dy)) > 10000:
        raise ValueError('Movement must be within 10000 native units per axis')
    return host.edit('move', {'ref': component_ref, 'dx': dx, 'dy': dy})


@server.tool()
@checked
def native_save_copy(output_path: str, overwrite: bool = False, allow_off_page: bool = False, verify: bool = True) -> dict:
    """Save a separate absolute .ms14 file while stopped. Check all sheets for off-page content and verify the saved copy through native reopen without replacing the active document or invalidating its handles. Resize or move off-page content before saving; allow_off_page=true preserves an intentional off-page layout. verify=false skips readback. Existing output requires overwrite=true and is backed up."""
    return host.save_copy(output_path,overwrite,allow_off_page,verify)


@server.tool()
@checked
def native_close_copy() -> dict:
    """Close an owned hidden host, or detach from an existing user's window without closing it. Save output first; checkpoints remain on disk."""
    return host.close()


@server.tool()
@checked
def native_attach(pid: int, project_index: int = 0) -> dict:
    """Attach to a specified existing Multisim PID; back up its unsaved native project before editing. Close only detaches; never terminates the user's process."""
    return host.attach(pid, project_index)


@server.tool()
@checked
def native_create_circuit(title: str = 'Circuit') -> dict:
    """Start a blank native 14.3 schematic in an owned host. Other Multisim windows must be closed."""
    return {**host.create(title),'state':host.call('circuitState')}


@server.tool()
@checked
def native_search_library(query: str, limit: int = 20, family: str = '', group: str = '') -> dict:
    """Search native component names and IDs with actual family/group categories. Optional family/group filters use exact names; library names alone do not identify symbol or model type."""
    if not 1 <= limit <= 100 or len(query)>128: raise ValueError('Invalid search size')
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
def native_transform_component(component_ref: str, angle: int | None = None, mirror_axis: str | None = None) -> dict:
    """Rotate a component by multiples of 90 degrees or mirror horizontally/vertically; keep wires attached to the same native pins."""
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
    """Apply 1-100 edits. Each item has operation and arguments. Default atomic=true rolls back this entire batch on failure, preserving earlier calls. Set atomic=false to keep completed operations and roll back only the failed operation. Failures return an error with rollback_scope, handles_invalidated and fresh state. Operations include wire, move, moveLabel, place, copy, remove, transform, route, autoWire (id), connectTouching (optional refs), setParameter, rename, addText, labelWire, splitWire, connectEndpoint, reconnect, replace, createSheet and sheetSize (width/height 96-8192 sheet units)."""
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
def native_run_analysis(analysis: str = 'op', step: float = 0.00001, stop: float = 0.01, use_initial_conditions: bool = False) -> dict:
    """Run real Multisim DC operating-point (op) or transient (tran) analysis. Return verified numeric waveforms plus ASCII RAW, CSV and native SPICE source paths. At most 100000 requested transient steps."""
    return host.run_analysis(analysis,step,stop,use_initial_conditions)


@server.tool()
@checked
def native_run_ac_sweep(sweep: str = 'dec', points: int = 20, start_hz: float = 1., stop_hz: float = 100000.) -> dict:
    """Run native AC analysis: lin uses total points, dec/oct use points per decade/octave. Return complex RAW and real/imaginary CSV vectors."""
    return host.run_analysis('ac',ac_sweep=sweep,ac_points=points,ac_start=start_hz,ac_stop=stop_hz)


@server.tool()
@checked
def native_start_analysis(analysis: str = 'tran', step: float = 0.00001, stop: float = 0.01, use_initial_conditions: bool = False) -> dict:
    """Start a native analysis in the background so pause/resume/stop and status tools remain available."""
    return host.start_analysis(analysis,step,stop,use_initial_conditions)


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
    real_time: bool | None = None, reset: bool = False) -> dict:
    """Read or configure the next MCP-started native GUI interactive runs. Time steps are seconds (1e-12 to 1); real_time enables native real-time pacing. For low-frequency LED circuits, time_step=0.001, max_time_step=0.001, real_time=true reduces unnecessary solver steps. Choose steps suitable for the circuit's fastest signals and verify its waveforms. Change options while stopped. Settings belong to this attached session, do not change the saved circuit or numeric analysis, and reset=true restores application defaults. Status reports the actual applied native startup parameters."""
    return host.configure_interactive(time_step,max_time_step,real_time,reset)


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
    active_component: str | None = None, wait_timeout: float = 5.0) -> dict:
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
    """Run up to 100 native trials. Parameters: {ref,index,values}; analysis uses native run options. Constraints use measurement IDs. Optional objective: {measurement,goal:min|max|target,target}. Restore the original circuit after all trials; return feasible candidates and best index."""
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
    """Export a saved experiment as standalone HTML, Markdown, measurement CSV, native circuit PNG and waveform SVG. Choose zh or en and up to eight plotted signals."""
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
    """Render PNG/BMP natively at 36-600 DPI. Default is a clean circuit image; show_frame enables sheet border/title block, show_grid enables the dot grid. Rendering restores display preferences. Choose region or fit_content for cropping; cropping does not resize the saved sheet. At most 32 million pixels."""
    return host.export_image(output_path,overwrite,dpi,scale,region,fit_content,padding,show_frame,show_grid)


def main():
    try:
        server.run(transport='stdio')
    finally:
        experiments.shutdown()
        host.close()
