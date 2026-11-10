# Multisim Native MCP

[English](README.md) · [简体中文](README.zh-CN.md)

Native circuit editing and analog analysis for NI Multisim through the Model Context Protocol.

- 44 MCP tools for components, wires, sheets, subcircuits, models and analysis.
- Editable `.ms14` projects with named-pin connections and routed wire branches.
- Batch edits, checkpoints, undo, redo and native save/reopen.
- DC operating point and transient analog analysis with RAW and CSV output.
- Schematic export to PNG and BMP.
- Windows installer with automatic Python setup and Codex configuration.

## Requirements

| Component | Version |
| --- | --- |
| Operating system | Windows 10 / 11 |
| NI Multisim | 14.2 or 14.3, Windows, 32-bit |
| Python | CPython 3.12, 32-bit; installed automatically |
| Transport | STDIO |

Multisim 14.2 and 14.3 expose the same private native object model, and both are supported: component and wire editing, netlist generation, DC operating point and transient analysis, native `.ms14` save and image export work on either version. `native-profile.json` keeps the 14.3 module hashes as a diagnostic reference, so a 14.2 installation reports `compatible: false` while still running normally. An installation outside the default 14.3 directory is selected with `-MultisimPath` (see [Install](#install)).

## Install

Run in PowerShell:

```powershell
irm https://raw.githubusercontent.com/y-wi/multisim-native-mcp/v0.2.2/install.ps1 | iex
```

Restart Codex. The server appears as `multisim_native`.

To install from a checkout:

```powershell
git clone https://github.com/y-wi/multisim-native-mcp.git
cd multisim-native-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

For a custom Multisim installation directory:

```powershell
.\install.ps1 -MultisimPath 'D:\Applications\NI\Circuit Design Suite 14.2'
```

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
uv tool install --python cpython-3.12-windows-x86-none https://github.com/y-wi/multisim-native-mcp/releases/download/v0.2.2/multisim_native_mcp-0.2.2-py3-none-any.whl
multisim-native-mcp doctor
multisim-native-mcp configure
```

## Use

Start with one of these requests in your MCP client:

> Create a 12 V voltage divider with two 1 kΩ resistors. Connect the named pins, check the netlist, save the circuit and export a PNG.

> Open a copy of my Multisim project. List the components and pin names, replace R2 with 2.2 kΩ and save a new project.

> Move R1 and keep its wires attached. Add a branch at the midpoint of the output wire, then save and reopen the circuit.

### Edit an existing project

1. `native_open_copy` — open a working copy.
2. `native_list_components` — read the component references and exact pin names.
3. Edit components and connections.
4. `native_check_netlist` — check the electrical netlist.
5. `native_save_copy` — save the resulting `.ms14` file.
6. `native_close_copy` — close the session.

Use `native_attach` with a process ID to work in an existing Multisim window. Closing an attached session releases the connection and leaves that window open.

### Connect a wire branch

1. Read the route with `native_list_wires`.
2. Call `native_split_wire` at a point on the route.
3. Connect the returned `junction_id` with `native_connect_endpoints`.

Read component and wire IDs again after undo, redo or a netlist check that returns `handles_invalidated: true`.

## Tools

| Category | Operations |
| --- | --- |
| Sessions | Runtime checks, open copy, create project, attach, diagnostics, close |
| Components | Library search, place, copy, delete, replace, rename |
| Parameters | Read/write parameters and embedded SPICE models |
| Geometry | Move, rotate, mirror, route wires, add text |
| Connections | Named pins, junctions, branches, endpoint replacement, net labels |
| Hierarchy | Sheets, subcircuits, hierarchical ports |
| History | Batch editing, checkpoints, undo, redo |
| Analog analysis | DC operating point, transient analysis, waveform data |
| Export | Native `.ms14`, PNG, BMP, RAW, CSV |

[Tool reference](docs/tools.md) · [Python example](examples/voltage_divider.py)

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `MULTISIM_NATIVE_INSTALL` | Multisim installation directory | `%ProgramFiles(x86)%\National Instruments\Circuit Design Suite 14.3` |
| `MULTISIM_NATIVE_DATA_DIR` | Working copies and session artifacts | `%LOCALAPPDATA%\MultisimNativeMCP` |
| `CODEX_HOME` | Codex configuration directory | `%USERPROFILE%\.codex` |

Run `multisim-native-mcp doctor` to check the Python architecture, package resources and Multisim modules. `configure` preserves the other Codex settings and creates a timestamped backup when updating an existing configuration.

Module hashes and the reference version are diagnostic information. Startup, process attachment and installation readiness use runtime availability.

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

[FSF All-Permissive License](LICENSE).
