import asyncio
import json
import os
import sys

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from multisim_native_mcp.contracts import normalize_criteria, normalize_measurements
from multisim_native_mcp.verification import verify


def test_consistent_ids_and_legacy_criteria():
    measurements=[{'id':'output','value':6}]
    for key in ['id','measurement']:
        result=verify(measurements,[{key:'output','target':6}])
        assert result['passed'] and result['criteria'][0]['id']=='output'
        assert result['criteria'][0]['measurement']=='output'
    with pytest.raises(ValueError,match='same measurement'):
        normalize_criteria([{'id':'a','measurement':'b','target':6}])


@pytest.mark.parametrize('requests,expected',[
    ([{'id':'v','signal':'V(1)'}],r'measurements\[0\].metric'),
    ([{'metric':'mean'}],r'measurements\[0\].signal'),
    ([{'metric':'gain_db','signal':'V(1)'}],'reference and frequency_hz'),
])
def test_readable_measurement_errors(requests,expected):
    with pytest.raises(ValueError,match=expected):normalize_measurements(requests)


def test_bad_criterion_identifies_expected_field():
    with pytest.raises(ValueError,match=r'criteria\[0\].id'):
        normalize_criteria([{'target':6}])
    with pytest.raises(ValueError,match="expected one of.*output"):
        normalize_criteria([{'id':'wrong','min':0}],{'output'})


def test_stdio_schema_and_alias_validation_before_waveform_read(tmp_path):
    async def check():
        parameters=StdioServerParameters(command=sys.executable,args=['-m','multisim_native_mcp'],env={**os.environ,'MULTISIM_NATIVE_DATA_DIR':str(tmp_path/'server')})
        raw=tmp_path/'op.raw'
        raw.write_text('Plotname: DC Operating Point\nNo. Variables: 1\nNo. Points: 1\nVariables:\n0 v1 voltage V(1)\nValues:\n0 6\n')
        async with stdio_client(parameters) as (reader,writer):
            async with ClientSession(reader,writer,read_timeout_seconds=30) as session:
                await session.initialize()
                tools={t.name:t for t in (await session.list_tools()).tools}
                schema=tools['native_verify_waveform'].model_dump(by_alias=True)['inputSchema']
                assert 'id' in schema['$defs']['AcceptanceCriterion']['properties']
                for key in ['id','measurement']:
                    result=await session.call_tool('native_verify_waveform',{'raw_path':str(raw),'measurements':[{'id':'v','metric':'mean','signal':'V(1)'}],'criteria':[{key:'v','target':6}]})
                    assert not result.is_error
                    data=result.structured_content or json.loads(result.content[0].text)
                    assert data['passed']
                result=await session.call_tool('native_verify_waveform',{'raw_path':'absent.raw','measurements':[{'id':'v','metric':'mean','signal':'V(1)'}],'criteria':[{'target':6}]})
                assert result.is_error
                message=' '.join(c.text for c in result.content if hasattr(c,'text'))
                assert 'criteria' in message and 'id' in message and 'Field required' in message
                assert 'FileNotFound' not in message
    asyncio.run(check())
