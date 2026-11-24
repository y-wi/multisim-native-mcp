# Multisim Native MCP

English · [简体中文](README.zh-CN.md)

Multisim Native MCP connects an AI assistant to NI Multisim on Windows. Build and edit schematics—including all 19 native right-hand Instruments toolbar virtual instruments—run native simulations, and save designs as editable `.ms14` files.

## What's new in v0.5.4

- **Automatic client setup.** The Windows installer detects installed MCP clients, registers the server, and syncs the bundled Multisim skill.
- **Bundled skill and examples.** Look up common component pins and parameters, and adapt workflow templates for voltage dividers, RC filters, and live indicators. Clients can also read the guides through MCP resources.
- **Signal resolution and net names.** Waveform workflows recover component IDs after topology refreshes, and wire labels are checked for naming conflicts across sheets.

[Release downloads](https://github.com/y-wi/multisim-native-mcp/releases/tag/v0.5.4) · [Changelog](CHANGELOG.md)

## Install (one command, auto-detects harnesses + installs skill)

| Component | Requirement |
| --- | --- |
| Windows | Windows 10 or 11 |
| NI Multisim | 14.3, 32-bit |
| Python | CPython 3.12, 32-bit, installed automatically by `install.ps1` |
| MCP transport | STDIO |

Run the installer in PowerShell. By default (`-Client auto`), it installs the runtime, verifies `doctor --connect`, detects all installed AI harnesses on this machine, registers `multisim_native`, and installs/updates the bundled `multisim-native` Agent Skill automatically:

```powershell
$installer = Join-Path $env:TEMP 'multisim-native-install.ps1'
Invoke-WebRequest 'https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.4/install.ps1' -OutFile $installer
& $installer
```

From a local source checkout, simply run `.\install.ps1`. Re-run the same script to update or sync a new harness.

### Supported harnesses & installer options

Pass `-Client` explicitly (single harness or comma-separated list such as `-Client antigravity,claude-code`) when you want to target specific harnesses:

| Harness / option | Installer argument | Default MCP config path | Default Agent Skill path |
| --- | --- | --- | --- |
| Auto-detect installed harnesses (default) | `-Client auto` | All detected below (falls back to `codex`) | Matching skill dir for each detected harness |
| Antigravity | `-Client antigravity` | `~/.gemini/config/mcp_config.json` (legacy fallback) | `~/.gemini/config/skills/multisim-native` |
| OpenAI Codex | `-Client codex` | `~/.codex/config.toml` (`$CODEX_HOME`) | `~/.codex/skills/multisim-native` |
| Claude Code | `-Client claude-code` | `~/.claude.json` | `~/.claude/skills/multisim-native` |
| Claude Desktop | `-Client claude-desktop` | `%APPDATA%\Claude\claude_desktop_config.json` | Uses MCP resources (`multisim://skill/SKILL.md`) |
| Cursor | `-Client cursor` | `~/.cursor/mcp.json` | `~/.cursor/skills/multisim-native` |
| Windsurf | `-Client windsurf` | `~/.codeium/windsurf/mcp_config.json` | `~/.codeium/windsurf/skills/multisim-native` |
| Gemini CLI | `-Client gemini-cli` | `~/.gemini/settings.json` | `~/.gemini/skills/multisim-native` |
| VS Code (native MCP) | `-Client vscode` | `%APPDATA%\Code\User\mcp.json` (`servers`) | `~/.copilot/skills/multisim-native` |
| GitHub Copilot CLI | `-Client copilot` | `~/.copilot/mcp-config.json` | `~/.copilot/skills/multisim-native` |
| OpenCode | `-Client opencode` | `~/.config/opencode/opencode.json` or `%APPDATA%\opencode\opencode.json` (`mcp`) | `~/.config/opencode/skills/multisim-native` |
| DeepSeek Harness | `-Client dsh -Profile desktop` | `~/.dsh/profiles/<profile>/cordis.patch.yml` | Optional via `-SkillDir` |
| Portable workspace setup | `-Client project -ProjectDir <dir>` | `<dir>\.mcp.json` | `<dir>\.agents\skills\multisim-native` |
| Standard JSON MCP client | `-Client json -ConfigPath <path>` | `<path>` (`mcpServers`) | Optional via `-SkillDir` |
| Print config without modifying files | `-Client none` | Printed to stdout | Optional via `-SkillDir` |

Additional switches: `-SkipSkill` (MCP only), `-SkillDir <dir>` (custom skill root), `-MultisimPath <dir>` (custom Multisim folder), `-Force` (reinstall same version), `-SkipDoctor` (skip connection test).

### Let your AI agent configure itself

Any terminal-capable AI agent can inspect or configure your harnesses directly via the installed CLI:

```powershell
# Inspect detected harnesses and paths
multisim-native-mcp clients

# Configure MCP + sync bundled skill for one or all detected harnesses
multisim-native-mcp configure --client auto

# Sync only the bundled skill (including cross-agent ~/.agents/skills)
multisim-native-mcp install-skill --client auto
multisim-native-mcp install-skill --client agents

# Print config snippet for manual or custom harnesses (json, codex, dsh, vscode, opencode)
multisim-native-mcp config --format json

# Clean up old installed environments and expired session caches
multisim-native-mcp cleanup
```

Reload MCP servers (or restart your harness) after configuration. The server appears as `multisim_native`.

## Universal Agent Skill & MCP Resources

The `multisim-native` skill follows the open [Agent Skills (`SKILL.md`) specification](https://agentskills.io/) and is bundled directly inside the package wheel—no separate download is required. It includes:

- [SKILL.md](skills/multisim-native/SKILL.md) — workflow-first guidance and native Multisim pitfalls
- [references/editing.md](skills/multisim-native/references/editing.md) — verified Multisim 14.3 22-part pin/parameter/spacing cheat sheet and 19-instrument terminal & settings reference
- [references/workflows.md](skills/multisim-native/references/workflows.md) & [references/analysis.md](skills/multisim-native/references/analysis.md)
- Ready-to-adapt templates in `skills/multisim-native/assets/` (voltage divider, RC AC filter, interactive indicators)

For harnesses that do not read local `SKILL.md` directories (such as Claude Desktop or custom MCP hosts), the server also exposes the same guides as MCP resources (`multisim://skill/SKILL.md`, `multisim://skill/references/editing.md`, `multisim://skill/references/workflows.md`, `multisim://skill/references/analysis.md`).

## Virtual instruments (Instruments toolbar)

Multisim's right-hand Instruments toolbar devices are native snap-in instruments rather than Master Database library parts. Multisim Native MCP supports all **19** active toolbar instruments directly through Multisim's official C++ APIs (no GUI clicking, no hardcoded RVAs, no `.ms14` binary patching), with full undo/redo, batch/workflow execution, live interactive readouts, trace export, and native save-reopen verification:

| Category | Supported instruments (RefDes) | Highlights |
| --- | --- | --- |
| Analog meters & sources | Multimeter (`XMM`), Function Generator (`XFG`), Wattmeter (`XWM`), Current Probe (`XCP`) | Friendly mode/waveform/frequency/amplitude/ratio settings; live `XMM`/`XWM` interactive readouts; automatic SPICE impedance update on meter mode switch |
| Time & frequency scopes | 2-Ch Oscilloscope (`XSC`), 4-Ch Oscilloscope (`XSC`), Bode Plotter (`XBP`), Frequency Counter (`XFC`) | Timebase, per-channel scale/coupling/offset, trigger & sweep settings; native `.scp` (scope) and `.bod` (Bode) trace export |
| Digital & RF analyzers | Word Generator (`XWG`), Logic Converter (`XLC`), Logic Analyzer (`XLA`), IV Analyzer (`XIV`), Distortion Analyzer (`XDA`), Spectrum Analyzer (`XSA`), Network Analyzer (`XNA`) | Friendly settings + raw `NI_EWB_*` property paths (including nested maps/arrays); live `XDA` interactive readout |
| Benchtop instruments | Agilent 33120A (`XFG`), Agilent 34401A (`XMM`), Agilent 54622D (`XSC`), Tektronix TDS 2024 (`XSC`) | Native benchtop placement, pin maps, front-panel/channel settings, and live `34401A` readouts |

Dedicated MCP tools (also accepted in `native_edit_batch` and `native_run_workflow` as `place_instrument` and `set_instrument_settings`; `native_search_library` also hints matching toolbar instruments):

- `native_list_instruments(query)` — search all 19 instruments by English/Chinese name, alias, or RefDes; inspect pins, friendly settings, DLL availability, and placed instances.
- `native_place_instrument(instrument, x, y, ..., settings)` — place any toolbar instrument natively and optionally configure its initial settings in one undoable edit.
- `native_get_instrument_settings(component_ref, include_raw)` / `native_set_instrument_settings(component_ref, settings, include_raw)` — read and update friendly settings (or raw `NI_EWB_*` nested paths) with readback verification and `.ms14` persistence.
- `native_export_instrument_data(component_ref, output_path, overwrite)` — export captured `.scp` (2-Ch/4-Ch Oscilloscope) or `.bod` (Bode Plotter) waveform files after interactive simulation.

Example (`native_place_instrument` + `native_set_instrument_settings`):

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

During interactive simulation, call `native_interactive_status(include_displays=true)` to inspect live `instrument_readouts` alongside LEDs and seven-segment displays. See [Schematic editing — Virtual instruments](docs/schematic.md#virtual-instruments--虚拟仪器右侧仪器栏) and [Tool reference](docs/tools.md).

## Use Multisim from your assistant

> Create a 10 V divider with two 1 kΩ resistors. Sweep the supply from 0 to 10 V, export the midpoint voltage as CSV, and save the circuit as `divider.ms14`.

> Place a Function Generator (1 kHz, 5 Vp square wave), a 2-Ch Oscilloscope (500 µs/div, Ch A 2 V/div DC), and a DC Voltmeter across a 1 kΩ load. Run interactive simulation, read the live multimeter value, export the scope `.scp` waveform, and save as `scope_demo.ms14`.

> Open my amplifier circuit, run an AC analysis, and export a PNG Bode plot of the output relative to the input.

> Start interactive simulation on my counter circuit. Capture a schematic image when the hexadecimal display shows A, and report which LEDs are lit.

Use `native_create_circuit` with a full output path to create a design, or `native_open_circuit` with the source path to open an existing design. Save changes with `native_save_source`. [Python voltage-divider example](examples/voltage_divider.py)

For multi-step tasks, `native_run_workflow` combines schematic edits, sheet selection, analysis, acceptance criteria and exports. Use `native_workflow_status` to check progress and `native_control_workflow` to cancel or resume. [Workflow guide](docs/workflows.md)

## Documentation

- [Schematic editing, wiring and export](docs/schematic.md)
- [Simulation settings and persistence](docs/persistence.md)
- [Measurements, sweeps and reports](docs/experiments.md)
- [MCP tool reference](docs/tools.md)
- [GitHub Issues](https://github.com/y-wi/multisim-native-mcp/issues)

[MIT License](LICENSE)
