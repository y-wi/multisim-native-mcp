import json
import shutil
import subprocess

from multisim_native_mcp.paths import RESOURCE_DIR


def test_native_startup_options_are_scoped_and_preserve_other_solver_settings():
    source=(RESOURCE_DIR/'editor_agent.js').read_text(encoding='utf-8')
    section=source[source.index('let interactiveConfiguration='):source.index('function interactiveStatus(')]
    harness=r'''
const assert=require('node:assert/strict');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const pointer=value=>({value,equals(other){return value===other.value;}});
let hook,detached=0,selected=pointer(10);
const uiThread=7,activeNativeOperation=null;
const Process={getCurrentThreadId:()=>uiThread,getModuleByName:()=>({getExportByName:()=>pointer(20)})};
const Interceptor={attach:(_,callbacks)=>{hook=callbacks;return{detach(){detached++;}};}};
const Memory={allocUtf16String:value=>({readUtf16String:()=>value})};
const project=()=>({proj:selected});
eval(input.source+`
 const native='tran  -env-options 1e-05 1e30 0 1e-05 auto_ic auto_tstep auto_tmax throttle';
 const options={time_step:.001,max_time_step:.001,real_time:true};
 assert.equal(rewriteInteractiveCommand('tran .001 10 uic',options),null);
 assert.equal(rewriteInteractiveCommand('tran -env-options .001 10 0 .001 auto_ic',options),null);
 assert.equal(rewriteInteractiveCommand('op',options),null);
 let result=rewriteInteractiveCommand(native,options);
 assert.equal(result.command,'tran -env-options 0.001 1e30 0 0.001 auto_ic throttle');
 result=rewriteInteractiveCommand(native,{max_time_step:.002,real_time:false});
 assert.equal(result.time_step,1e-5);assert.equal(result.max_time_step,.002);
 assert.ok(result.command.includes('auto_tstep'));assert.ok(!result.command.includes('auto_tmax'));
 assert.ok(!result.real_time);assert.ok(result.command.includes('auto_ic'));
 assert.throws(()=>rewriteInteractiveCommand('tran -env-options bad 1e30 0 1e-5',options),/parameters/);
 assert.equal(interactiveOptions().configured,false);
 interactiveOptions({configuration:options});
 function arm(){interactiveStartup={session:pointer(1),project:pointer(10),expires:Date.now()+1000};}
 function execute(command,session=1){const params=[Memory.allocUtf16String(command)],context={context:{ecx:pointer(session)}};
   hook.onEnter.call(context,params);hook.onLeave.call(context,{toInt32:()=>0});return params[0].readUtf16String();}
 arm();assert.equal(execute(native,2),native);assert.equal(interactiveOptions().last_start,null);
 selected=pointer(11);assert.equal(execute(native),native);selected=pointer(10);
 assert.equal(execute('tran .001 10 uic'),'tran .001 10 uic');
 assert.equal(execute(native),'tran -env-options 0.001 1e30 0 0.001 auto_ic throttle');
 assert.equal(interactiveOptions().last_start.native_result,0);
 assert.equal(interactiveOptions().last_start.applied,true);
 assert.equal(execute(native),native); // Another GUI run is not a new MCP start.
 arm();interactiveStartup.expires=0;assert.ok(execute(native).includes('0.001'));
 interactiveOptions({reset:true});assert.equal(detached,1);assert.equal(interactiveOptions().configured,false);
`);
console.log(JSON.stringify({passed:true}));
'''
    result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps({'source':section}),
                          text=True,capture_output=True,check=True,timeout=15)
    assert json.loads(result.stdout)['passed']
