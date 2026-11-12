# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

Create, edit and simulate editable NI Multisim circuits through the Model Context Protocol.

- **Native circuit editing:** components, named-pin wiring, branches, labels, sheets, subcircuits and embedded SPICE models.
- **Direct file saving:** create a circuit at a chosen path or edit an existing `.ms14` file in place. Normal close saves pending changes; backups and recovery checkpoints are managed automatically.
- **Persistent simulation settings:** configure 19 native analysis profiles and 44 solver options, including time steps, tolerances, integration, convergence, temperature and digital thresholds.
- **Analysis and measurements:** DC operating point, transient and AC sweeps, RAW/CSV output, frequency, duty cycle, gain, phase and numeric criteria.
- **Interactive simulation:** start, pause, resume and stop; configure real-time pacing and export actual LED/display states.
- **Automation and export:** dependent workflows, parameter sweeps, resumable background jobs, PNG/BMP schematics and bilingual reports.

The server provides 77 tools. See the [tool reference](docs/tools.md) for their parameters.

## Requirements

| Component | Requirement |
| --- | --- |
| Operating system | Windows 10 / 11 |
| NI Multisim | 14.3, 32-bit |
| Python | CPython 3.12, 32-bit; the installer sets it up |
| MCP transport | STDIO |

## Install

Run in PowerShell:

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.5.0/install.ps1 | iex
```

Restart Codex to load `multisim_native`. To update an existing installation, download and run the installer with `-Force`:

```powershell
$installer = Join-Path $env:TEMP "multisim-native-install.ps1"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.0/install.ps1" -OutFile $installer
& $installer -Force
```

The installer accepts these options:

| Option | Purpose |
| --- | --- |
| `-MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.3'` | Select a custom Multisim installation |
| `-Client dsh -Profile desktop` | Configure DeepSeek Harness; `web` and `tui` profiles are also supported |
| `-Client none` | Install and print configuration for another MCP client |
| `-ConfigPath <path>` | Select a client configuration file |
| `-Force` | Reinstall the package |

DSH profiles reload the MCP connection automatically. Other clients can use the JSON returned by the installed command:

```powershell
$mcp = Join-Path $env:LOCALAPPDATA "MultisimNativeMCP\bin\multisim-native-mcp.exe"
& $mcp config
& $mcp doctor --connect
```

For source installation, clone this repository and run `.\install.ps1`. To install the wheel directly:

```powershell
uv tool install --force --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.0/multisim_native_mcp-0.5.0-py3-none-any.whl
multisim-native-mcp configure
```

## Agent skill

Install the [multisim-native skill](skills/multisim-native/SKILL.md) for circuit workflows and native simulation guidance:

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $env:USERPROFILE ".codex\skills" }
$skillArchive = Join-Path $env:TEMP "multisim-native-skill-0.5.0.zip"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.0/multisim-native-skill-0.5.0.zip" -OutFile $skillArchive
Expand-Archive -LiteralPath $skillArchive -DestinationPath $skillRoot -Force
```

Restart Codex, then invoke `$multisim-native` or describe a Multisim task. From a source checkout, copy `skills/multisim-native` into the same skills directory.

## Use

Example requests:

> Create a 12 V divider with two 1 kΩ resistors. Save the circuit in the current working directory and export a PNG.

> Open my existing `.ms14` file, change R2 to 2.2 kΩ and save the source file.

> Configure this LED chaser's time steps and real-time pacing, save the settings, and export an actual lit frame.

### Create and save circuits

Supply a complete absolute filename for a new circuit; its parent directory must exist:

```json
{"output_path":"C:/Circuits/divider.ms14","title":"Voltage divider"}
```

Pass that request to `native_create_circuit`. For an existing circuit, call `native_open_circuit` with `source_path`. The server reuses a single running Multisim window when available; `native_attach` selects a specific process and document.

Use `native_save_source` for normal saves. `native_close_copy` saves pending edits before closing an owned session or detaching from an existing window. `native_save_copy(output_path)` performs Save As, while `native_open_copy` creates a separate comparison document. Saving the current document does not require an overwrite flag; replacing another existing file uses `overwrite:true`.

The calling task chooses file locations. The server does not configure a global project directory.

### Save simulation settings

Stop simulation, then call `native_configure_interactive`:

```json
{"time_step":0.001,"max_time_step":0.001,"real_time":true,"save_to_source":true}
```

This saves 1 ms time steps and real-time pacing to the current `.ms14` file. Choose time steps for the circuit's fastest relevant signal. Without `save_to_source`, settings remain in the document until normal save or close; `persist:false` selects temporary session settings.

Use `native_simulation_settings` to discover and edit analysis profiles and solver options. The `interactive` and `analysis` scopes are independent. Numeric analysis accepts `persist:true` to retain run settings, or `use_saved_settings:true` to execute saved OP/AC/TRAN settings. See [simulation settings and persistence](docs/persistence.md).

### Workflows and long runs

`native_run_workflow` combines editing, analysis, numeric criteria, saving and export. Read progress with `native_workflow_status`; cancel or resume with `native_control_workflow`. Individual analysis jobs use `native_start_analysis`, `native_analysis_status` and `native_control_analysis`.

Workflows have no default runtime deadline. `max_runtime` sets an optional deadline; status waits only control when a response returns. Editing batches, sample counts and export sizes have no MCP workload quotas; native data formats and available resources determine capacity. Client request timeouts are configured by the client.

[Workflow guide](docs/workflows.md) · [Complete divider request](skills/multisim-native/assets/workflow_divider.json) · [Python example](examples/voltage_divider.py)

## Guides

- [Circuit editing, wiring and export](docs/schematic.md)
- [Simulation settings and persistence](docs/persistence.md)
- [Measurements, sweeps and reports](docs/experiments.md)
- [All tools](docs/tools.md)

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim installation directory | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | Recovery files and session artifacts | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `MULTISIM_NATIVE_IO_DIR` | Optional ASCII directory for legacy SPICE file transfers | System temporary directory |
| `CODEX_HOME` | Codex configuration directory | `%USERPROFILE%\.codex` |

## License

[MIT](LICENSE).
