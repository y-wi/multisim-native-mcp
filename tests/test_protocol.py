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
                assert initialized.server_info.version == '0.5.4'
                listed=await session.list_tools();names={tool.name for tool in listed.tools}
                interactive=next(tool for tool in listed.tools if tool.name=='native_configure_interactive')
                assert {'persist','save_to_source'}<=interactive.input_schema['properties'].keys()
                create=next(tool for tool in listed.tools if tool.name=='native_create_circuit')
                assert create.input_schema['required']==['output_path']
                assert 'workspace_path' not in create.input_schema['properties']
                assert interactive.input_schema['properties']['persist']['default'] is True
                workflow=next(tool for tool in listed.tools if tool.name=='native_run_workflow')
                definitions=workflow.input_schema['$defs']
                assert definitions['WorkflowPlan']['properties']['max_runtime']['default'] is None
                assert 'maxItems' not in definitions['EditStage']['properties']['operations']
                assert 'maximum' not in definitions['AnalysisOptions']['properties']['stop']
                capture=next(tool for tool in listed.tools if tool.name=='native_export_interactive_image')
                assert capture.input_schema['properties']['wait_timeout']['default'] is None
                state_tool=next(t for t in listed.tools if t.name=='native_get_circuit_state')
                assert state_tool.input_schema['properties']['include_parameters']['default'] is False
                assert state_tool.input_schema['properties']['include_nets']['default'] is False
                search_tool=next(t for t in listed.tools if t.name=='native_search_library')
                assert {'manufacturer','simulatable_only'}<=search_tool.input_schema['properties'].keys()
                set_param_tool=next(t for t in listed.tools if t.name=='native_set_parameter')
                assert {'index','name','role','value','expression'}<=set_param_tool.input_schema['properties'].keys()
                assert set_param_tool.input_schema['required']==['component_ref']
                place_tool=next(t for t in listed.tools if t.name=='native_place_component')
                assert 'params' in place_tool.input_schema['properties']
                save_tool=next(t for t in listed.tools if t.name=='native_save_source')
                assert save_tool.input_schema['properties']['verify']['default'] is True
                assert len(names)==91
                assert {'native_list_instruments','native_place_instrument','native_get_instrument_settings','native_set_instrument_settings','native_export_instrument_data'} <= names
                assert {'native_get_connectivity','native_resolve_signal','native_run_dc_sweep','native_fit_sheet','native_plot_waveform'} <= names
                assert {'native_list_texts','native_update_text','native_update_sheet','native_update_hierarchical_port','native_move_junction'} <= names
                assert {'native_connect_pins','native_delete_text'}.isdisjoint(names)
                alias=await session.call_tool('native_delete_text',{'object_id':'missing'})
                assert alias.is_error and 'Unknown tool' not in str(alias.content)
                assert {'native_run_workflow','native_workflow_status','native_control_workflow','native_prepare_components','native_session_changes','native_attach','native_split_wire','native_save_copy','native_read_waveform','native_repair_wire_geometry','native_control_interactive','native_interactive_status','native_configure_interactive','native_export_interactive_image','native_configure_wiring','native_connect_touching'} <= names
                status=await session.call_tool('native_runtime_status',{})
                assert not status.is_error
                data=status.structured_content or json.loads(status.content[0].text)
                assert not data['session_attached']
                assert len(data['checks']) == 15
                invalid=await session.call_tool('native_list_components',{})
                assert invalid.is_error
                resources = await session.list_resources()
                uris = {str(item.uri) for item in resources.resources}
                assert {
                    'multisim://skill/SKILL.md',
                    'multisim://skill/references/editing.md',
                    'multisim://skill/references/workflows.md',
                    'multisim://skill/references/analysis.md',
                } <= uris
                skill_doc = await session.read_resource('multisim://skill/SKILL.md')
                assert 'multisim-native' in skill_doc.contents[0].text
    asyncio.run(check())


def test_packaged_resources():
    from multisim_native_mcp.paths import RESOURCE_DIR
    profile=json.loads((RESOURCE_DIR/'native-profile.json').read_text())
    assert profile['version']=='14.3.1500.0'
    assert len(profile['modules'])==15
    assert all(len(value)==64 for value in profile['modules'].values())
    assert (RESOURCE_DIR/'assets/blank14.3.ms14').stat().st_size > 32
    for name in ['host_agent.js','editor_agent.js','instruments_agent.js','simulation_settings.js','startup_agent.js']:
        assert (RESOURCE_DIR/name).stat().st_size > 100


def test_connection_check_does_not_change_existing_experiment_records(tmp_path,monkeypatch):
    from multisim_native_mcp.cli import check_connection
    folder=tmp_path/'experiments';folder.mkdir()
    record=folder/('a'*32+'.json');raw=b'{"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"running"}'
    record.write_bytes(raw)
    monkeypatch.setenv('MULTISIM_NATIVE_DATA_DIR',str(tmp_path))
    result=asyncio.run(check_connection())
    assert result['tool_count']==91 and result['server_version']=='0.5.4'
    assert record.read_bytes()==raw
