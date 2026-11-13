# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

An MCP server for creating, editing and simulating native NI Multisim circuits from an AI assistant. Circuits remain editable `.ms14` files that open directly in Multisim.

- **Build and edit circuits:** place library components, connect pins and junctions, route wires, edit annotations, and manage sheets, subcircuits and hierarchical ports.
- **Save designs and settings:** edit existing files in place and retain component values, embedded SPICE models, sheet properties and simulation configuration.
- **Run native analysis:** DC operating point, transient and AC analysis, with RAW/CSV results, waveform measurements and parameter sweeps.
- **Control interactive simulation:** start, pause, resume and stop simulation, set real-time pacing, and capture actual LED and display states.
- **Automate complete tasks:** combine edits, analysis, measurements, saves and schematic exports in resumable workflows.

## What's new in 0.5.1

- Edit and delete free text; update sheet properties, hierarchical ports and branch junctions.
- Save hierarchical circuits correctly after deleting connected ports, including after undo and redo.
- Use consistent selectors across individual tools, edit batches and workflows, with concise parameter responses.
- Receive object ID mappings after document refreshes and detailed field differences when save verification fails.

See the [changelog](CHANGELOG.md) for all changes.

## Requirements

| Component | Requirement |
| --- | --- |
| Operating system | Windows 10 / 11 |
| NI Multisim | 14.3, 32-bit |
| Python | CPython 3.12, 32-bit; the installer sets it up |
| MCP transport | STDIO |

## Install

Run in PowerShell to install the server and configure Codex:

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.5.1/install.ps1 | iex
```

The installer sets up the required 32-bit Python environment and package dependencies. Restart Codex to load `multisim_native`.

To update an existing installation, download and run the installer with `-Force`:

```powershell
$installer = Join-Path $env:TEMP "multisim-native-install.ps1"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/install.ps1" -OutFile $installer
& $installer -Force
```

For DeepSeek Harness, run the downloaded installer with the target profile:

```powershell
& $installer -Client dsh -Profile desktop
```

### Installation options

| Option | Purpose |
| --- | --- |
| `-MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.3'` | Select a custom Multisim installation |
| `-Client dsh -Profile desktop` | Configure DeepSeek Harness; `web` and `tui` profiles are also supported |
| `-Client none` | Install and print configuration for another MCP client |
| `-ConfigPath <path>` | Select a client configuration file |
| `-Force` | Reinstall the package |

DSH profiles reload the MCP connection automatically. For another MCP client, use `-Client none` and copy the JSON printed by the installer into that client's server configuration.

Check the installation and MCP connection:

```powershell
$mcp = Join-Path $env:LOCALAPPDATA "MultisimNativeMCP\bin\multisim-native-mcp.exe"
& $mcp doctor --connect
```

For source installation, clone this repository and run `.\install.ps1`. The [release page](https://github.com/y-wi/multisim-native-mcp/releases/tag/v0.5.1) also provides a wheel, source archive and `SHA256SUMS`.

## Agent skill

The optional [multisim-native skill](skills/multisim-native/SKILL.md) gives the assistant circuit editing and native simulation guidance. Install it for Codex with:

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $env:USERPROFILE ".codex\skills" }
$skillArchive = Join-Path $env:TEMP "multisim-native-skill-0.5.1.zip"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.5.1/multisim-native-skill-0.5.1.zip" -OutFile $skillArchive
Expand-Archive -LiteralPath $skillArchive -DestinationPath $skillRoot -Force
```

Restart Codex, then invoke `$multisim-native` or describe a Multisim task. For another skill-enabled client, extract the archive into its skills directory, keeping the `multisim-native` folder. From a source checkout, copy `skills/multisim-native` instead.

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

Choose file locations in each request. Recovery backups and checkpoints are managed automatically.

### Save simulation settings

Stop simulation, then call `native_configure_interactive`:

```json
{"time_step":0.001,"max_time_step":0.001,"real_time":true,"save_to_source":true}
```

This saves 1 ms time steps and real-time pacing to the current `.ms14` file. Choose time steps for the circuit's fastest relevant signal. Without `save_to_source`, settings remain in the document until normal save or close; `persist:false` selects temporary session settings.

Use `native_simulation_settings` to discover and edit analysis profiles and solver options. The `interactive` and `analysis` scopes are independent. Numeric analysis accepts `persist:true` to retain run settings, or `use_saved_settings:true` to execute saved OP/AC/TRAN settings. See [simulation settings and persistence](docs/persistence.md).

### Workflows and long runs

`native_run_workflow` combines editing, analysis, numeric criteria, saving and export. Read progress with `native_workflow_status`; cancel or resume with `native_control_workflow`. Individual analysis jobs use `native_start_analysis`, `native_analysis_status` and `native_control_analysis`.

Long runs continue in the background while the client reads progress. Workflows have no default runtime deadline; set `max_runtime` when a deadline is needed.

[Workflow guide](docs/workflows.md) · [Complete divider request](skills/multisim-native/assets/workflow_divider.json) · [Python example](examples/voltage_divider.py)

## Guides

- [Circuit editing, wiring and export](docs/schematic.md)
- [Simulation settings and persistence](docs/persistence.md)
- [Measurements, sweeps and reports](docs/experiments.md)
- [All tools](docs/tools.md)

The tool reference covers preferred connection and deletion tools, batch selectors, full parameter reads and object ID mappings. Existing tool aliases remain compatible.

## Troubleshooting

- **Multisim is not found:** rerun the installer with `-MultisimPath` pointing to the directory containing `Multisim.exe`.
- **The client does not list the server:** restart or reconnect the client, then run `doctor --connect` using the command above.
- **An operation fails:** use the returned error details to identify the affected object or setting. Save-verification errors include the differing fields and a diagnostic file path.

Report reproducible issues through [GitHub Issues](https://github.com/y-wi/multisim-native-mcp/issues).

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim installation directory | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | Recovery files and session artifacts | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `MULTISIM_NATIVE_IO_DIR` | Optional ASCII directory for legacy SPICE file transfers | System temporary directory |
| `CODEX_HOME` | Codex configuration directory | `%USERPROFILE%\.codex` |

## License

[MIT](LICENSE).
