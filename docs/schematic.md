# Schematics / 原理图

## Coordinates / 坐标

`native_create_circuit` and `native_open_copy` return an initial `state`. Use `native_get_circuit_state` to read sheets, components, named pins, wire vertices, labels and content bounds together.

`native_create_circuit` 与 `native_open_copy` 返回初始 `state`。通过 `native_get_circuit_state` 可一次读取图纸、元件、命名引脚、导线、标签与内容边界。

Coordinates use **sheet units**, with a top-left origin and 96 units per inch. Read `page.width`, `page.height` and `page.bounds` before placing components. The bundled blank sheet is 960 × 720; printing-paper dimensions are separate. Wire vertices and pin positions use the same coordinate system.

坐标使用**图纸单位**，原点在左上角，每英寸 96 单位。放置前读取 `page.width`、`page.height` 和 `page.bounds`。附带的空白图纸为 960 × 720，打印纸尺寸单独返回。导线顶点和引脚位置使用同一套坐标。

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

## Images and labels / 图片与标签

`native_export_image` renders at the requested DPI using the native engine. `dpi` accepts 36–600; `scale` applies additional scaling. Use `fit_content: true` and optional `padding` to include the complete circuit, including off-page objects. Alternatively, supply an absolute sheet-coordinate region:

图片由原生引擎按指定 DPI 渲染，`dpi` 范围为 36–600，`scale` 可继续调整倍率。`fit_content: true` 配合 `padding` 可完整导出电路及图纸外对象；也可指定绝对图纸坐标区域：

```json
{
  "output_path": "C:/Circuits/divider.png",
  "dpi": 192,
  "region": {"left": 100, "top": 80, "right": 700, "bottom": 500}
}
```

Choose either `region` or `fit_content`. Export leaves component positions, connections and sheet dimensions unchanged. The maximum image size is 32 million pixels. Whole-page export returns off-page references and rejects an export when every component lies outside the page.

`region` 与 `fit_content` 二选一。导出保持元件位置、连接和图纸尺寸，最大图片为 3200 万像素。整页导出会返回页外元件引用；所有元件均在页外时会提示改用适配内容或区域导出。

Move an overlapping reference label with `native_move_component_label(component_ref, x, y)`. Coordinates specify the label's center. Read label bounds from `state.components[].labels`; the symbol and electrical pins remain at their existing positions.

参考号重叠时，使用 `native_move_component_label(component_ref, x, y)` 移动标签中心。标签边界位于 `state.components[].labels`，元件符号和电气引脚保持原位。

## Numeric results / 数值结果

Analysis uses the generated SPICE source. Waveform variables and summaries include their units; numeric values use SI units, and CSV headers carry units such as `[V]`, `[A]`, `[s]` and `[Hz]`. A source current of `-0.006` A means −6 mA.

分析使用生成的 SPICE 源码。波形变量和汇总数据提供单位，数值使用 SI 单位，CSV 表头标注 `[V]`、`[A]`、`[s]`、`[Hz]` 等。电源电流 `-0.006` A 表示 −6 mA。

For a 12 V divider with two 1 kΩ resistors, verify both the 6 V midpoint and the −0.006 A source current against the actual resistance parameters and SPICE source.

12 V、两只 1 kΩ 的分压电路应结合真实阻值参数和 SPICE 源码，同时验证中点 6 V 与电源电流 −0.006 A。
