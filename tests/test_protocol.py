import asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client


def test_installed_package_stdio(tmp_path):
    async def check():
        parameters=StdioServerParameters(command=sys.executable,args=['-m','multisim_native_mcp'],env={**os.environ,'MULTISIM_NATIVE_DATA_DIR':str(tmp_path)})
        async with stdio_client(parameters) as (reader,writer):
            async with ClientSession(reader,writer,read_timeout_seconds=30) as session:
                initialized=await session.initialize()
                assert initialized.server_info.name == 'multisim-native'
                assert initialized.server_info.version == '0.4.0'
                listed=await session.list_tools();names={tool.name for tool in listed.tools}
                assert len(names)==72
                assert {'native_run_workflow','native_workflow_status','native_control_workflow','native_prepare_components','native_session_changes','native_attach','native_split_wire','native_save_copy','native_read_waveform','native_repair_wire_geometry','native_control_interactive','native_interactive_status','native_configure_interactive','native_export_interactive_image','native_configure_wiring','native_connect_touching'} <= names
                status=await session.call_tool('native_runtime_status',{})
                assert not status.is_error
                data=status.structured_content or json.loads(status.content[0].text)
                assert not data['running']
                assert len(data['checks']) == 15
                invalid=await session.call_tool('native_list_components',{})
                assert invalid.is_error
    asyncio.run(check())


def test_packaged_resources():
    from multisim_native_mcp.paths import RESOURCE_DIR
    profile=json.loads((RESOURCE_DIR/'native-profile.json').read_text())
    assert profile['version']=='14.3.1500.0'
    assert len(profile['modules'])==15
    assert all(len(value)==64 for value in profile['modules'].values())
    assert (RESOURCE_DIR/'assets/blank14.3.ms14').stat().st_size > 32
    for name in ['host_agent.js','editor_agent.js','startup_agent.js']:
        assert (RESOURCE_DIR/name).stat().st_size > 100


def test_connection_check_does_not_change_existing_experiment_records(tmp_path,monkeypatch):
    from multisim_native_mcp.cli import check_connection
    folder=tmp_path/'experiments';folder.mkdir()
    record=folder/('a'*32+'.json');raw=b'{"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"running"}'
    record.write_bytes(raw)
    monkeypatch.setenv('MULTISIM_NATIVE_DATA_DIR',str(tmp_path))
    result=asyncio.run(check_connection())
    assert result['tool_count']==72 and result['server_version']=='0.4.0'
    assert record.read_bytes()==raw
