# Tool reference / 工具参考

| Tool | Parameters |
| --- | --- |
| `native_runtime_status` | — |
| `native_diagnostics` | — |
| `native_open_copy` | source_path |
| `native_list_components` | — |
| `native_get_circuit_state` | include_parameters |
| `native_move_component_label` | component_ref, x, y, kind |
| `native_list_wires` | component_ref |
| `native_connect_pins` | source_ref, source_pin, target_ref, target_pin |
| `native_move_component` | component_ref, dx, dy |
| `native_save_copy` | output_path, overwrite |
| `native_close_copy` | — |
| `native_attach` | pid, project_index |
| `native_create_circuit` | title |
| `native_search_library` | query, limit, family, group |
| `native_place_component` | name, x, y, reference, family, group, manufacturer, parameters, anchor, pin |
| `native_copy_component` | component_ref, new_ref, x, y |
| `native_delete_object` | object_id, component_ref |
| `native_get_parameters` | component_ref |
| `native_set_parameter` | component_ref, index, value, expression |
| `native_replace_component` | component_ref, name, pin_map, family, group |
| `native_get_model` | component_ref |
| `native_set_model_text` | component_ref, text |
| `native_transform_component` | component_ref, angle, mirror_axis |
| `native_rename_component` | component_ref, new_ref |
| `native_route_wire` | wire_id, points |
| `native_repair_wire_geometry` | — |
| `native_split_wire` | wire_id, x, y |
| `native_connect_endpoints` | source, target, points |
| `native_reconnect_wire` | wire_id, source, target |
| `native_add_text` | text, x, y |
| `native_label_wire` | wire_id, name |
| `native_list_sheets` | — |
| `native_select_sheet` | index |
| `native_create_sheet` | title, page |
| `native_create_subcircuit` | title, reference, x, y |
| `native_create_hierarchical_port` | name, x, y |
| `native_list_projects` | — |
| `native_edit_batch` | operations, include_state, atomic |
| `native_undo` | — |
| `native_redo` | — |
| `native_check_netlist` | — |
| `native_run_analysis` | analysis, step, stop, use_initial_conditions |
| `native_start_analysis` | analysis, step, stop, use_initial_conditions |
| `native_analysis_status` | — |
| `native_control_analysis` | action |
| `native_read_waveform` | raw_path, offset, limit, plot_index |
| `native_export_image` | output_path, overwrite, dpi, scale, region, fit_content, padding, show_frame, show_grid |
| `native_run_ac_sweep` | sweep, points, start_hz, stop_hz |
| `native_measure_waveform` | raw_path, measurements |
| `native_verify_waveform` | raw_path, measurements, criteria |
| `native_decode_seven_segment` | raw_path, digits, expected, start, stop, threshold, active_high, select_threshold, select_active_high, settling, min_dwell |
| `native_run_parameter_sweep` | parameters, analysis, measurements, criteria, objective |
| `native_start_experiment` | parameters, analysis, measurements, criteria, objective |
| `native_experiment_status` | experiment_id |
| `native_list_experiments` | limit |
| `native_cancel_experiment` | experiment_id |
| `native_retry_experiment` | experiment_id |
| `native_export_experiment_report` | experiment_id, output_directory, language, title, signals, overwrite |
| `native_check_layout` | — |
| `native_plan_wire_route` | wire_id, clearance |
| `native_auto_route_wire` | wire_id, clearance |

Use the schemas returned by MCP `tools/list` for parameter types and defaults.
参数类型和默认值以 MCP `tools/list` 返回的 schema 为准。

### `native_repair_wire_geometry`

Synchronize symbol and junction graphics with grid-snapped electrical connectors, then align wire endpoints on the selected sheet. This is one undoable edit. Returns aligned components/junctions, changed wire IDs, endpoint verification and fresh state. Electrical attachments are preserved.

将当前图纸的元件、接点图形同步到电气连接坐标，再校正导线端点，支持一次撤销。返回校正的元件、接点、导线及验证结果和完整状态，保留原电气连接关系。
