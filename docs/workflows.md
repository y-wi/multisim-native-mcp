# Circuit workflows / 电路工作流

`native_run_workflow` executes dependent circuit stages within one MCP request. It prepares library metadata, resolves real pins, checks the circuit, runs native analysis, evaluates criteria and publishes outputs. Individual tools remain available for local changes.

`native_run_workflow` 在一次 MCP 请求内连续执行电路任务：准备库元件、解析实际引脚、检查电路、原生仿真、指标验收和文件交付。局部调整仍可使用单步工具。

Use the complete [12 V divider request](../skills/multisim-native/assets/workflow_divider.json): create its output directory, adjust the two output paths and submit the JSON arguments. The workflow verifies a 6 V midpoint and −6 mA source current, saves an editable circuit with native readback, exports a PNG and closes its owned session.

可直接使用完整的 [12 V 分压请求](../skills/multisim-native/assets/workflow_divider.json)：创建输出目录、修改两个输出路径，再提交 JSON 参数。工作流验证 6 V 分压和 −6 mA 电源电流，保存可编辑工程并原生回读，导出 PNG 后关闭自有会话。

## Execution / 执行

- `native_prepare_components`: prepare several unknown library types together; return exact pins and parameter descriptors. The drawing is restored after probing and metadata is cached for the session.
- `native_run_workflow`: submit a typed `plan` and wait up to 30 seconds. Stages include session, preparation, wiring, editing, layout, analysis/acceptance, waveform verification, display decoding, saving, exporting and interactive captures.
- `native_workflow_status`: wait for completion or a decision boundary. Use a nonzero `wait_timeout` for ongoing work. Default results contain key measurements and files; `detail: true` reads full stored diagnostics and bindings.
- `native_control_workflow`: cancel or explicitly resume an unfinished workflow, optionally replacing the remaining stages.
- `native_session_changes`: obtain a revision and full/incremental state. Pass the revision as the plan's `expected_revision` to reject stale input.

Use `bind` on an edit operation and `{"$ref":"lower.component.id"}` in dependent arguments. Every stage also binds its result to its `id`. References support earlier results, array indices and two-term `$add`/`$sub` numeric offsets. Placement `value` selects an unambiguous primary-value parameter; named-pin voltage selectors avoid guessing waveform node numbers. `alignPin` moves a selected native pin to a requested sheet coordinate.

编辑操作通过 `bind` 命名结果，后续参数用 `{"$ref":"lower.component.id"}` 引用。每个阶段也会以自己的 `id` 保存结果。支持前序结果、数组索引和两个数的 `$add`/`$sub` 运算。放置时的 `value` 自动选择唯一的主值参数；电压测量可指定元件及引脚，无需猜测波形节点编号。`alignPin` 可将指定原生引脚移动到目标图纸坐标。

## Results and recovery / 结果与恢复

Check `status`: only `complete` means the whole plan finished. `needs_input` returns unresolved library choices, stale revisions or failed criteria. `failed` includes the exact failed stage and rollback details. Detailed records and analysis artifacts are stored in the user's MCP data directory.

Each edit stage is one rollback unit. Up to eight edits run per native UI-thread slice before yielding. A failed edit stage rolls back that stage; earlier successful stages remain. Analysis and output failures retain prior successful edits and completed files. Resume retries only the unfinished tail. After a service restart, an interrupted workflow can reopen its last saved successful phase. Rebinding requires a unique physical match.

检查返回的 `status`，只有 `complete` 表示整份计划完成。`needs_input` 会返回待选择的库元件、过期版本或未通过的判据；`failed` 包含具体失败阶段及回滚信息。详细记录和分析产物保存在用户的 MCP 数据目录。

每个编辑阶段为一个回滚单元；原生 UI 线程每组最多执行八项编辑，再交还消息处理。编辑失败只回滚本阶段，保留之前完成的阶段。分析、文件输出失败保留此前成功的编辑与文件；续跑只执行未完成部分。服务重启后可从上一个成功阶段的快照恢复，对象映射需能够唯一确认。

Interactive stages can configure, start, wait for requested display digits, capture several real frames and stop. Each frame retains its actual native display state. Runtime budgets request cancellation at supported native boundaries. Electrical values and acceptance limits change only when supplied in an updated plan.

Set `persist: true` on an `interactive` stage to write its steps and pacing into native document settings. Follow with a `save` stage to retain them in the output `.ms14`. Without `persist`, overrides last only for the current MCP session. Explicit original-file replacement is available through `native_configure_interactive(persist: true, save_to_source: true)` with backup and reopen verification.

交互阶段可以配置、启动仿真，在本地等待指定数字，连续截取多个真实画面后停止；每张截图均附实际原生显示状态。运行时间预算会在支持的原生边界请求取消。电气参数和验收范围由提交的计划明确指定。

`stats.external_calls` counts workflow API calls; `native_calls` and `native_seconds` measure host RPC work. Model reasoning turns require client-side measurements. See the self-contained [workflow skill reference](../skills/multisim-native/references/workflows.md) for schemas and examples.

`stats.external_calls` 统计工作流 API 调用次数，`native_calls`、`native_seconds` 统计原生主机 RPC。模型推理轮次需由客户端记录。完整字段与示例见 [工作流 skill 参考](../skills/multisim-native/references/workflows.md)。
