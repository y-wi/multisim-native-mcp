# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

通过 Model Context Protocol 编辑 NI Multisim 原生电路，执行仿真、测量和实验验收。

- 65 个 MCP 工具，涵盖元件、连线、图纸、子电路、模型与分析。
- 可配置交互仿真步长、实时节奏，并截取器件实际点亮状态。
- 生成可编辑的 `.ms14` 工程，支持按引脚名称连接和导线分支。
- 支持批量编辑、检查点、撤销、重做和原生保存重开。
- 直流工作点、瞬态与 AC 扫频分析，导出 RAW 与 CSV 数据。
- 时间加权波形测量、指标验收与扫描数码管解码。
- 参数扫描、候选选优、持久后台实验及中英文报告。
- 原生端点与布局检查、器件避障正交布线。
- 原理图导出为 PNG、BMP。
- Windows 安装脚本自动配置 Python 环境及 Codex 或 DeepSeek Harness。

## 系统要求

| 项目 | 版本 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| NI Multisim | 14.2 或 14.3，Windows，32 位 |
| Python | CPython 3.12，32 位；安装脚本自动配置 |
| 通信方式 | STDIO |

## 安装

在 PowerShell 中运行：

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.3.6/install.ps1 | iex
```

重启 Codex，工具列表中会出现 `multisim_native`。

从源码安装：

```powershell
git clone https://github.com/y-wi/multisim-native-mcp.git
cd multisim-native-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

指定 Multisim 安装目录：

```powershell
.\install.ps1 -MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.2'
```

### DeepSeek Harness

从源码目录为 DSH 桌面版安装：

```powershell
.\install.ps1 -Client dsh -Profile desktop
```

其他配置可选择 `-Profile web` 或 `-Profile tui`。安装脚本更新 `cordis.patch.yml`，保留其他插件，并验证 MCP 连接。正在运行的配置会自动热重载连接。

为已有安装配置 DSH，或导出 YAML 补丁：

```powershell
multisim-native-mcp configure --client dsh --profile desktop
multisim-native-mcp config --format dsh
multisim-native-mcp doctor --connect
```

安装脚本会复用兼容的已安装环境。使用 `-Force` 重新安装，或通过 `-ConfigPath` 指定补丁文件。

### 其他 MCP 客户端

使用 `-Client none` 安装并输出 JSON 配置：

```powershell
.\install.ps1 -Client none
```

安装后也可以随时导出配置：

```powershell
& "$env:LOCALAPPDATA\MultisimNativeMCP\bin\multisim-native-mcp.exe" config
```

将输出的 `mcpServers.multisim_native` 项添加到客户端的 MCP 配置中。

### 使用 uv 安装

```powershell
uv tool install --force --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.3.6/multisim_native_mcp-0.3.6-py3-none-any.whl
multisim-native-mcp doctor
multisim-native-mcp configure
```

## 使用

可以直接向 MCP 客户端提出以下需求：

> 新建一个 12 V 电源和两个 1 kΩ 电阻组成的分压电路。连接引脚、检查网表、保存工程并导出 PNG。

> 打开我的 Multisim 工程副本，列出元件和引脚名称，把 R2 改为 2.2 kΩ，另存为一个新工程。

> 移动 R1 并保持导线连接，在输出导线中点添加分支，然后保存并重新打开检查。

### Agent 技能

[multisim-native skill](skills/multisim-native/SKILL.md) 提供能力速查、原生编辑流程和仿真验收方法。可在源码目录中为 Codex 安装：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse .\skills\multisim-native "$env:USERPROFILE\.codex\skills\"
```

设置了 `CODEX_HOME` 时，改用其下的 `skills` 目录。重启 Codex 后，可通过 `$multisim-native` 显式调用，也可由 agent 在 Multisim 任务中自动选用。技能使用已配置的 `multisim_native` MCP 连接。

### 编辑已有工程

1. `native_open_copy`：打开工作副本。
2. `native_list_components`：读取元件引用名和准确的引脚名称。
3. 编辑元件与连接。
4. `native_check_netlist`：检查电气网表。
5. `native_save_copy`：保存新的 `.ms14` 文件。
6. `native_close_copy`：关闭会话。

编辑已有窗口时，使用 `native_attach` 并提供进程 ID。结束附着会话会释放连接，保留该 Multisim 窗口。

### 添加导线分支

1. 使用 `native_list_wires` 读取导线路径。
2. 使用 `native_split_wire` 在导线上创建节点。
3. 使用返回的 `junction_id` 调用 `native_connect_endpoints` 连接分支。

撤销、重做，或网表检查返回 `handles_invalidated: true` 后，重新读取元件和导线 ID。

### 交互仿真

使用 `native_control_interactive` 启动（`start`）、暂停（`pause`）、继续（`resume`）或停止（`stop`）仿真。通过 `native_interactive_status` 读取实际状态、仿真时间和错误；使用 `native_export_interactive_image` 导出 LED 或数码管实际点亮的画面。

对于低频流水灯，先停止仿真，再向 `native_configure_interactive` 传入：

```json
{
  "time_step": 0.001,
  "max_time_step": 0.001,
  "real_time": true
}
```

随后调用 `native_control_interactive`，参数为 `{"action": "start"}`。1 ms 步长可减少求解计算，原生实时节奏让灯光按实际时间切换。较快的信号应使用更小步长，调整后验证频率和输出顺序。

配置对当前会话后续由 MCP 启动的运行生效，保存的 `.ms14` 文件和数值分析设置保持不变。通过 `interactive_options.last_start` 确认实际生效的原生参数。无参数调用 `native_configure_interactive` 读取配置；停止仿真后传入 `{"reset": true}` 恢复软件默认值。

可直接向 agent 提出：

> 用 1 ms 步长和实时节奏运行这个低频流水灯，检查频率和 LED 点亮顺序，再截取一张实际点亮的电路图。

## 工具范围

| 类别 | 操作 |
| --- | --- |
| 会话 | 环境检查、打开副本、新建工程、附着、诊断、关闭 |
| 元件 | 元件库检索、放置、复制、删除、替换、重命名 |
| 参数 | 读取与修改参数、内嵌 SPICE 模型 |
| 布局 | 移动、旋转、镜像、导线布线、添加文字 |
| 连接 | 引脚连接、节点、分支、端点重接、网络标签 |
| 层级 | 多图纸、子电路、层级端口 |
| 历史 | 批量编辑、检查点、撤销、重做 |
| 分析 | 直流工作点、瞬态、AC 扫频、混合波形 |
| 交互仿真 | 启动、暂停、继续、停止、可配置步长、实时节奏、器件显示状态 |
| 测量与验收 | 均值、RMS、频率、占空比、增益、相位、指标约束和数码管解码 |
| 实验 | 扫参、选优、持久后台任务、取消和重试 |
| 报告 | 中英文 HTML、Markdown、CSV、电路图和波形图 |
| 布线检查 | 原生端点、图形边界、正交避障布线 |
| 导出 | 原生 `.ms14`、PNG、BMP、RAW、CSV |

[原理图指南](docs/schematic.md) · [实验指南](docs/experiments.md) · [工具参考](docs/tools.md) · [Python 示例](examples/voltage_divider.py)

## 配置

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim 安装目录 | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | 工作副本和会话产物目录 | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `CODEX_HOME` | Codex 配置目录 | `%USERPROFILE%\.codex` |

运行 `multisim-native-mcp doctor` 检查 Python 位数、安装资源和 Multisim 模块。`configure` 保留其他 Codex 设置，更新已有配置时生成带时间戳的备份。

## 开发

```powershell
uv venv --python cpython-3.12-windows-x86-none
uv pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -m 'not native'
.\.venv\Scripts\python.exe -m pytest -m native
uv build
```

原生集成测试调用已安装的 Multisim。运行前关闭 Multisim。

## 许可证

[MIT 许可证](LICENSE)。
