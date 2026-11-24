# Multisim Native MCP

[English](README.md) · 简体中文

Multisim Native MCP 将 AI 助手连接到 Windows 上的 NI Multisim。可搭建和修改原理图（包含最右侧仪器栏全部 19 种原生虚拟仪器）、运行原生仿真，并将设计保存为可在 Multisim 中继续编辑的 `.ms14` 文件。

## v0.5.4 更新

- **自动配置客户端。** Windows 安装器可检测已安装的 MCP 客户端、注册服务，并同步内置的 Multisim 技能。
- **内置技能和示例。** 提供常用器件引脚与参数速查，以及分压、RC 滤波和实时显示读数的工作流模板。客户端也可以通过 MCP 资源读取技能文档。
- **信号解析与网络命名。** 波形工作流在拓扑刷新后重新匹配元件 ID，设置导线网络名时会检查跨图纸命名冲突。

[发行下载](https://github.com/y-wi/multisim-native-mcp/releases/tag/v0.5.4) · [更新日志](CHANGELOG.md)

## 安装（一条命令自动识别 Harness 并安装 Skill）

| 项目 | 要求 |
| --- | --- |
| Windows | Windows 10 或 11 |
| NI Multisim | 14.3，32 位 |
| Python | CPython 3.12，32 位，由 `install.ps1` 自动安装 |
| MCP 通信方式 | STDIO |

在 PowerShell 中下载并运行安装脚本。默认使用 `-Client auto`：自动安装 32 位运行时、执行 `doctor --connect` 验证、检测本机已安装的 AI Harness、注册 `multisim_native` 并自动安装/更新内置的 `multisim-native` Skill：

```powershell
$installer = Join-Path $env:TEMP 'multisim-native-install.ps1'
Invoke-WebRequest 'https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.4/install.ps1' -OutFile $installer
& $installer
```

在本地源码仓库目录直接运行 `.\install.ps1` 即可从本地安装或升级。

### 支持的 Harness 与安装参数

如需指定单个或多个客户端（支持逗号分隔，如 `-Client antigravity,claude-code`），传入 `-Client` 即可：

| Harness / 选项 | 安装参数 | 默认 MCP 配置路径 | 默认 Agent Skill 路径 |
| --- | --- | --- | --- |
| 自动检测全部已装客户端（默认） | `-Client auto` | 自动配置下方已检测项（均未检测到时回退 `codex`） | 同步写入各已检测客户端的 Skill 目录 |
| Antigravity | `-Client antigravity` | `~/.gemini/config/mcp_config.json`（兼容旧路径） | `~/.gemini/config/skills/multisim-native` |
| OpenAI Codex | `-Client codex` | `~/.codex/config.toml`（支持 `$CODEX_HOME`） | `~/.codex/skills/multisim-native` |
| Claude Code | `-Client claude-code` | `~/.claude.json` | `~/.claude/skills/multisim-native` |
| Claude Desktop | `-Client claude-desktop` | `%APPDATA%\Claude\claude_desktop_config.json` | 通过 MCP Resource（`multisim://skill/SKILL.md`）提供 |
| Cursor | `-Client cursor` | `~/.cursor/mcp.json` | `~/.cursor/skills/multisim-native` |
| Windsurf | `-Client windsurf` | `~/.codeium/windsurf/mcp_config.json` | `~/.codeium/windsurf/skills/multisim-native` |
| Gemini CLI | `-Client gemini-cli` | `~/.gemini/settings.json` | `~/.gemini/skills/multisim-native` |
| VS Code（原生 MCP） | `-Client vscode` | `%APPDATA%\Code\User\mcp.json`（`servers` 键） | `~/.copilot/skills/multisim-native` |
| GitHub Copilot CLI | `-Client copilot` | `~/.copilot/mcp-config.json` | `~/.copilot/skills/multisim-native` |
| OpenCode | `-Client opencode` | `~/.config/opencode/opencode.json` 或 `%APPDATA%\opencode\opencode.json`（`mcp` 键） | `~/.config/opencode/skills/multisim-native` |
| DeepSeek Harness | `-Client dsh -Profile desktop` | `~/.dsh/profiles/<profile>/cordis.patch.yml` | 可通过 `-SkillDir` 指定 |
| 跨工具项目级标准 | `-Client project -ProjectDir <dir>` | `<dir>\.mcp.json` | `<dir>\.agents\skills\multisim-native` |
| 标准 JSON MCP 客户端 | `-Client json -ConfigPath <path>` | `<path>`（`mcpServers` 键） | 可通过 `-SkillDir` 指定 |
| 仅输出配置不改文件 | `-Client none` | 打印到标准输出 | 可通过 `-SkillDir` 指定 |

常用附加开关：`-SkipSkill`（跳过 Skill 安装）、`-SkillDir <dir>`（自定义 Skill 目录）、`-MultisimPath <dir>`（自定义 Multisim 安装目录）、`-Force`（强制重装同版本）、`-SkipDoctor`（跳过连接校验）。

### 让用户的 Agent 自动完成配置

任何具备终端执行能力的 Agent 都可以直接调用 CLI 完成检测与配置：

```powershell
# 查看本机已检测到的 Harness 及其配置/Skill 路径
multisim-native-mcp clients

# 自动配置所有已检测到的 Harness 并同步 Skill
multisim-native-mcp configure --client auto

# 仅同步内置 Skill（支持通用的 ~/.agents/skills 标准目录）
multisim-native-mcp install-skill --client auto
multisim-native-mcp install-skill --client agents

# 导出任意格式配置片段（json / codex / dsh / vscode / opencode）
multisim-native-mcp config --format json

# 清理旧版本安装环境与过期会话缓存
multisim-native-mcp cleanup
```

配置完成后重启客户端或在 Antigravity 中重载 MCP 服务即可生效，服务名为 `multisim_native`。

## 通用 Agent 技能与 MCP Resource 兜底

`multisim-native` 遵循开放的 [Agent Skills (`SKILL.md`) 规范](https://agentskills.io/)，且已直接打包进 wheel，**无需额外下载独立 zip**，安装和升级始终与 MCP 版本保持一致：

- [SKILL.md](skills/multisim-native/SKILL.md) — 工作流优先策略与 Multisim 避坑要点
- [references/editing.md](skills/multisim-native/references/editing.md) — Multisim 14.3 实机核对的 22 种常用器件引脚/命名参数/跨距速查表及 19 种虚拟仪器端口与设置速查
- [references/workflows.md](skills/multisim-native/references/workflows.md) 与 [references/analysis.md](skills/multisim-native/references/analysis.md)
- `skills/multisim-native/assets/` 内置可直接改写的分压电路、RC 低通滤波（AC/Bode）、交互式数码管/LED 模板

对于不支持本地 `SKILL.md` 目录的客户端（如 Claude Desktop 或自定义 MCP 宿主），服务端同时通过标准 MCP Resource 暴露完整文档（`multisim://skill/SKILL.md`、`multisim://skill/references/editing.md`、`multisim://skill/references/workflows.md`、`multisim://skill/references/analysis.md`），确保跨 Harness 开箱即用。

## 虚拟仪器（右侧仪器栏）

Multisim 最右侧仪器栏中的示波器、函数发生器、万用表等属于原生插件仪器，不在一般元件库（Master Database）中。Multisim Native MCP 通过 Multisim 官方 C++ API 直接原生支持全部 **19** 种仪器（零界面模拟点击、零硬编码地址偏移、零 `.ms14` 二进制修补），完整支持撤销/重做、批处理与工作流、实时交互读数、波形数据导出以及保存回读校验：

| 分类 | 支持的虚拟仪器（参考号前缀） | 核心能力 |
| --- | --- | --- |
| 模拟表计与信号源 | 万用表（`XMM`）、函数发生器（`XFG`）、功率表（`XWM`）、电流探针（`XCP`） | 友好模式/波形/频率/幅值/变比设置；`XMM`/`XWM` 实时交互读数；切换万用表模式自动更新 SPICE 内阻 |
| 时域与频域示波仪器 | 双通道示波器（`XSC`）、四通道示波器（`XSC`）、波特图仪（`XBP`）、频率计（`XFC`） | 时基、各通道量程/耦合/偏移、触发及扫频参数配置；原生导出 `.scp`（示波器）与 `.bod`（波特图仪）数据 |
| 数字与射频分析仪 | 字信号发生器（`XWG`）、逻辑转换仪（`XLC`）、逻辑分析仪（`XLA`）、伏安特性分析仪（`XIV`）、失真分析仪（`XDA`）、频谱分析仪（`XSA`）、网络分析仪（`XNA`） | 友好参数 + 原始 `NI_EWB_*` 嵌套属性路径读写；`XDA` 实时交互读数 |
| 实机面板仪器 | 安捷伦 33120A（`XFG`）、安捷伦 34401A（`XMM`）、安捷伦 54622D（`XSC`）、泰克 TDS 2024（`XSC`） | 原生放置、引脚映射、面板/通道参数设置与 `34401A` 实时读数 |

专用 MCP 工具（同样可在 `native_edit_batch` 和 `native_run_workflow` 中以 `place_instrument` / `set_instrument_settings` 调用；使用 `native_search_library` 搜索仪器名时也会自动给出仪器提示）：

- `native_list_instruments(query)` — 支持中英文名、别名、参考号前缀检索全部 19 种虚拟仪器，查看端口引脚、友好设置项、DLL 状态及当前图纸已放置仪器。
- `native_place_instrument(instrument, x, y, ..., settings)` — 原生放置任意仪器栏虚拟仪器，并可在同一次可撤销事务中写入初始参数。
- `native_get_instrument_settings(component_ref, include_raw)` / `native_set_instrument_settings(component_ref, settings, include_raw)` — 通过友好参数名或原始 `NI_EWB_*` 嵌套路径读写配置，自动回读验证并持久保存到 `.ms14`。
- `native_export_instrument_data(component_ref, output_path, overwrite)` — 在交互仿真采集后原生导出示波器 `.scp` 或波特图仪 `.bod` 波形数据文件。

调用示例（`native_place_instrument` 与 `native_set_instrument_settings`）：

```json
{
  "instrument": "function_generator",
  "x": 180,
  "y": 180,
  "reference": "XFG1",
  "settings": {
    "waveform": "square",
    "frequency_hz": 1000,
    "amplitude_vp": 5,
    "duty_cycle_pct": 40,
    "offset_v": 2.5
  }
}
```

```json
{
  "component_ref": "XSC1",
  "settings": {
    "timebase_scale_s_per_div": 0.0005,
    "channel_a_scale_v_per_div": 2,
    "channel_a_coupling": "DC",
    "trigger_edge": "rising",
    "trigger_level_v": 2.5
  }
}
```

交互仿真期间调用 `native_interactive_status(include_displays=true)` 即可与数码管、LED 一同读取实时 `instrument_readouts`。更多说明见[原理图编辑 — 虚拟仪器](docs/schematic.md#virtual-instruments--虚拟仪器右侧仪器栏)与[MCP 工具参考](docs/tools.md)。

## 通过助手操作 Multisim

> 用 10 V 电源和两个 1 kΩ 电阻搭建分压电路。将电源从 0 V 扫到 10 V，把中点电压导出为 CSV，并保存为 `divider.ms14`。

> 放置一个函数发生器（1 kHz、5 Vp 方波）、双通道示波器（500 µs/div、通道 A 2 V/div 直流耦合）和直流电压表接到 1 kΩ 负载上；启动交互仿真，读取万用表实时读数、导出示波器 `.scp` 波形，并保存为 `scope_demo.ms14`。

> 打开我的放大器电路，运行交流分析，将输出相对输入的伯德图导出为 PNG。

> 启动计数器的交互仿真，在十六进制数码管显示 A 时导出一张原理图，并告诉我哪些 LED 点亮了。

使用 `native_create_circuit` 和完整的输出路径创建电路，或使用 `native_open_circuit` 打开已有设计。修改后通过 `native_save_source` 保存。[Python 分压电路示例](examples/voltage_divider.py)

使用 `native_run_workflow` 串联原理图编辑、图纸切换、仿真、验收和导出。通过 `native_workflow_status` 查询进度，通过 `native_control_workflow` 取消或续跑。[工作流指南](docs/workflows.md)

## 文档

- [原理图编辑、连线与导出](docs/schematic.md)
- [仿真设置与持久保存](docs/persistence.md)
- [测量、扫描与报告](docs/experiments.md)
- [MCP 工具参考](docs/tools.md)
- [GitHub Issues](https://github.com/y-wi/multisim-native-mcp/issues)

[MIT 许可证](LICENSE)
