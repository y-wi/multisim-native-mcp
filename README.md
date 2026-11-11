# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

Native circuit editing, simulation and experiment verification for NI Multisim through the Model Context Protocol.

- Typed workflows with result bindings, native acceptance, recovery and artifact delivery.
- 77 MCP tools for components, wires, sheets, subcircuits, models and analysis.
- Persistent native simulation settings, solver options and verified saves back to the source file; see [persistence ownership](docs/persistence.md).
- Interactive simulation with configurable time steps, real-time pacing and actual display captures.
- Editable `.ms14` projects with named-pin connections and routed wire branches.
- Batch edits, checkpoints, undo, redo and native save/reopen.
- DC operating point, transient and AC analysis with RAW and CSV output.
- Time-weighted measurements, numeric acceptance checks and scanned display decoding.
- Parameter sweeps, candidate ranking, persistent background experiments and bilingual reports.
- Native automatic wiring, rerouting on move, touching-pin connections and layout checks.
- Schematic export to PNG and BMP.
- Windows installer with automatic Python setup and Codex or DeepSeek Harness configuration.

## Requirements

| Component | Version |
| --- | --- |
| Operating system | Windows 10 / 11 |
| NI Multisim | 14.3, Windows, 32-bit |
| Python | CPython 3.12, 32-bit; installed automatically |
| Transport | STDIO |

## Install

Run in PowerShell:

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.4.0/install.ps1 | iex
```

Restart Codex. The server appears as `multisim_native`.

To install from source:

```powershell
git clone https://github.com/y-wi/multisim-native-mcp.git
cd multisim-native-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

For a custom Multisim installation directory:

```powershell
.\install.ps1 -MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.3'
```

### DeepSeek Harness

From a source checkout, install for DSH Desktop:

```powershell
.\install.ps1 -Client dsh -Profile desktop
```

Use `-Profile web` or `-Profile tui` for other profiles. The installer updates `cordis.patch.yml`, preserves other plugins, and verifies the MCP connection. Active profiles reload the connection automatically.

Configure an existing installation or export its YAML patch:

```powershell
$mcp = Join-Path $env:LOCALAPPDATA "MultisimNativeMCP\bin\multisim-native-mcp.exe"
& $mcp configure --client dsh --profile desktop
& $mcp config --format dsh
& $mcp doctor --connect
```

The installer reuses a compatible installed environment. Use `-Force` to reinstall, or `-ConfigPath` to select a patch file.

### Other MCP clients

Install with `-Client none` to print the JSON configuration:

```powershell
.\install.ps1 -Client none
```

The installed command also exports client configuration:

```powershell
& "$env:LOCALAPPDATA\MultisimNativeMCP\bin\multisim-native-mcp.exe" config
```

Add the resulting `mcpServers.multisim_native` entry to your client's MCP configuration.

### Install with uv

```powershell
uv tool install --force --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.4.0/multisim_native_mcp-0.4.0-py3-none-any.whl
$mcp = Join-Path (uv tool dir --bin) "multisim-native-mcp.exe"
& $mcp doctor
& $mcp configure
```

## Use

Start with one of these requests in your MCP client:

> Create a 12 V voltage divider with two 1 kΩ resistors. Connect the named pins, check the netlist, save the circuit and export a PNG.

> Open a copy of my Multisim project. List the components and pin names, replace R2 with 2.2 kΩ and save a new project.

> Move R1 and keep its wires attached. Add a branch at the midpoint of the output wire, then save with native readback verification.

### Circuit workflows

For complete tasks, submit one `native_run_workflow` plan with dependent edits, analysis criteria, save and export stages. The server resolves intermediate objects and waits locally. Use `native_workflow_status` with a nonzero wait for long jobs, and resume an unfinished tail with `native_control_workflow`. Single-step tools remain available for local adjustments.

See [workflows](docs/workflows.md) and the complete [divider request](skills/multisim-native/assets/workflow_divider.json).

### Agent skill

The [multisim-native skill](skills/multisim-native/SKILL.md) gives agents staged workflows, result bindings and simulation verification guidance. Install the release package for Codex:

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $env:USERPROFILE ".codex\skills" }
$skillArchive = Join-Path $env:TEMP "multisim-native-skill-0.4.0.zip"
Invoke-WebRequest "https://github.com/y-wi/multisim-native-mcp/releases/download/v0.4.0/multisim-native-skill-0.4.0.zip" -OutFile $skillArchive
Expand-Archive -LiteralPath $skillArchive -DestinationPath $skillRoot -Force
```

From a source checkout, copy `skills/multisim-native` into the same skills directory. Restart Codex to discover the skill. Invoke it explicitly as `$multisim-native`, or let the agent select it for Multisim tasks. It uses the configured `multisim_native` MCP connection.

### Edit an existing project

1. `native_open_circuit` — open the actual source document.
2. `native_list_components` — read the component references and exact pin names.
3. Edit components and connections.
4. `native_check_netlist` — check the electrical netlist.
5. `native_save_source` — save the current workspace/source file.
6. `native_close_copy` — close the session.

Use `native_attach` with a process ID to work in an existing Multisim window. Closing an attached session releases the connection and leaves that window open.

Power symbols such as VCC and VEE can share a reference. Use the selected symbol's current component `id` for movement, rotation and wiring. Wire endpoints expose `component_id`; `native_list_wires` can filter by that ID. Ambiguous edit targets return candidate IDs.

### Connect a wire branch

1. Read the route with `native_list_wires`.
2. Call `native_split_wire` at a point on the route.
3. Connect the returned `junction_id` with `native_connect_endpoints`.

Read component and wire IDs again after undo, redo or a netlist check that returns `handles_invalidated: true`.

### Interactive simulation

Use `native_control_interactive` to `start`, `pause`, `resume` or `stop` simulation. Read `native_interactive_status` for the observed state, elapsed simulation time and errors. Export actual lit LEDs or displays with `native_export_interactive_image`.

For a low-frequency LED chaser, stop simulation and call `native_configure_interactive` with:

```json
{
  "time_step": 0.001,
  "max_time_step": 0.001,
  "real_time": true
}
```

Then call `native_control_interactive` with `{"action": "start"}`. The 1 ms steps reduce solver work; native real-time pacing keeps light changes observable. Choose smaller steps for faster signals, and verify the frequency and output sequence after changing them.

By default interactive settings belong to the native document and persist through normal save/close. Use persist:false for an intentionally temporary override; read that override with persist:false and confirm it with interactive_options.last_start.

To keep these settings in the original `.ms14`, call `native_configure_interactive` with `{"time_step": 0.001, "max_time_step": 0.001, "real_time": true, "persist": true, "save_to_source": true}`. The server writes native document properties, backs up the source and independently reopens the saved circuit to verify all simulation settings. Ordinary Multisim starts after reopening use those steps without an MCP override. External source edits block replacement. With only `persist: true`, settings remain in the editable document until normal save/close writes them; `saved_to_file` reports this distinction. Read document settings with `{"persist": true}`; restore automatic steps and real-time pacing with `{"persist": true, "reset": true}` (then save). Numeric-analysis definitions and other solver options are preserved.

Example request:

> Run this low-frequency LED chaser interactively with 1 ms steps and real-time pacing. Check its frequency and LED sequence, then export a frame showing an actual lit LED.

## Tools

| Category | Operations |
| --- | --- |
| Workflows | Dependent stages, result bindings, acceptance, wait, cancel, resume, session revisions |
| Sessions | Runtime checks, direct file open/create, explicit comparison copies, attach, diagnostics, close |
| Components | Library search, place, copy, delete, replace, rename |
| Parameters | Read/write parameters and embedded SPICE models |
| Geometry | Move, rotate, mirror, route wires, add text |
| Connections | Named pins, native autowiring, touching contacts, junctions, branches, endpoint replacement, net labels |
| Hierarchy | Sheets, subcircuits, hierarchical ports |
| History | Batch editing, checkpoints, undo, redo |
| Analysis | DC operating point, transient, AC lin/dec/oct, mixed RAW plots |
| Interactive simulation | Start, pause, resume, stop, configurable time steps, real-time pacing, live display states |
| Measurements | Mean, RMS, extrema, frequency, duty cycle, AC gain and phase |
| Verification | Limits, target tolerances, multiplexed seven-segment decoding |
| Experiments | Parameter sweeps, constraints, ranking, background jobs, cancel and retry |
| Reports | Chinese/English HTML, Markdown, CSV, native circuit PNG and waveform SVG |
| Layout | Endpoint checks, native wire rerouting, component bounds, orthogonal obstacle planning |
| Export | Native `.ms14`, PNG, BMP, RAW, CSV |

[Schematic guide](docs/schematic.md) · [Experiment guide](docs/experiments.md) · [Tool reference](docs/tools.md) · [Python example](examples/voltage_divider.py)

New circuits are created at the absolute filename supplied by the caller. `native_open_circuit` edits an existing source directly, and normal save/close retains edits in the current document. Backups, checkpoints and logs remain internal. Explicit comparison copies use a separate filename. See [file editing and persistence](docs/persistence.md).

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim installation directory | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | Internal recovery and session artifacts | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `MULTISIM_NATIVE_IO_DIR` | Optional ASCII directory for legacy SPICE file transfers | System temporary directory |
| `CODEX_HOME` | Codex configuration directory | `%USERPROFILE%\.codex` |

Run `multisim-native-mcp doctor` to check the Python architecture, package resources and Multisim modules. `configure` preserves the other Codex settings and creates a timestamped backup when updating an existing configuration.

## Development

```powershell
uv venv --python cpython-3.12-windows-x86-none
uv pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -m 'not native'
.\.venv\Scripts\python.exe -m pytest -m native
uv build
```

Native tests use the installed Multisim runtime. Close Multisim before running them.

## License

[MIT License](LICENSE).
