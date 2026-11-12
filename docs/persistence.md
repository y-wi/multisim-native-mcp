# Persistence / 持久保存

`native_persistence_capabilities` describes where each tool stores its results: the native circuit document, application preferences, session state or external files.

## Native simulation settings

Read `native_simulation_settings` before changing a setting:

```json
{"scope":"interactive","analysis_type":"TRAN"}
```

The response contains `available_analyses`, typed scalar `fields` with exact relative paths, `solver_options` with enabled states, and a `revision`. Multisim 14.3 supplies 19 profiles in both `interactive` and `analysis` scopes: OP, AC, PHASOR, TRAN, FOUR, NOISE, DISTO, PSWEEP, TSWEEP, PZ, TF, DC_SWEEP, SENS, WORST, MONTE, USER, RUN, TRACEWIDTH and NOISE_FIGURE. Existing scalar fields are editable; whole native lists, empty profile lists and analysis instances are not created by this API. RAW/CSV execution supports OP, AC and TRAN; other profile settings are retained for Multisim's native analyses.

For example, customize interactive transient accuracy, integration, convergence, temperature and digital thresholds, then save directly to the source file:

```json
{
  "scope":"interactive",
  "analysis_type":"TRAN",
  "changes":[
    {"path":["ANALYSIS","IC"],"value":"auto_ic"},
    {"path":["DIGITAL_THRESHOLD_L"],"value":2},
    {"path":["DIGITAL_THRESHOLD_H"],"value":3}
  ],
  "solver_options":{"reltol":0.0002,"abstol":1e-12,"vntol":1e-6,"method":"gear","itl4":150,"temp":35},
  "save_to_source":true
}
```

These are examples, not universal recommended values. Read the current values and choose settings for the actual circuit. `IC` accepts `auto_ic`, `uic` or `zero_ic`; TSTEP/TMAX accept a number or `null` for automatic calculation. Solver option `null` or `false` disables the override; flag options use booleans. Setting solver values also selects native custom options (`USE_ASYS_OPT=1`, `MSM_ASYS_OPT=0`), because default selection otherwise masks stored custom values. All 44 native solver options are discoverable, including tolerances, iteration limits, integration method, temperature, gmin and digital solver flags. Native parsing/serialization preserves untouched fields and definitions.

The `analysis` scope controls saved analysis definitions; `interactive` controls default instrument/interactive settings. They are intentionally independent. Fields with duplicate names use zero-based integer indexes in the returned paths; updating these requires the catalog's `expected_revision`. A stale revision, missing/ambiguous field, unsupported value or failed readback rejects the operation. Transactions restore native checkpoints on failure and report invalidated handles.

Without `save_to_source`, changes remain in the editable native document: call `native_save_copy` or `native_save_source` to save them. `saved_to_file:false` means this call performed no disk save, including read-only catalog calls. Ordinary Multisim starts use saved configuration after reopening; no MCP launch override is required.

## Saved numeric analysis

`native_run_analysis`, `native_start_analysis` and `native_run_ac_sweep` accept `persist`, `save_to_source` and `use_saved_settings`:

- Defaults retain the existing behavior: explicit arguments apply only to that run.
- `persist:true` writes explicit transient/AC arguments into the native `analysis` profile and runs it. Add `save_to_source:true` to back up and save the source before the run; saved configuration is independent of whether a subsequent analysis succeeds.
- `use_saved_settings:true` runs stored OP/AC/TRAN settings and solver options through Multisim's native command compiler. This is exclusive with `persist:true`.
- Transient and AC execution validate finite values, positive steps/frequencies and their ordering, without MCP duration or sample-count quotas.

## Where settings are saved

| Capability | Destination and behavior |
| --- | --- |
| Component values, expressions, embedded models, placements, labels, wires, ports, subcircuits, annotations and sheets | Native document; save through `native_save_source` or `native_save_copy`. Model changes refresh every affected label before saving. |
| Native page name | Saved using `SetPageName`; the root window caption still follows the filename after reopening. |
| Grid, border and bounds | `native_configure_sheet_display` modifies the selected sheet's native preferences; save the document or pass `save_to_source:true`. |
| Autowiring and movement thresholds | Native **application-wide** preferences. `native_configure_wiring(persist:true)` saves through Multisim and verifies reloading, after reloading. These are not `.ms14` fields; temporary mode remains the default. |
| Title-block export visibility | Rendering flag only. Native load derives title-block presence from title-block graphics and overwrites a standalone `Title Block ON` value. It is an export rendering option. |
| Runtime start/pause/stop, simulation clock and LED/display phase | Live solver state; not portable circuit design settings. |
| Export DPI, crop, clean-frame flags and PNG/BMP/RAW/CSV results | External artifacts. Export cropping does not resize the document. |
| MCP sweeps, objectives, acceptance criteria, workflow plans and execution logs | Durable external experiment/workflow records, with native checkpoint circuits. They are not native PSWEEP definitions. Trials restore the original circuit; apply a selected candidate's parameter values explicitly, then save to retain the design. |
| Undo/redo and metadata caches | Session state. The resulting restored design can be saved; process-local history cannot be embedded as a portable circuit. |
| Inspection, routing plans and waveform calculations | Read-only outputs; no document setting to save. |

`native_save_source` saves **all** current document edits, not just simulation settings. It always checks external source changes, creates a backup, saves natively to a staged file and independently reopens it before source replacement. Verification covers components/parameters, embedded SPICE text, connectivity/geometry, labels, annotations, page names, grid/border/bounds and the complete simulation-information property. New circuits are created directly as workspace files and use the same normal source save; packaged templates remain internal resources.

## 中文要点

`native_simulation_settings` 先读取原生字段、类型、路径和版本，再修改。可编辑 19 类分析配置中的现有标量字段，以及 44 项求解器选项；列表与分析实例由原生文档管理。瞬态、交流、初始条件、数字阈值、误差容限、积分算法、迭代上限和温度均可写入文档并保存回源文件。自定义求解器参数会同步切换原生“使用自定义参数”标志，避免保存值被默认配置掩盖。

`native_save_source` 是统一的源文件保存入口，适用于元件、接线、模型、注释、图纸及仿真配置。保存前备份并检查外部修改，独立重开核对后才替换源文件。图纸网格、边框和坐标边界可持久保存；标题通过原生页名保存，根窗口标题仍由文件名决定。

自动连线偏好是软件全局设置，`persist:true` 保存到 Multisim 应用配置并验证，保存位置独立于 `.ms14`。运行中的仿真时间、暂停位置、灯光相位、导出参数、波形文件和 MCP 工作流/实验记录各有其运行时或外部保存位置。标题栏临时渲染开关会被原生加载逻辑覆盖，属于导出渲染选项。用 `native_persistence_capabilities` 可查询所有工具的准确保存归属。

## File editing defaults (0.5.0)

New circuits are real `.ms14` files in the task workspace from the start. The calling skill/agent resolves the filename from the task context and supplies an absolute `output_path`; the MCP has no global workspace or project-directory configuration. `native_open_circuit` and workflow `mode:open` edit the actual source. A single running Multisim is reused, opening/selecting the requested source while preserving its other projects. Multiple running processes can be selected with `native_attach`.

`native_save_source` and a workflow `save` without output_path update the current source. Normal close saves pending changes first; save failure leaves the session open. `save_changes:false` skips saving; detached user windows retain unsaved edits. Save As in direct mode becomes the current document, and saving the current path does not require an extra overwrite flag.

Editable copies are only created by explicitly choosing `native_open_copy` / `session.isolated_copy:true`, with an explicit output filename (or beside the source when omitted). Internal recovery backups, checkpoints, verification files and logs are distinct from the actual editable file. Comparison-mode normal close saves its comparison file, while explicitly calling native_save_source updates the original. Recovery/resume retains the actual source identity and external-change hash rather than making a checkpoint the deliverable.

Interactive configuration and interactive workflow stages default to document persistence. One-off numeric analysis arguments remain per-run unless persist:true is requested. Native calls have no fixed process-kill watchdog; native pause/stop controls remain available. Geometry, electrical validation and external-source conflict checks remain because they detect actual correctness/data-loss problems.

The server has no task watchdog or default workflow runtime deadline. Client transport timeouts and native Multisim/data-format limits are independent of the server. Use background analysis/workflow status APIs when the client needs short requests. Pagination defaults and internal edit slices do not cap total work.
