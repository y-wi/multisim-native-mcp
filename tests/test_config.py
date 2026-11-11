import json
from pathlib import Path
import subprocess
import sys
import tomllib

from multisim_native_mcp.cli import client_entry, codex_document, configure


def test_codex_round_trip_preserves_other_servers():
    original = '# workspace settings\nmodel = "gpt-6"\n[mcp_servers.other]\ncommand = "other.exe"\n'
    result = codex_document(original, client_entry(r"C:\NI Suite"))
    data = tomllib.loads(result)
    assert '# workspace settings' in result
    assert data['model'] == 'gpt-6'
    assert data['mcp_servers']['other']['command'] == 'other.exe'
    assert data['mcp_servers']['multisim_native']['env']['MULTISIM_NATIVE_INSTALL'] == str(Path(r'C:\NI Suite').resolve())


def test_replace_existing_server_removes_old_environment():
    result = codex_document('[mcp_servers.multisim_native]\ncommand="old"\n[mcp_servers.multisim_native.env]\nOLD="old"\n', client_entry())
    entry = tomllib.loads(result)['mcp_servers']['multisim_native']
    assert entry['command'] == sys.executable
    assert 'env' not in entry
    assert 'startup_timeout_sec' not in entry and 'tool_timeout_sec' not in entry


def test_normal_configuration_does_not_pin_a_previous_project_globally():
    source='[mcp_servers.multisim_native]\ncommand="old"\n[mcp_servers.multisim_native.env]\nMULTISIM_NATIVE_WORKSPACE="E:/work"\nOLD="old"\n'
    result=tomllib.loads(codex_document(source,client_entry()))
    assert 'env' not in result['mcp_servers']['multisim_native']


def test_configure_backups_and_idempotence(tmp_path):
    path = tmp_path / 'profile with spaces' / 'config.toml'
    path.parent.mkdir();path.write_text('model = "sample"\n', encoding='utf-8')
    entry = client_entry()
    first = configure(path, entry)
    assert Path(first['backup']).read_text(encoding='utf-8') == 'model = "sample"\n'
    assert tomllib.loads(path.read_text())['model'] == 'sample'
    assert configure(path, entry)['backup'] is None


def test_invalid_toml_leaves_original_bytes(tmp_path):
    import pytest
    path = tmp_path/'config.toml';raw=b'[invalid\n';path.write_bytes(raw)
    with pytest.raises(Exception):configure(path, client_entry())
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


def test_config_command_emits_launchable_json():
    process = subprocess.run([sys.executable,'-m','multisim_native_mcp','config'],capture_output=True,text=True,check=True)
    entry = json.loads(process.stdout)['mcpServers']['multisim_native']
    assert entry['command'] == sys.executable
    assert entry['args'] == ['-m','multisim_native_mcp']


def test_cli_configure_isolated_home(tmp_path):
    import os
    environment = dict(os.environ, CODEX_HOME=str(tmp_path))
    subprocess.run([sys.executable,'-m','multisim_native_mcp','configure'],env=environment,capture_output=True,text=True,check=True)
    assert tomllib.loads((tmp_path/'config.toml').read_text())['mcp_servers']['multisim_native']['command'] == sys.executable
