"""Create, analyze and save a voltage divider through the installed MCP server."""
import asyncio,json,sys
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client


async def create_divider(output: Path):
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    parameters=StdioServerParameters(command=sys.executable,args=['-m','multisim_native_mcp'])
    async with stdio_client(parameters) as (reader,writer):
        async with ClientSession(reader,writer,read_timeout_seconds=90) as session:
            await session.initialize()
            calls=0
            async def call(tool_name,**args):
                nonlocal calls
                calls+=1
                result=await session.call_tool(tool_name,args)
                if result.is_error:raise RuntimeError(result.content[0].text)
                return result.structured_content or json.loads(result.content[0].text)
            try:
                await call('native_create_circuit',output_path=str(output/'voltage-divider.ms14'),title='Voltage divider')
                operations=[]
                for name,ref,x,y,value in [('DC_POWER','V1',108,108,12),('RESISTOR_VIRTUAL','R1',306,108,1000),('RESISTOR_VIRTUAL','R2',504,108,1000),('GROUND','0',108,306,None)]:
                    args={'name':name,'ref':ref,'x':x,'y':y}
                    if value is not None:args['parameters']=[{'index':1,'value':value}]
                    operations.append({'operation':'place','arguments':args})
                for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]:
                    operations.append({'operation':'wire','arguments':{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}}})
                scene=(await call('native_edit_batch',operations=operations))['state']
                content,page=scene['content_bounds'],scene['page']['bounds']
                if any(content[k]<page[k]+18 for k in ('left','top')) or any(content[k]>page[k]-18 for k in ('right','bottom')):
                    raise RuntimeError('Fit the complete circuit inside the sheet before saving')
                netlist=await call('native_check_netlist')
                if netlist['failed']:raise RuntimeError(netlist['messages'])
                result=await call('native_run_analysis',analysis='op')
                current=next(v for v in result['vectors'] if v['name']=='I(V1)')
                if current['unit']!='A' or abs(current['last']+.006)>1e-8:raise RuntimeError('Divider source current must be -0.006 A')
                await call('native_save_source')
                await call('native_export_image',output_path=str(output/'voltage-divider.png'),overwrite=True,dpi=192)
                (output/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            finally:
                await call('native_close_copy')
            return {**result,'tool_calls':calls}


if __name__=='__main__':
    print(json.dumps(asyncio.run(create_divider(Path(sys.argv[1] if len(sys.argv)>1 else 'output'))),indent=2))
