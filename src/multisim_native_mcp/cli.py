"""Server launcher, runtime checks and MCP client configuration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import struct
import sys

from . import __version__


def client_entry(install_path: str | None = None) -> dict:
    entry = {"command": sys.executable, "args": ["-m", "multisim_native_mcp"]}
    if install_path:
        entry["env"] = {"MULTISIM_NATIVE_INSTALL": str(Path(install_path).resolve())}
    return entry


def codex_document(text: str, entry: dict) -> str:
    """Round-trip other settings, replacing the named server table."""
    import tomlkit
    document = tomlkit.parse(text)
    servers = document.setdefault("mcp_servers", tomlkit.table())
    settings = tomlkit.table()
    settings.update(entry)
    servers["multisim_native"] = settings
    return tomlkit.dumps(document)


def configure(path: Path, entry: dict, client: str = 'codex') -> dict:
    from .dsh_config import dsh_document
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if client not in ('codex','dsh'):raise ValueError('Choose codex or dsh')
    result = dsh_document(original,entry) if client=='dsh' else codex_document(original, entry)
    backup = None
    if original != result:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(path.name + "." + stamp + ".bak")
            shutil.copy2(path, backup)
        temporary = path.with_name(path.name + ".multisim.tmp")
        temporary.write_text(result, encoding="utf-8", newline="\n")
        temporary.replace(path)
    return {"config": str(path), "client":client,"server": "multisim_native", "backup": str(backup) if backup else None}


def doctor(install_path: str | None = None, connect: bool = False) -> dict:
    if install_path:
        os.environ["MULTISIM_NATIVE_INSTALL"] = str(Path(install_path).resolve())
    from .paths import DATA_DIR, RESOURCE_DIR
    report = {
        "version": __version__, "platform": sys.platform,
        "python": sys.version.split()[0], "architecture": struct.calcsize("P") * 8,
        "resources": all((RESOURCE_DIR / name).is_file() for name in (
            "host_agent.js", "editor_agent.js", "simulation_settings.js", "startup_agent.js", "native-profile.json", "assets/blank14.3.ms14")),
        "data_directory": str(DATA_DIR),
    }
    if sys.platform == "win32" and struct.calcsize("P") == 4:
        from .bridge import NativeHost
        host = NativeHost()
        try:
            report["runtime"] = host.runtime_status()
        finally:
            host.close()
    report["ready"] = bool(report["resources"] and report.get("runtime", {}).get("available"))
    if connect:
        import asyncio
        try:
            report['connection']=asyncio.run(check_connection())
        except Exception as error:report['connection']={'ready':False,'error':str(error)[:300]}
        report['ready']=report['ready'] and report['connection']['ready']
    return report


async def check_connection():
    from mcp import ClientSession,types
    from mcp.client.stdio import StdioServerParameters,stdio_client
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='multisim-native-check-') as data_directory:
      parameters=StdioServerParameters(command=sys.executable,args=['-m','multisim_native_mcp'],
          env={**os.environ,'MULTISIM_NATIVE_DATA_DIR':data_directory})
      async with stdio_client(parameters) as (reader,writer):
        async with ClientSession(reader,writer,read_timeout_seconds=30) as session:
            initialized=await session.initialize();names=set();cursor=None
            while True:
                page=await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor)) if cursor else await session.list_tools()
                names.update(tool.name for tool in page.tools)
                cursor=page.next_cursor
                if not cursor:break
            result=await session.call_tool('native_runtime_status',{})
            if result.is_error:raise RuntimeError('MCP runtime status failed')
            runtime=result.structured_content or json.loads(result.content[0].text)
            required={'native_runtime_status','native_create_circuit','native_open_copy','native_export_image'}
            return {'ready':required<=names and runtime['available'],'server_version':initialized.server_info.version,'tool_count':len(names)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="multisim-native-mcp", description="Native Multisim MCP server")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="action")
    commands.add_parser("serve", help="Run the STDIO MCP server")
    check = commands.add_parser("doctor", help="Check Python, packaged resources and Multisim")
    check.add_argument("--multisim-path")
    check.add_argument("--connect",action='store_true',help='Check the STDIO handshake, tools and runtime status')
    config = commands.add_parser("config", help="Print an MCP configuration")
    config.add_argument("--format", choices=["json", "codex", "dsh"], default="json")
    config.add_argument("--multisim-path")
    register = commands.add_parser("configure", help="Register the server in an MCP client")
    register.add_argument("--client",choices=['codex','dsh'],default='codex')
    register.add_argument("--profile",default='desktop')
    register.add_argument("--config-path", type=Path)
    register.add_argument("--multisim-path")
    args = parser.parse_args(argv)
    try:
        if args.action == "config":
            from .dsh_config import dsh_document
            entry = client_entry(args.multisim_path)
            print(dsh_document('',entry) if args.format=='dsh' else codex_document("", entry) if args.format == "codex" else json.dumps({"mcpServers": {"multisim_native": entry}}, indent=2))
            return 0
        if args.action == "configure":
            from .dsh_config import profile_path
            path = args.config_path or (profile_path(args.profile) if args.client=='dsh' else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml")
            print(json.dumps(configure(path, client_entry(args.multisim_path),args.client), indent=2))
            return 0
        if args.action == "doctor":
            report = doctor(args.multisim_path,args.connect)
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 1
        if sys.platform != "win32" or struct.calcsize("P") != 4:
            parser.error("Use Windows with 32-bit Python 3.12. Run install.ps1 to set up the runtime.")
        from .server import main as serve
        serve()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
