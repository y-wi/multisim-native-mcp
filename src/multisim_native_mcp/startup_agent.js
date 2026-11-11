"use strict";
// Observe normal native startup without a wall-clock deadline.
function startupErrors(){
  const user=Process.findModuleByName('user32.dll');if(!user)return [];
  const call=(name,result,args)=>new NativeFunction(user.getExportByName(name),result,args,'stdcall');
  const length=call('GetWindowTextLengthW','int',['pointer']),getText=call('GetWindowTextW','int',['pointer','pointer','int']);
  const text=window=>{const count=length(window)+1,buffer=Memory.alloc(count*2);getText(window,buffer,count);return buffer.readUtf16String();};
  const process=call('GetWindowThreadProcessId','uint',['pointer','pointer']),errors=[];
  const callback=new NativeCallback(window=>{
    const owner=Memory.alloc(4);process(window,owner);if(owner.readU32()!==Process.id)return 1;
    const title=text(window);if(!/^(Error|错误|Erreur|Fehler)$/i.test(title))return 1;
    const messages=[],child=new NativeCallback(item=>{const value=text(item);if(value)messages.push(value);return 1;},'int',['pointer','pointer'],'stdcall');
    call('EnumChildWindows','int',['pointer','pointer','pointer'])(window,child,ptr(0));
    errors.push({title,messages});return 1;
  },'int',['pointer','pointer'],'stdcall');
  call('EnumWindows','int',['pointer','pointer'])(callback,ptr(0));return errors;
}
rpc.exports={
  ready(){return Process.enumerateModules().some(m=>m.name.toLowerCase()==='sch_cap.dll');},
  report(){return {passive:true,modules:Process.enumerateModules().length,
    dao_loaded:Process.enumerateModules().some(m=>m.name.toLowerCase()==='dao360.dll'),startup_errors:startupErrors()};}
};
