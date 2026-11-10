# Experiments / 实验

## AC and measurements / AC 与测量

Run `native_run_ac_sweep` with `sweep: lin`, `dec` or `oct`. `points` is the total count for `lin`, or points per decade/octave. The source's AC magnitude must be configured in the native circuit.

调用 `native_run_ac_sweep`，`sweep` 选择 `lin`、`dec` 或 `oct`。`lin` 的 `points` 为总点数，其余为每十倍频程或倍频程点数。先在原生电路中设置电源的 AC 幅值。

Pass the returned `raw_path` to `native_measure_waveform` or `native_verify_waveform`:

将返回的 `raw_path` 传给测量或验收工具：

```json
{
  "measurements": [
    {"id": "gain", "metric": "gain_db", "signal": "V(2)", "reference": "V(1)", "frequency_hz": 159.1549430918953},
    {"id": "phase", "metric": "phase_deg", "signal": "V(2)", "reference": "V(1)", "frequency_hz": 159.1549430918953}
  ],
  "criteria": [
    {"id": "gain", "target": -3.0103, "absolute_tolerance": 0.01},
    {"id": "phase", "min": -45.1, "max": -44.9}
  ]
}
```

Real-waveform metrics: `min`, `max`, `mean`, `rms`, `peak_to_peak`, `frequency`, `duty_cycle`. Use `start` and `stop` for a time window, and `threshold` for crossing measurements. Duty cycle is a fraction from 0 to 1. Mean and RMS integrate the actual adaptive time grid. AC transfer measurements interpolate complex samples at `frequency_hz`.

Measurements and acceptance criteria both use `id` to identify a metric. The legacy criterion key `measurement` remains accepted. Tool schemas expose the nested fields, and malformed requests report the failing field before waveform processing or simulation.

测量与验收条件统一使用 `id` 标识指标，兼容旧的条件字段 `measurement`。工具 schema 提供嵌套字段定义；格式错误会在读取波形或开始仿真前指出具体字段。

实数波形支持极值、均值、RMS、峰峰值、频率和占空比。`start`、`stop` 指定时间窗口，`threshold` 指定阈值；占空比取值 0 至 1。均值和 RMS 按实际采样时间积分，AC 增益与相位按复数样本插值。

`native_run_analysis` and `native_start_analysis` accept `use_initial_conditions: true` for transient UIC analysis. Each run saves a JSON diagnostic file with netlist checks and native command stages. `native_read_waveform` lists all plots; use `plot_index` to read an appended digital-node event plot. Digital event rows contain `time`, `rising`, `falling` flags.

瞬态分析可通过 `use_initial_conditions: true` 使用 UIC。每次分析保存网表检查和原生命令阶段的 JSON 诊断记录。`native_read_waveform` 返回所有数据段的元信息；通过 `plot_index` 读取附带的数字节点事件，事件列依次为时间、上升标志、下降标志。

## Parameter experiments / 扫参与选优

Use `native_run_parameter_sweep` for a synchronous persisted experiment, or `native_start_experiment` for a background job:

同步实验使用 `native_run_parameter_sweep`，后台实验使用 `native_start_experiment`：

```json
{
  "parameters": [{"ref": "R1", "index": 1, "values": [500, 1000, 2000]}],
  "analysis": {"analysis": "ac", "ac_sweep": "lin", "ac_points": 3, "ac_start": 159.1549430918953, "ac_stop": 477.464829275686},
  "measurements": [{"id": "gain", "metric": "gain_db", "signal": "V(2)", "reference": "V(1)", "frequency_hz": 159.1549430918953}],
  "criteria": [{"id": "gain", "min": -5}],
  "objective": {"measurement": "gain", "goal": "target", "target": -3.0103}
}
```

Read parameter indexes with `native_get_parameters` first. Up to four parameters and 100 Cartesian combinations are supported. Objective goals are `min`, `max`, `target`. `result.best` is the zero-based index of the best feasible trial. The original numeric parameters and expressions are restored after execution; the best candidate is returned for review.

先用 `native_get_parameters` 读取参数索引。支持最多 4 个参数、100 组组合。目标为最小值、最大值或最接近目标值。`result.best` 是最优可行候选的零起始索引。结束后恢复原数值和表达式，并返回选优结果。

Query records with `native_experiment_status` and `native_list_experiments`. Cancel with `native_cancel_experiment`; wait for terminal status and `result.restored`. To retry, close the current native session, then call `native_retry_experiment`. It opens a new copy of the saved source and creates a new ID with `retry_of`. Interrupted jobs remain queryable after service restart.

通过状态与列表工具查询持久记录。取消后等待最终状态与 `result.restored`。重试前关闭当前原生会话，再调用 `native_retry_experiment`；工具从已保存的源电路新开副本，并生成带有 `retry_of` 的新记录。服务重启后仍可查询中断的实验。

## Display verification / 数码管验收

`native_decode_seven_segment` takes digits in display order. Each digit has `label`, seven `segments` vector names ordered **a,b,c,d,e,f,g**, and a `select` vector. Set signal thresholds and polarities to match the supplied voltages or currents. `settling` skips the beginning of each selection interval; `min_dwell` specifies the minimum accumulated duration of a sustained pattern. The result includes per-digit patterns, durations and selection conflicts.

按显示顺序提供各位配置，每位包含标签、a 至 g 顺序的七个段信号，以及位选信号。阈值和有效极性对应输入的电压或电流。`settling` 跳过切换后的建立时间，`min_dwell` 指定持续图案的最短累计时间。结果包含各位图案、持续时间与位选冲突。

## Reports and routing / 报告与布线

`native_export_experiment_report` exports a saved record to an existing absolute directory. Choose `language: zh` or `en`; optional `signals` selects up to eight traces. Outputs: standalone HTML, Markdown, measurement CSV, native schematic PNG and waveform SVG.

报告工具将记录导出到已有绝对目录。选择中文或英文，可指定最多八个波形。产物包括独立 HTML、Markdown、测量 CSV、原生电路 PNG 和波形 SVG。

`native_check_layout` checks real native connector coordinates, drawing pens, orthogonal segments and component graphic bounds. `native_plan_wire_route` returns an obstacle-aware route without editing; `native_auto_route_wire` applies it as an undoable native edit. `clearance` is in native sheet units. Read wire IDs again after operations that invalidate handles.

布局检查使用真实原生端口坐标、导线画笔、线段和器件图形边界。路径规划工具返回避障路线，自动布线工具将路线应用为可撤销的原生编辑；`clearance` 使用图纸原生坐标单位。句柄失效后重新读取导线 ID。
