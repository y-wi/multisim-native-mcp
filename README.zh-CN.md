# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

通过 Model Context Protocol 创建、编辑和仿真可继续修改的 NI Multisim 原生电路。

- **原生电路编辑**：元件、命名引脚连线、分支、可修改的自由文本、标签、多图纸、子电路和内嵌 SPICE 模型。
- **直接保存文件**：在指定路径新建电路，或直接修改已有 `.ms14` 源文件；正常关闭时保存修改，自动管理备份和恢复检查点。
- **仿真设置持久保存**：支持 19 类原生分析配置与 44 项求解器选项，包括步长、误差容限、积分方法、收敛、温度和数字阈值。
- **分析与测量**：直流工作点、瞬态、AC 扫频，RAW/CSV 导出，以及频率、占空比、增益、相位和数值判据。
- **交互仿真**：启动、暂停、继续、停止，配置实时节奏，导出 LED 与数码管实际显示状态。
- **自动化与导出**：连续电路工作流、参数扫描、可续跑的后台任务、PNG/BMP 原理图及中英文报告。

提供 83 个工具，完整参数见[工具参考](docs/tools.md)。

## 系统要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| NI Multisim | 14.3，32 位 |
| Python | CPython 3.12，32 位；安装脚本自动配置 |
| MCP 通信方式 | STDIO |

## 安装

在 PowerShell 中运行：

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.5.1/install.ps1 | iex
```

重启 Codex 后加载 `multisim_native`。更新已有安装时，下载并使用 `-Force` 重新安装：

```powershell
$installer = Join-Path $env:TEMP "multisim-native-install.ps1"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/install.ps1" -OutFile $installer
& $installer -Force
```

安装脚本支持以下选项：

| 选项 | 用途 |
| --- | --- |
| `-MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.3'` | 指定 Multisim 安装目录 |
| `-Client dsh -Profile desktop` | 配置 DeepSeek Harness；也支持 `web`、`tui` |
| `-Client none` | 安装并输出其他 MCP 客户端所需的配置 |
| `-ConfigPath <path>` | 指定客户端配置文件 |
| `-Force` | 重新安装包 |

DSH 配置自动重新加载 MCP 连接。其他客户端可使用安装后命令输出的 JSON：

```powershell
$mcp = Join-Path $env:LOCALAPPDATA "MultisimNativeMCP\bin\multisim-native-mcp.exe"
& $mcp config
& $mcp doctor --connect
```

从源码安装时，克隆本仓库后运行 `.\install.ps1`。也可以直接安装 wheel：

```powershell
uv tool install --force --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/multisim_native_mcp-0.5.1-py3-none-any.whl
multisim-native-mcp configure
```

## Agent 技能

安装 [multisim-native skill](skills/multisim-native/SKILL.md)，提供电路工作流与原生仿真操作方法：

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $env:USERPROFILE ".codex\skills" }
$skillArchive = Join-Path $env:TEMP "multisim-native-skill-0.5.1.zip"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/multisim-native-skill-0.5.1.zip" -OutFile $skillArchive
Expand-Archive -LiteralPath $skillArchive -DestinationPath $skillRoot -Force
```

重启 Codex 后，通过 `$multisim-native` 调用，或直接描述 Multisim 任务。从源码安装时，也可将 `skills/multisim-native` 复制到同一技能目录。

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

文件位置由当前任务确定，MCP 不配置全局工程目录。

### 保存仿真设置

先停止仿真，再调用 `native_configure_interactive`：

```json
{"time_step":0.001,"max_time_step":0.001,"real_time":true,"save_to_source":true}
```

这会把 1 ms 步长与实时节奏保存到当前 `.ms14` 文件。步长应能分辨电路中最快的相关信号。不传 `save_to_source` 时，设置保留在文档中，在正常保存或关闭后写入文件；`persist:false` 用于临时会话设置。

`native_simulation_settings` 可发现并修改分析配置和求解器选项，`interactive` 与 `analysis` 两种作用域独立。数值分析可通过 `persist:true` 保留运行参数，或通过 `use_saved_settings:true` 执行已保存的 OP/AC/TRAN 配置。详见[仿真设置与持久保存](docs/persistence.md)。

### 工作流与长任务

`native_run_workflow` 连续完成编辑、分析、数值判据、保存和导出。使用 `native_workflow_status` 查询进度，使用 `native_control_workflow` 取消或续跑。独立数值分析使用 `native_start_analysis`、`native_analysis_status` 和 `native_control_analysis`。

工作流默认不设总时限；`max_runtime` 可指定时限，状态等待参数只决定何时返回响应。编辑批量、采样数量与导出尺寸不设 MCP 工作量上限，实际容量由原生数据格式及可用资源决定。客户端请求超时由客户端配置。

[工作流指南](docs/workflows.md) · [完整分压电路请求](skills/multisim-native/assets/workflow_divider.json) · [Python 示例](examples/voltage_divider.py)

## 指南

- [电路编辑、连线与导出](docs/schematic.md)
- [仿真设置与持久保存](docs/persistence.md)
- [测量、扫描与报告](docs/experiments.md)
- [全部工具](docs/tools.md)

## 配置

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim 安装目录 | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | 恢复文件与会话产物目录 | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `MULTISIM_NATIVE_IO_DIR` | 旧版 SPICE 文件传输使用的可选英文目录 | 系统临时目录 |
| `CODEX_HOME` | Codex 配置目录 | `%USERPROFILE%\.codex` |

## 许可证

[MIT](LICENSE)。
