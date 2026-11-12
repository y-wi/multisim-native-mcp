# Schematics / 原理图

## Native autowiring / 原生自动布线

`native_configure_wiring` reads or changes Multisim's native wiring settings. Connections use the native router, moves reroute attached wires below the configured connection limit, and touching pins connect during placement or movement. Moves outside that limit preserve existing attachments and route shape. Settings apply to the current session and restore on close or `reset: true`.

`native_configure_wiring` 读取或修改 Multisim 原生连线设置。连线调用原生布线器；连接数量低于设定阈值时，移动元件会重新布线；放置或移动时可自动连接接触的引脚。超过阈值的移动保留已有连接和走线形状。设置作用于当前会话，关闭或调用 `reset: true` 后恢复。

```json
{
  "autowire_on_connection": true,
  "autowire_on_move": true,
  "connect_touching": true,
  "move_connection_limit": 32
}
```

Use `native_connect_touching(component_refs)` to connect contacts already present on the selected sheet. A pin contacting a wire interior creates a native branch junction. Contacts at crossings of different nets return an error so the intended connection can be specified explicitly. Splitting a wire can replace its ID; consume the returned fresh state.

通过 `native_connect_touching(component_refs)` 可连接当前图纸中已经接触的引脚。引脚接触导线中段时创建原生分支节点；遇到不同网络的交叉点会返回错误，需明确指定目标连接。拆分导线可能替换其 ID，后续使用返回的新状态。

`native_auto_route_wire(wire_id)` reroutes one existing wire with Multisim's router while retaining its ID, labels and electrical endpoints. Batch construction supports `autoWire` with `arguments: {"id": "..."}` and `connectTouching` with `arguments: {"refs": ["R1", "R2"]}`. `native_plan_wire_route` previews the separate MCP obstacle planner; select `engine: "obstacle"` in `native_auto_route_wire` to apply that route with a custom `clearance`.

`native_auto_route_wire(wire_id)` 使用 Multisim 原生布线器重新规划已有导线，保留导线 ID、标签与电气端点。批处理支持 `autoWire`（参数 `{"id": "..."}`）和 `connectTouching`（参数 `{"refs": ["R1", "R2"]}`）。`native_plan_wire_route` 预览独立的 MCP 避障算法；在自动布线工具中选择 `engine: "obstacle"` 可应用该路径并自定义 `clearance`。

Native automatic routing requires endpoints inside the sheet. Resize the sheet or move the circuit inside before routing. Explicit wire points remain available for planned paths.

原生自动布线要求端点位于图纸内。布线前应调整实际图纸尺寸或将电路移入图纸；已规划的路径仍可通过显式导线顶点设置。

## Coordinates / 坐标

`native_create_circuit(output_path, title)` and `native_open_circuit(source_path)` return an initial `state`. Use `native_get_circuit_state` to read sheets, components, named pins, wire vertices, labels and content bounds together.

`native_create_circuit(output_path, title)` 与 `native_open_circuit(source_path)` 返回初始 `state`。通过 `native_get_circuit_state` 可一次读取图纸、元件、命名引脚、导线、标签与内容边界。

Coordinates use **sheet units**, with a top-left origin and 96 units per inch. Read `page.width`, `page.height` and `page.bounds` before placing components. The bundled blank sheet is 960 × 720; printing-paper dimensions are separate. Wire vertices and pin positions use the same coordinate system.

坐标使用**图纸单位**，原点在左上角，每英寸 96 单位。放置前读取 `page.width`、`page.height` 和 `page.bounds`。附带的空白图纸为 960 × 720，打印纸尺寸单独返回。导线顶点和引脚位置使用同一套坐标。

Placement defaults to the library graphic `anchor: origin`, which can be offset from both the symbol body and its pins. Use `anchor: center` for the body center, or `anchor: pin` with an exact `pin` name to place that connector at the requested coordinates. The result's `placement` includes requested and actual anchor positions, graphic origin and body bounds. Read returned pins before routing because grid snapping applies.

放置默认使用元件库图形原点 `anchor: origin`，该点可能既不是符号中心，也不是引脚。可选择 `anchor: center` 按符号主体中心放置，或使用 `anchor: pin` 配合准确的 `pin` 名称按引脚放置。结果中的 `placement` 提供请求位置、实际锚点、图形原点与主体边界。网格吸附可能调整位置，布线必须读取返回的真实引脚坐标。

## Connector graphics / 连接图形

Pins and wire endpoints include `graphic_position` and `graphics_aligned` alongside grid-snapped `x`/`y`. `native_check_layout` checks both positions. Use `native_repair_wire_geometry` when an imported circuit looks disconnected despite an intact electrical netlist; it synchronizes symbols, junctions and wire routes as one undoable edit. Saving and image export also synchronize connector graphics. Undo checkpoints preserve their original geometry.

引脚与导线端点同时提供吸附后的 `x`/`y`、图形位置 `graphic_position` 及对齐状态 `graphics_aligned`；`native_check_layout` 会同时检查两者。导入电路电气连接正常、图形却留有缝隙时，使用 `native_repair_wire_geometry` 同步元件、接点和走线，支持一次撤销。保存和图片导出也会同步连接图形；撤销检查点保留原几何状态。

## Components and parameters / 元件与参数

`native_search_library` returns `Family_Name` and `Group_Name`. Filter by exact `family` and `group` names. For an adjustable resistor, search `RESISTOR_VIRTUAL` in family `RESISTOR`. Placement returns the actual model, native reference prefix and indexed parameters. Primary parameters include a name, unit and `role: value`.

元件库搜索返回真实族名与组名，可通过 `family` 和 `group` 精确筛选。可调电阻可选择 `RESISTOR` 族的 `RESISTOR_VIRTUAL`。放置结果提供实际模型、默认参考号前缀和参数索引；主参数包含名称、单位及 `role: value`。

Set parameters during placement:

放置时可直接设置参数：

```json
{
  "name": "RESISTOR_VIRTUAL",
  "x": 300,
  "y": 180,
  "reference": "R1",
  "parameters": [{"index": 1, "value": 1000}]
}
```

Use `native_edit_batch` to place components, set their values and connect named pins in one request. Its `state` contains the resulting references, parameter values, pins and wires. See the [voltage-divider example](../examples/voltage_divider.py).

通过 `native_edit_batch` 可在一次请求中放置元件、设置数值并连接引脚。返回的 `state` 包含最终参考号、参数、引脚和导线。参见[分压电路示例](../examples/voltage_divider.py)。

`native_check_netlist` refreshes changed topology. If `handles_invalidated` is true, use the returned `state` for the new handles. Parameter, label and geometry edits preserve handles. Prefer named component references for subsequent edits.

网表检查仅在拓扑改变时刷新连接。`handles_invalidated` 为 true 时，直接使用返回的 `state` 获取新句柄；参数、标签和几何编辑保留句柄。后续编辑优先使用元件参考号。

Batch edits are atomic by default: a failed operation rolls back that batch while preserving earlier calls. Set `atomic: false` to keep completed operations and roll back only the failed operation. An edit failure reports `rollback_scope`, `completed_operations`, `handles_invalidated` and fresh `state`. Invalid first-operation references fail before creating a checkpoint and keep handles intact.

批量编辑默认具有原子性：失败时回滚本批，保留之前调用的修改。设置 `atomic: false` 可保留本批已完成操作，只回滚失败步骤。编辑错误会返回回滚范围、保留操作数、句柄失效状态与最新 `state`。首步引用名错误会在创建检查点前被发现，保留现有句柄。

## Saved sheet layout / 保存图纸布局

Before saving a finished schematic, check that `content_bounds` lies inside `page.bounds` with a margin. Include symbols, labels, text and wire routes. Move the complete layout inside the page, or enlarge the real sheet through `native_edit_batch` with a `sheetSize` operation:

保存完整原理图前，检查 `content_bounds` 是否位于 `page.bounds` 内并留有边距，检查范围包括元件、标签、文字与导线路径。可将完整电路移入图纸，或通过 `native_edit_batch` 的 `sheetSize` 操作增大真实图纸：

```json
{"operations":[{"operation":"sheetSize","arguments":{"width":1200,"height":900}}],"include_state":true}
```

Choose dimensions from actual content bounds; enlarging width and height does not correct negative left/top coordinates. Save and reopen the output to verify that the page contains the circuit, then inspect a whole-page image without `region` or `fit_content`. These image options change framing only and preserve the original saved-sheet dimensions.

尺寸应依据实际内容边界确定；增加宽高不能解决左侧或上侧的负坐标。保存时原生回读会核对内容，纸外对象不会阻止保存。按需要检查整页或裁剪图片。这两个图片选项仅改变取景范围，会保留原有图纸尺寸。

## Images and labels / 图片与标签

`native_export_image` renders at the requested DPI using the native engine. `dpi` accepts positive integers; `scale` applies additional scaling. Use `fit_content: true` and optional `padding` to include the complete circuit, including off-page objects. Alternatively, supply an absolute sheet-coordinate region:

图片由原生引擎按指定 DPI 渲染，`dpi` 为正整数，`scale` 可继续调整倍率。`fit_content: true` 配合 `padding` 可完整导出电路及图纸外对象；也可指定绝对图纸坐标区域：

Export defaults to a clean circuit image. Set `show_frame: true` to include the sheet border and title block, or `show_grid: true` to include the dot grid. Export restores the original display settings.

默认导出纯电路图片；设置 `show_frame: true` 可显示图框及标题栏，`show_grid: true` 可显示点阵网格。导出结束后恢复原显示设置。

```json
{
  "output_path": "C:/Circuits/divider.png",
  "dpi": 192,
  "region": {"left": 100, "top": 80, "right": 700, "bottom": 500}
}
```

Choose either `region` or `fit_content`. Export preserves electrical attachments and sheet dimensions; connector graphics are synchronized before rendering. There is no MCP pixel quota. Bitmap file format and available memory determine rendering capacity. Whole-page export reports off-page references without blocking the export.

`region` 与 `fit_content` 二选一。导出前会同步连接图形，保留电气连接和图纸尺寸，最大图片为 3200 万像素。整页导出会返回页外元件引用；所有元件均在页外时会提示改用适配内容或区域导出。

Move a reference or value label with `native_move_component_label(component_ref, x, y, kind)`, where `kind` is `reference` (default) or `value`. Coordinates specify the label's center. Read label text and bounds from `state.components[].labels`; the symbol and electrical pins remain at their existing positions. Parameter edits refresh native value text immediately, and rotation keeps labels upright and clear of the symbol body.

使用 `native_move_component_label(component_ref, x, y, kind)` 可移动标签中心，`kind` 为 `reference`（默认参考号）或 `value`（数值）。标签文字和边界位于 `state.components[].labels`，元件符号和电气引脚保持原位。参数修改会立即刷新原生值标签；旋转后标签保持正向，并避开符号主体。

## Numeric results / 数值结果

Analysis uses the generated SPICE source. Waveform variables and summaries include their units; numeric values use SI units, and CSV headers carry units such as `[V]`, `[A]`, `[s]` and `[Hz]`. A source current of `-0.006` A means −6 mA.

分析使用生成的 SPICE 源码。波形变量和汇总数据提供单位，数值使用 SI 单位，CSV 表头标注 `[V]`、`[A]`、`[s]`、`[Hz]` 等。电源电流 `-0.006` A 表示 −6 mA。

For a 12 V divider with two 1 kΩ resistors, verify both the 6 V midpoint and the −0.006 A source current against the actual resistance parameters and SPICE source.

12 V、两只 1 kΩ 的分压电路应结合真实阻值参数和 SPICE 源码，同时验证中点 6 V 与电源电流 −0.006 A。

Add `persist:true` to `native_configure_wiring` to commit native application-wide preferences and verify reload. They survive a new Multisim process but are not `.ms14` content. To retain selected-sheet grid, border or bounds, use `native_configure_sheet_display` and save. Page-name edits now update the saved native page name, while the root window caption follows the filename. General source saves verify annotations and embedded models; model edits refresh all affected labels before saving. See [persistence ownership](persistence.md).

Off-page wiring uses explicit orthogonal routes when the native router cannot route outside the sheet. Moving outside the sheet preserves attached wire geometry. The MCP does not reject these edits. Sheet dimensions must fit the native CUTRect work-area fields after unit conversion; these fields are signed 32-bit integers. Rotation accepts finite angles, including fractional degrees.

Named wires save their native network name and visibility. Generated node text is reconstructed by Multisim and is verified separately from independent annotations. Deleting a generated net label clears that wire’s user name/display while preserving the wire. `native_list_projects` can attach the sole running Multisim process; `native_runtime_status` distinguishes running applications from the attached MCP session.
