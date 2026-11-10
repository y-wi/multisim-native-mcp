import os
from pathlib import Path
import subprocess
import sys
import pytest
from multisim_native_mcp.cli import client_entry,configure
from multisim_native_mcp.dsh_config import dsh_document,profile_path,yaml_parser,PLUGIN


def entries(text):
    doc=yaml_parser().load(text)
    return [entry for item in doc for entry in item.get('insert',[]) if entry.get('name')==PLUGIN]


def test_new_dsh_connection_is_inserted():
    text=dsh_document('',client_entry())
    entry=entries(text)[0]
    assert entry['config']['command']==sys.executable
    assert entry['config']['args']==['-m','multisim_native_mcp']
    assert entry['config']['toolCallTimeoutMs']==120000
    assert dsh_document(text,client_entry())==text


def test_update_preserves_other_plugins_comments_and_js_tags():
    original='''# user settings
- id: theme
  config:
    preference: light
- insert:
  - id: other
    name: another-plugin
    config:
      token: !!js process.env.MY_TOKEN
  - id: mcp-multisim-native
    name: "@deepseek-ai/dsh-mcp-client"
    config:
      serverName: multisim_native
      command: old.exe
      # connection settings
      reconnect:
        maxAttempts: 3
      env:
        CUSTOM: preserved
'''
    result=dsh_document(original,client_entry(r'C:\NI Suite'))
    doc=yaml_parser().load(result)
    assert doc[0]['config']['preference']=='light'
    assert '!!js process.env.MY_TOKEN' in result and '# user settings' in result
    assert '# connection settings' in result
    target=entries(result)[0]['config']
    assert target['reconnect']['maxAttempts']==3 and target['env']['CUSTOM']=='preserved'
    assert target['env']['MULTISIM_NATIVE_INSTALL']==str(Path(r'C:\NI Suite').resolve())


def test_repair_bare_patch_and_merge_duplicate_server_names():
    original=f'''- id: mcp-multisim-native
  name: "{PLUGIN}"
  config:
    command: bad.exe
- insert:
  - id: existing-multisim
    name: "{PLUGIN}"
    config:
      serverName: multisim_native
      command: previous.exe
'''
    result=dsh_document(original,client_entry())
    assert len(entries(result))==1
    assert entries(result)[0]['id']=='existing-multisim'
    assert all('id' not in item for item in yaml_parser().load(result))


@pytest.mark.parametrize('text',['settings: true','- insert: wrong','[invalid','- id: mcp-multisim-native\n  name: another-plugin\n'])
def test_invalid_patch_leaves_original_file(tmp_path,text):
    path=tmp_path/'cordis.patch.yml';path.write_text(text,encoding='utf-8');before=path.read_bytes()
    with pytest.raises(ValueError):configure(path,client_entry(),'dsh')
    assert path.read_bytes()==before and list(tmp_path.iterdir())==[path]


def test_custom_home_and_configure_idempotence(tmp_path,monkeypatch):
    monkeypatch.setenv('DSH_HOME',str(tmp_path))
    path=profile_path('desktop');path.parent.mkdir(parents=True)
    path.write_text('# profile\n',encoding='utf-8')
    first=configure(path,client_entry(),'dsh')
    assert Path(first['backup']).read_text()=='# profile\n'
    assert configure(path,client_entry(),'dsh')['backup'] is None
    with pytest.raises(ValueError):profile_path('../escape')


def test_cli_dsh_export_and_profile_configuration(tmp_path):
    r=subprocess.run([sys.executable,'-m','multisim_native_mcp','config','--format','dsh'],capture_output=True,check=True,encoding='utf-8')
    assert len(entries(r.stdout))==1
    subprocess.run([sys.executable,'-m','multisim_native_mcp','configure','--client','dsh','--profile','web'],env={**os.environ,'DSH_HOME':str(tmp_path)},capture_output=True,check=True)
    assert len(entries((tmp_path/'profiles/web/cordis.patch.yml').read_text()))==1
