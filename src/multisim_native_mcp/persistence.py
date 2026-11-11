"""Explicit persistence ownership for every public MCP capability."""
GROUPS = [
    ('circuit_edits','circuit','Save with native_save_source or native_save_copy; native reopen verifies the document.', '''
native_move_component_label native_connect_pins native_connect_touching native_move_component
native_place_component native_copy_component native_delete_object native_set_parameter native_replace_component
native_set_model_text native_transform_component native_rename_component native_route_wire native_repair_wire_geometry
native_split_wire native_connect_endpoints native_reconnect_wire native_add_text native_label_wire
native_create_sheet native_create_subcircuit native_create_hierarchical_port native_edit_batch native_auto_route_wire'''),
    ('document_settings','circuit','Native document properties; save explicitly. Interactive settings are document-owned by default; persist=false explicitly selects temporary overrides.', '''
native_simulation_settings native_configure_sheet_display native_configure_interactive'''),
    ('save','circuit_file','Native save with backup and reopen verification; source save always verifies and detects conflicts.', '''
native_save_source native_save_copy'''),
    ('application_preferences','application','persist=true commits native application preferences and verifies reload; these are not .ms14 fields.', '''
native_configure_wiring'''),
    ('analysis','circuit_configuration_and_external_results','persist=true retains native analysis settings; save_to_source=true saves them. use_saved_settings=true runs stored settings. RAW/CSV results are separate files.', '''
native_run_analysis native_run_ac_sweep native_start_analysis'''),
    ('history','circuit_result_and_session_history','The restored drawing can be saved; process-local undo/redo stacks are not portable circuit content.', '''
native_undo native_redo'''),
    ('workflows','native_documents_and_external_records','Simulation-settings, sheet-display and persistent analysis stages modify native documents; save stages support save_to_source=true. Plans and execution logs are external durable records.', '''
native_run_workflow native_workflow_status native_control_workflow'''),
    ('experiments','external_records','Trial specifications, constraints, objectives, results and reports are external durable experiment records. Trials restore original values; explicitly apply selected parameter values and save to retain a candidate in the circuit.', '''
native_run_parameter_sweep native_start_experiment native_experiment_status native_list_experiments
native_cancel_experiment native_retry_experiment native_export_experiment_report'''),
    ('exports','external_files','PNG/BMP captures and rendering options are external exports. Use native_configure_sheet_display to retain native sheet preferences. Runtime LED states are not saved design values.', '''
native_export_image native_export_interactive_image'''),
    ('runtime_control','session','Start/pause/resume/stop, simulation time and runtime display states are live process state, not circuit configuration.', '''
native_analysis_status native_interactive_status native_control_interactive native_control_analysis'''),
    ('session_context','session','Opening, attaching, sheet selection and metadata preparation control the current session. Ordinary open/create use the actual workspace/source file; normal close saves pending edits. Explicit comparisons alone use workspace copies.', '''
native_prepare_components native_open_circuit native_open_copy native_close_copy native_attach native_create_circuit native_select_sheet'''),
    ('inspection','read_only','Reads circuit, waveform or persistence information; creates no document setting that needs saving.', '''
native_session_changes native_runtime_status native_diagnostics native_list_components native_get_circuit_state
native_list_wires native_search_library native_get_parameters native_get_model native_list_sheets native_list_projects
native_check_netlist native_read_waveform native_measure_waveform native_verify_waveform native_decode_seven_segment
native_check_layout native_plan_wire_route native_persistence_capabilities'''),
]


def persistence_capabilities():
    from . import __version__
    tools=[{'tool':name,'category':category,'scope':scope,'persistence':note}
           for category,scope,note,names in GROUPS for name in names.split()]
    assert len({t['tool'] for t in tools})==len(tools)
    return {'server_version':__version__,'tool_count':len(tools),'tools':sorted(tools,key=lambda t:t['tool']),
            'source_save':'native_save_source',
            'simulation_configuration':'native_simulation_settings',
            'file_verification':['all sheets','components and parameters','embedded SPICE text models','wire connectivity and geometry',
                                 'labels and annotations','sheet titles and display preferences','complete native simulation properties'],
            'not_circuit_content':['application-wide preferences','running solver state and animation phase','MCP undo stacks and session caches',
                                   'RAW/CSV/PNG/BMP files','MCP workflow and experiment records',
                                   'export-only title-block rendering flag (native load derives visibility from title-block objects)']}
