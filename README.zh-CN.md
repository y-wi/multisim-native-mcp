# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

通过 AI 助手创建、编辑和仿真 NI Multisim 原生电路的 MCP 服务。生成的 `.ms14` 文件可直接在 Multisim 中打开并继续编辑。

- **搭建与编辑电路**：放置库元件、连接引脚和支点、布线、修改注释，管理图纸、子电路和层级端口。
- **保存设计与设置**：直接修改已有文件，保留元件参数、内嵌 SPICE 模型、图纸属性和仿真配置。
- **运行原生分析**：直流工作点、瞬态和 AC 分析，支持 RAW/CSV 结果、波形测量和参数扫描。
- **控制交互仿真**：启动、暂停、继续和停止，设置实时节奏，捕获 LED 与数码管的实际显示状态。
- **自动完成连续任务**：通过可续跑工作流串联编辑、分析、测量、保存和原理图导出。

## 0.5.1 更新

- 修改和删除自由文本，更新图纸属性、层级端口与分支支点。
- 修复删除已连接层级端口后的文件保存，支持撤销和重做后的正常保存。
- 单工具、批量编辑和工作流使用一致的选择参数，默认返回精简的元件参数。
- 文档刷新后返回对象 ID 映射；保存校验失败时列出具体字段差异。

完整变更见[更新日志](CHANGELOG.md)。

## 系统要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| NI Multisim | 14.3，32 位 |
| Python | CPython 3.12，32 位；安装脚本自动配置 |
| MCP 通信方式 | STDIO |

## 安装

在 PowerShell 中运行，安装服务并配置 Codex：

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.5.1/install.ps1 | iex
```

安装脚本会配置所需的 32 位 Python 环境及包依赖。重启 Codex 后加载 `multisim_native`。

更新已有安装时，下载并使用 `-Force` 重新安装：

```powershell
$installer = Join-Path $env:TEMP "multisim-native-install.ps1"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/install.ps1" -OutFile $installer
& $installer -Force
```

使用 DeepSeek Harness 时，向已下载的安装脚本指定目标配置：

```powershell
& $installer -Client dsh -Profile desktop
```

### 安装选项

| 选项 | 用途 |
| --- | --- |
| `-MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.3'` | 指定 Multisim 安装目录 |
| `-Client dsh -Profile desktop` | 配置 DeepSeek Harness；也支持 `web`、`tui` |
| `-Client none` | 安装并输出其他 MCP 客户端所需的配置 |
| `-ConfigPath <path>` | 指定客户端配置文件 |
| `-Force` | 重新安装包 |

DSH 配置自动重新加载 MCP 连接。其他 MCP 客户端可使用 `-Client none`，将安装脚本输出的 JSON 填入客户端的服务配置。

检查安装和 MCP 连接：

```powershell
$mcp = Join-Path $env:LOCALAPPDATA "MultisimNativeMCP\bin\multisim-native-mcp.exe"
& $mcp doctor --connect
```

从源码安装时，克隆本仓库后运行 `.\install.ps1`。[发行页面](https://github.com/y-wi/multisim-native-mcp/releases/tag/v0.5.1)也提供 wheel、源码包和 `SHA256SUMS`。

## Agent 技能

可选的 [multisim-native skill](skills/multisim-native/SKILL.md) 为助手提供电路编辑与原生仿真操作方法。在 Codex 中安装：

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $env:USERPROFILE ".codex\skills" }
$skillArchive = Join-Path $env:TEMP "multisim-native-skill-0.5.1.zip"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/multisim-native-skill-0.5.1.zip" -OutFile $skillArchive
Expand-Archive -LiteralPath $skillArchive -DestinationPath $skillRoot -Force
```

重启 Codex 后，通过 `$multisim-native` 调用，或直接描述 Multisim 任务。其他支持 skill 的客户端可将压缩包解压到各自的技能目录，保留 `multisim-native` 文件夹。从源码安装时，也可直接复制 `skills/multisim-native`。

## 使用

可以直接提出：

> 新建一个 12 V 电源与两个 1 kΩ 电阻组成的分压电路，保存到当前工作目录，并导出 PNG。

> 打开已有 `.ms14` 电路，把 R2 改为 2.2 kΩ，保存源文件。

> 配置这个流水灯的仿真步长与实时节奏，保存设置，再导出一张实际点亮的画面。

### 创建与保存电路

新建电路时提供完整绝对文件名，父目录需已存在：

```json
{"output_path":"C:/Circuits/divider.ms14","title":"Voltage divider"}
```

将上述参数传给 `native_create_circuit`。编辑已有电路时，向 `native_open_circuit` 提供 `source_path`。存在一个运行中的 Multisim 窗口时会复用该窗口；需要选择特定进程或文档时使用 `native_attach`。

正常保存使用 `native_save_source`。`native_close_copy` 先保存待保存的修改，再关闭自有会话或从已有窗口断开。`native_save_copy(output_path)` 用于另存为；`native_open_copy` 用于创建独立对照副本。保存当前文件无需额外覆盖标志，替换其他已有文件使用 `overwrite:true`。

文件位置由每次请求指定，备份和恢复检查点自动管理。

### 保存仿真设置

先停止仿真，再调用 `native_configure_interactive`：

```json
{"time_step":0.001,"max_time_step":0.001,"real_time":true,"save_to_source":true}
```

这会把 1 ms 步长与实时节奏保存到当前 `.ms14` 文件。步长应能分辨电路中最快的相关信号。不传 `save_to_source` 时，设置保留在文档中，在正常保存或关闭后写入文件；`persist:false` 用于临时会话设置。

`native_simulation_settings` 可发现并修改分析配置和求解器选项，`interactive` 与 `analysis` 两种作用域独立。数值分析可通过 `persist:true` 保留运行参数，或通过 `use_saved_settings:true` 执行已保存的 OP/AC/TRAN 配置。详见[仿真设置与持久保存](docs/persistence.md)。

### 工作流与长任务

`native_run_workflow` 连续完成编辑、分析、数值判据、保存和导出。使用 `native_workflow_status` 查询进度，使用 `native_control_workflow` 取消或续跑。独立数值分析使用 `native_start_analysis`、`native_analysis_status` 和 `native_control_analysis`。

长任务在后台持续运行，客户端可读取进度。工作流默认不设总时限；需要时可用 `max_runtime` 指定。

[工作流指南](docs/workflows.md) · [完整分压电路请求](skills/multisim-native/assets/workflow_divider.json) · [Python 示例](examples/voltage_divider.py)

## 指南

- [电路编辑、连线与导出](docs/schematic.md)
- [仿真设置与持久保存](docs/persistence.md)
- [测量、扫描与报告](docs/experiments.md)
- [全部工具](docs/tools.md)

工具参考包含推荐的连线和删除入口、批量选择参数、完整参数读取方法以及对象 ID 映射。已有工具别名继续兼容。

## 常见问题

- **找不到 Multisim**：重新运行安装脚本，通过 `-MultisimPath` 指向包含 `Multisim.exe` 的目录。
- **客户端未显示服务**：重启或重新连接客户端，再使用上面的命令运行 `doctor --connect`。
- **操作失败**：根据返回的错误详情定位对象或设置；保存校验错误会列出差异字段和诊断文件路径。

可通过 [GitHub Issues](https://github.com/y-wi/multisim-native-mcp/issues) 提交可复现的问题。

## 配置

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim 安装目录 | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | 恢复文件与会话产物目录 | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `MULTISIM_NATIVE_IO_DIR` | 旧版 SPICE 文件传输使用的可选英文目录 | 系统临时目录 |
| `CODEX_HOME` | Codex 配置目录 | `%USERPROFILE%\.codex` |

## 许可证

[MIT](LICENSE)。
