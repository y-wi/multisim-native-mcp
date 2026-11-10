# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

通过 Model Context Protocol 编辑 NI Multisim 原生电路并执行模拟电路分析。

- 44 个 MCP 工具，涵盖元件、连线、图纸、子电路、模型与分析。
- 生成可编辑的 `.ms14` 工程，支持按引脚名称连接和导线分支。
- 支持批量编辑、检查点、撤销、重做和原生保存重开。
- 模拟电路直流工作点、瞬态分析，导出 RAW 与 CSV 数据。
- 原理图导出为 PNG、BMP。
- Windows 安装脚本自动配置 Python 环境和 Codex。

## 系统要求

| 项目 | 版本 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| NI Multisim | 14.2 或 14.3，Windows，32 位 |
| Python | CPython 3.12，32 位；安装脚本自动配置 |
| 通信方式 | STDIO |

Multisim 14.2 与 14.3 使用同一套私有原生对象模型，两者都受支持：元件与连线编辑、网表生成、直流工作点与瞬态分析、原生 `.ms14` 保存和图像导出在任一版本上均可用。`native-profile.json` 中的 14.3 模块哈希仅作诊断参考，因此 14.2 安装会报告 `compatible: false`，但不影响正常使用。非默认 14.3 目录的安装请在安装时用 `-MultisimPath` 指定（见[安装](#安装)）。

## 安装

在 PowerShell 中运行：

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.2.2/install.ps1 | iex
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
uv tool install --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.2.2/multisim_native_mcp-0.2.2-py3-none-any.whl
multisim-native-mcp doctor
multisim-native-mcp configure
```

## 使用

可以直接向 MCP 客户端提出以下需求：

> 新建一个 12 V 电源和两个 1 kΩ 电阻组成的分压电路。连接引脚、检查网表、保存工程并导出 PNG。

> 打开我的 Multisim 工程副本，列出元件和引脚名称，把 R2 改为 2.2 kΩ，另存为一个新工程。

> 移动 R1 并保持导线连接，在输出导线中点添加分支，然后保存并重新打开检查。

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
| 模拟分析 | 直流工作点、瞬态分析、波形数据 |
| 导出 | 原生 `.ms14`、PNG、BMP、RAW、CSV |

[工具参考](docs/tools.md) · [Python 示例](examples/voltage_divider.py)

## 配置

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim 安装目录 | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | 工作副本和会话产物目录 | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `CODEX_HOME` | Codex 配置目录 | `%USERPROFILE%\.codex` |

运行 `multisim-native-mcp doctor` 检查 Python 位数、安装资源和 Multisim 模块。`configure` 保留其他 Codex 设置，更新已有配置时生成带时间戳的备份。

模块哈希和参考版本用于诊断。启动、进程附着和安装就绪状态依据运行环境是否存在判断。

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

[FSF All-Permissive License](LICENSE)。
