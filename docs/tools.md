# Tool reference / 工具参考

| Tool | Parameters |
| --- | --- |
| `native_run_workflow` | plan, wait_timeout |
| `native_workflow_status` | workflow_id, wait_timeout, detail |
| `native_control_workflow` | workflow_id, action, replacement_steps, wait_timeout, expected_revision |
| `native_prepare_components` | components, refresh |
| `native_session_changes` | since_revision, include_parameters |
| `native_runtime_status` | — |
| `native_persistence_capabilities` | — |
| `native_diagnostics` | — |
| `native_open_copy` | source_path |
| `native_list_components` | — |
| `native_get_circuit_state` | include_parameters |
| `native_move_component_label` | component_ref, x, y, kind |
| `native_list_wires` | component_ref |
| `native_connect_pins` | source_ref, source_pin, target_ref, target_pin |
| `native_move_component` | component_ref, dx, dy |
| `native_save_copy` | output_path, overwrite, allow_off_page, verify |
| `native_save_source` | allow_off_page |
| `native_simulation_settings` | scope, analysis_type, changes, solver_options, save_to_source, expected_revision |
| `native_configure_sheet_display` | show_grid, show_border, show_bounds, save_to_source |
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
| `native_run_analysis` | analysis, step, stop, use_initial_conditions, persist, save_to_source, use_saved_settings |
| `native_start_analysis` | analysis, step, stop, use_initial_conditions, persist, save_to_source, use_saved_settings |
| `native_analysis_status` | — |
| `native_control_analysis` | action |
| `native_control_interactive` | action, wait_timeout |
| `native_configure_interactive` | time_step, max_time_step, real_time, reset, persist, save_to_source |
| `native_interactive_status` | include_displays |
| `native_export_interactive_image` | output_path, overwrite, dpi, scale, region, fit_content, padding, show_frame, show_grid, active_component, wait_timeout |
| `native_read_waveform` | raw_path, offset, limit, plot_index |
| `native_export_image` | output_path, overwrite, dpi, scale, region, fit_content, padding, show_frame, show_grid |
| `native_run_ac_sweep` | sweep, points, start_hz, stop_hz, persist, save_to_source, use_saved_settings |
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
| `native_auto_route_wire` | wire_id, clearance, engine |
| `native_configure_wiring` | autowire_on_connection, autowire_on_move, connect_touching, move_connection_limit, reset, persist |
| `native_connect_touching` | component_refs |

Use the schemas returned by MCP `tools/list` for parameter types and defaults.
参数类型和默认值以 MCP `tools/list` 返回的 schema 为准。

### Shared power references / 同名电源符号

VCC and VEE symbols can share a reference. Use the selected symbol's current `id` as `component_ref`, batch `ref` or a wiring endpoint's `ref`. Movement, rotation and contact processing retain that symbol's identity and update its own physical pin attachments. Wire endpoints include `component_id`. `native_list_wires` accepts an ID to isolate one symbol, or a shared reference to list all matching symbols. Ambiguous edit targets return candidate IDs without changing the circuit.

VCC、VEE 等电源符号可以重名。将所选符号当前的 `id` 传给 `component_ref`、批处理 `ref` 或连线端点的 `ref`。移动、旋转与接触处理按对象身份更新该符号实际连接的导线。导线端点返回 `component_id`；`native_list_wires` 传入 ID 只列出该符号的导线，传入共享名称则列出所有同名符号的导线。编辑目标重名时返回候选 ID，保留电路状态。

### `native_repair_wire_geometry`

Synchronize symbol and junction graphics with grid-snapped electrical connectors, then align wire endpoints on the selected sheet. This is one undoable edit. Returns aligned components/junctions, changed wire IDs, endpoint verification and fresh state. Electrical attachments are preserved.

将当前图纸的元件、接点图形同步到电气连接坐标，再校正导线端点，支持一次撤销。返回校正的元件、接点、导线及验证结果和完整状态，保留原电气连接关系。

### Saved circuits / 工程保存

`native_save_copy` checks content bounds on every sheet and reopens a separate verification copy by default. It compares saved component values, positions, labels and wire routes while preserving the active document and its object handles. Move content inside the page or resize the real sheet before saving. Set `allow_off_page: true` for an intentionally off-page drawing, or `verify: false` to skip readback. Existing targets require `overwrite: true`; the previous file is backed up before replacement.

`native_save_copy` 默认检查所有图纸的内容边界，并打开独立校验副本，比较保存后的元件值、位置、标签和导线路径，保留当前文档及对象句柄。保存前将内容移入图纸或调整实际图纸尺寸。有意保留纸外布局时使用 `allow_off_page: true`，使用 `verify: false` 可跳过重开校验。覆盖已有文件需传入 `overwrite: true`，替换前保留旧文件备份。

### Interactive simulation / 交互仿真

`native_configure_interactive(time_step: 0.001, max_time_step: 0.001, real_time: true)` sets temporary session overrides by default. Select steps that resolve the fastest relevant signal and verify the result. `interactive_options.last_start` reports effective temporary startup parameters. Add `persist: true` to write native document settings, then `native_save_copy` to retain them. Add both `persist: true` and `save_to_source: true` for an explicitly authorized original-file update: the server backs up the original, checks external changes, saves natively and independently reopens to verify all simulation settings. Ordinary GUI starts after reopening use the saved values. `saved_to_file: false` means a save is still needed. Read with `persist: true` and no options. Change while stopped; `reset: true` restores automatic steps and real-time pacing in the selected scope. Persistent changes clear session overrides and preserve numeric-analysis definitions and other solver options.

上述参数默认仅本会话有效。添加 `persist: true` 写入原生文档，再另存；同时添加 `save_to_source: true` 则先备份，保存回原文件并独立重开核对。重开后普通启动仿真也使用保存的参数。`saved_to_file: false` 表示还需保存；只传 `persist: true` 读取文档设置。`persist: true, reset: true` 恢复文档的自动步长和实时节奏，再保存即可保留。停止仿真后修改，设置不会覆盖数值分析定义和其他求解器选项。

`native_control_interactive` accepts `start`, `pause`, `resume` and `stop`. It returns the observed `state_name`, `simulation_time_s`, errors and `transition_confirmed`. Repeating an already reached state is idempotent. A queued command with `transition_confirmed: false` is still pending; poll `native_interactive_status`. Numeric-session cleanup occurs before starting interactive simulation and preserves object handles. Stop interactive simulation before editing, regenerating the netlist or running numeric analysis.

`native_control_interactive` 支持 `start`、`pause`、`resume`、`stop`，返回实际状态 `state_name`、仿真时间 `simulation_time_s`、错误及 `transition_confirmed`。重复请求已达到的状态不会重新运行；`transition_confirmed: false` 表示仍待确认，可继续查询状态。数值分析切换到交互仿真前自动清理仿真会话，保留对象句柄。编辑、重新生成网表或运行数值分析前，先停止交互仿真。

`native_interactive_status(include_displays: true)` reads native `SEVEN_SEG_COM_A` segment states in `abcdefg` order. `native_export_interactive_image` captures those actual states and the circuit through the native bitmap renderer. Set `active_component` to a display reference to wait for its lit digit. Paused simulation preserves one scan phase; resume before waiting for a different digit. Multiplexed displays illuminate in successive phases, so capture each digit separately. Each image returns `capture_mode: instantaneous`, `display_states` and simulation status; frames are not accumulated into a simultaneous display.

`native_interactive_status(include_displays: true)` 读取原生 `SEVEN_SEG_COM_A` 的段状态，顺序为 `abcdefg`。`native_export_interactive_image` 通过原生位图引擎导出实际显示状态和电路；`active_component` 可指定要等待点亮的数码管。暂停会保留某个位选阶段，等待另一位前先恢复仿真。动态扫描电路逐位点亮，应分别截取各位。每张图片返回 `capture_mode: instantaneous`、`display_states` 和仿真状态。

See [persistence ownership](persistence.md) for advanced native settings, source saves, application preferences and external-only capabilities.
