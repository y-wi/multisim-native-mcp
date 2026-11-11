import json
import shutil
import subprocess

from multisim_native_mcp.paths import RESOURCE_DIR


def test_native_wiring_options_validate_convert_bool_and_restore():
    source=(RESOURCE_DIR/'editor_agent.js').read_text(encoding='utf-8')
    section=source[source.index('function wiringSettings()'):source.index('function nativeDrop(')]
    harness=r'''
const assert=require('node:assert/strict');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let originalWiringOptions=null;
const values={AutowireOnConnection:1,AutowireOnMove:1,AutowirePinTouching:0,AutowirePinConnections:12};
const settings={isNull:()=>false};
function method(dll,name,result,types){
 if(name.startsWith('?GetSCH_CAPDocTypeSettings'))return ()=>settings;
 const match=/^\?(Is|Get|Set)(\w+)@/.exec(name);assert.ok(match,name);
 return (object,value)=>{assert.equal(object,settings);
  if(match[1]==='Set'){assert.equal(typeof value,'number');values[match[2]]=value;}
  else return values[match[2]];
 };
}
eval(input.source+`
 const before=wiringOptions();
 assert.equal(before.connect_touching,false);
 wiringOptions({autowire_on_move:false,connect_touching:true,move_connection_limit:24});
 assert.equal(values.AutowireOnMove,0);assert.equal(values.AutowirePinTouching,1);
 assert.equal(values.AutowirePinConnections,24);
 assert.throws(()=>wiringOptions({move_connection_limit:0}),/1 to 10000/);
 assert.throws(()=>wiringOptions({connect_touching:'true'}),/boolean/);
 assert.throws(()=>wiringOptions({reset:true,connect_touching:true}),/reset alone/);
 assert.throws(()=>temporaryWiring({connect_touching:false},()=>{throw new Error('operation failed');}),/operation failed/);
 assert.equal(values.AutowirePinTouching,1);
 closeWiringOptions();assert.deepEqual(wiringOptions(),before);
 assert.equal(originalWiringOptions,null);
 assert.deepEqual(wiringOptions({reset:true}),before);
`);
console.log(JSON.stringify({passed:true}));
'''
    result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps({'source':section}),
                          text=True,capture_output=True,check=True,timeout=15)
    assert json.loads(result.stdout)['passed']
