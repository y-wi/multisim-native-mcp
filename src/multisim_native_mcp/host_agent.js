'use strict';
const keep = [];
const jobs = [];
const functions = new Map();
const stringMethods = new Map();
const objectHandles = new Map();
let cachedDiagram = null;
let selectedProjectIndex = 0;
let selectedSheetId = null;
let activeNativeOperation = null;
const nativeErrorLog = [];
function native(dll, name, result, args, abi = 'thiscall') {
  const key = [dll, name, result, args, abi].join('|');
  if (!functions.has(key)) functions.set(key, new NativeFunction(Process.getModuleByName(dll).getExportByName(name), result, args, abi));
  return functions.get(key);
}
function ptrFunction(dll, name, args = [], abi = 'thiscall') { return native(dll, name, 'pointer', args, abi); }
function project() {
  const container = ptrFunction('DrwEngine.dll', '?GetWorkSpaceContainer@@YAPAVCWorkspaceContainer@@XZ', [], 'mscdecl')();
  const workspace = ptrFunction('DrwEngine.dll', '?GetMainWorkSpace@CWorkspaceContainer@@QAEPAVCWorkSpace@@XZ', ['pointer'])(container);
  const proj = ptrFunction('DrwEngine.dll', '?GetProject@CWorkSpace@@QAEPAVCProject@@I@Z', ['pointer', 'uint'])(workspace, selectedProjectIndex);
  if (proj.isNull()) throw new Error('No project in the isolated host');
  return { container, workspace, proj };
}
function pathString(value) {
  const storage = Memory.alloc(4);
  ptrFunction('Library.dll', '??0CPathString@@QAE@PB_W@Z', ['pointer', 'pointer'])(storage, Memory.allocUtf16String(value));
  return storage;
}
function projectPath(proj) {
  const method = Process.getModuleByName('DrwEngine.dll').enumerateExports().find(e => e.name.startsWith('?GetProjectFilePath@CProject'));
  const storage = new NativeFunction(method.address, 'pointer', ['pointer'], 'thiscall')(proj);
  return storage.readPointer().readUtf16String();
}
function rtti(p) {
  try {
    const locator = p.readPointer().sub(4).readPointer();
    return { name: locator.add(12).readPointer().add(8).readUtf8String(), offset: locator.add(4).readU32() };
  } catch (_) { return { name: 'unknown', offset: 0 }; }
}
function basePointer(p, type) {
  const locator=p.readPointer().sub(4).readPointer();
  const hierarchy=locator.add(16).readPointer(), count=hierarchy.add(8).readU32(), array=hierarchy.add(12).readPointer();
  for(let n=0;n<count;n++) { const b=array.add(n*4).readPointer();if(b.readPointer().add(8).readUtf8String()===type)return p.add(b.add(8).readS32()); }
  throw new Error('Native base type not found: '+type);
}
function diagram(materialize = true) {
  const p = project();
  if (cachedDiagram && cachedDiagram.proj.equals(p.proj)) return cachedDiagram;
  const vec = Memory.alloc(12); vec.writeByteArray(new Uint8Array(12));
  native('DrwEngine.dll', '?GetAllSheetsInProject@CProject@@QBEXAAV?$vector@PAVCDrwSubSheet@@V?$allocator@PAVCDrwSubSheet@@@std@@@std@@@Z', 'void', ['pointer','pointer'])(p.proj, vec);
  const candidates = [];
  let begin = vec.readPointer(), end = vec.add(4).readPointer();
  while (!begin.isNull() && begin.compare(end) < 0 && candidates.length < 1000) { const sh = begin.readPointer(); candidates.push({pointer:sh,...rtti(sh)}); begin=begin.add(4); }
  const selected = candidates.find(sh => /CSCH_CAPSubSheet/.test(sh.name) && (!selectedSheetId || sh.pointer.toString()===selectedSheetId));
  if (!selected && materialize) {
    native('DrwEngine.dll','?ShowAllSubSheets@CProject@@QAEXXZ','void',['pointer'])(p.proj);
    return diagram(false);
  }
  if (!selected) throw new Error('No native schematic sheet found: '+JSON.stringify(candidates));
  const sheet = selected.pointer;
  const doc = ptrFunction('SCH_CAP.dll', '?GetDocument@CSCH_CAPSubSheet@@QAEPAVCIITHierDoc@@XZ', ['pointer'])(sheet);
  if (doc.isNull()) throw new Error('Native schematic document is unavailable');
  const graph = ptrFunction('SCH_CAP.dll', '?GetDiagram@CSCH_CAPDoc@@QBEPAVCODDiagram@@XZ', ['pointer'])(doc);
  if (graph.isNull()) throw new Error('Native schematic diagram is not materialized');
  const composite = ptrFunction('Od101dll.dll', '?GetComponent@CODDiagram@@QBEPAVCODComponent@@XZ', ['pointer'])(graph);
  cachedDiagram = { ...p, sheet, doc, graph, composite, candidates };
  return cachedDiagram;
}
function enumerate() {
  const d = diagram();
  const pos = Memory.alloc(4);
  pos.writePointer(ptrFunction('Od101dll.dll', '?GetHeadPosition@CODComposite@@UBEPAU__POSITION@@XZ', ['pointer'])(d.composite));
  const next = ptrFunction('Od101dll.dll', '?GetNext@CODComposite@@UBEPAVCODComponent@@AAPAU__POSITION@@@Z', ['pointer', 'pointer']);
  const objects = [];
  while (!pos.readPointer().isNull() && objects.length < 20000) {
    const p = next(d.composite, pos);
    objectHandles.set(p.toString(),p);
    objects.push({ id: p.toString(), ...rtti(p) });
  }
  return { path: projectPath(d.proj), objects };
}
function listChildren(composite) {
  const pos = Memory.alloc(4);
  pos.writePointer(ptrFunction('Od101dll.dll', '?GetHeadPosition@CODComposite@@UBEPAU__POSITION@@XZ', ['pointer'])(composite));
  const next=ptrFunction('Od101dll.dll','?GetNext@CODComposite@@UBEPAVCODComponent@@AAPAU__POSITION@@@Z',['pointer','pointer']);
  const result=[];
  while(!pos.readPointer().isNull() && result.length<20000)result.push(next(composite,pos));
  return result;
}
function returnedString(dll,prefix,object) {
  const key=dll+'|'+prefix;
  if(!stringMethods.has(key)) {
    const matches=Process.getModuleByName(dll).enumerateExports().filter(e=>e.name.startsWith(prefix));
    if(matches.length!==1)throw new Error('Ambiguous native string method: '+prefix);
    stringMethods.set(key,ptrFunction(dll,matches[0].name,['pointer','pointer']));
  }
  const result=Memory.alloc(4);result.writePointer(ptr(0));
  stringMethods.get(key)(object,result);
  const p=result.readPointer();const value=p.isNull()?'':p.readUtf16String();
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(result);
  return value;
}
function components() {
  const d=diagram();const result=[];
  for(const obj of listChildren(d.composite)) {
    try {basePointer(obj,'.?AVCIITSymbolComp@@');}catch(_){continue;}
    objectHandles.set(obj.toString(),obj);
    const ci=ptrFunction('Od101dll.dll','?GetCiComponent@CIITSymbolComp@@UBEPAVCiComponent@@XZ',['pointer'])(basePointer(obj,'.?AUIRefDesable@@'));
    if(ci.isNull())continue;
    const localRef=returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',ci);
    const ref=instanceString('CIRCEXP.dll','?GetInstanceRefDes@CiComponent@@',ci,[treeInstance(),ptr(0),ptr(0),ptr(0)],Array(4).fill('pointer')) || localRef;
    const pins=[];
    for(const child of listChildren(obj))if(/CIITPinSymbolComp/.test(rtti(child).name)) {
      const pin=returnedString('Od101dll.dll','?GetPinName@CIITPinSymbolComp@@',child);
      const connector=listChildren(child).find(p=>/CIITPinConnectorComp/.test(rtti(p).name));
      if(!connector)continue;
      objectHandles.set(connector.toString(),connector);
      const count=native('Od101dll.dll','?GetConnectionCount@CODConnector@@QBEHXZ','int',['pointer'])(connector);
      const x=Memory.alloc(4), y=Memory.alloc(4);
      native('Od101dll.dll','?GetCenter@CODConnector@@UAEXAAH0@Z','void',['pointer','pointer','pointer'])(connector,x,y);
      pins.push({name:pin,id:connector.toString(),connections:count,x:x.readS32(),y:y.readS32()});
    }
    result.push({id:obj.toString(),ref,local_ref:localRef,transform:matrix(obj),pins});
  }
  return {path:projectPath(d.proj),components:result};
}
function component(ref) {
  const all=components().components,exact=all.filter(c=>c.ref===ref||c.id===ref);
  const matches=exact.length?exact:all.filter(c=>c.local_ref===ref);
  if(matches.length!==1)throw new Error('Expected one component named '+ref);
  return matches[0];
}
function matrix(object) {
  const graphic=ptrFunction('Od101dll.dll','?GetGraphic@CODComponent@@QAEPAVCODGraphic@@XZ',['pointer'])(object);
  const transform=ptrFunction('Od101dll.dll','?GetTransformer@CODGraphic@@QAEPAVCODTransformer@@XZ',['pointer'])(graphic);
  if(transform.isNull())return [1,0,0,1,0,0];
  const values=Array.from({length:6},()=>Memory.alloc(4));
  native('Od101dll.dll','?Matrix@CODTransformer@@UBEXAAM00000@Z','void',['pointer',...Array(6).fill('pointer')])(transform,...values);
  return values.map(v=>v.readFloat());
}
function move(args) {
  const c=component(args.ref),object=ptr(c.id),before=matrix(object);
  const attached=wires().wires.filter(w=>w.source.ref===c.ref||w.target.ref===c.ref);
  native('Od101dll.dll','?MoveComponentBy@CODDiagram@@UAEXPAVCODComponent@@VCSize@@@Z','void',['pointer','pointer','int','int'])(diagram().graph,object,args.dx,args.dy);
  const after=matrix(object);
  const pins=component(args.ref).pins;
  for(const w of attached) {
    let points=w.points;
    for(const end of ['source','target']) {
      if(w[end].ref!==c.ref)continue;
      const pin=pins.find(p=>p.id===w[end].id);
      if(!pin || points.length<2)throw new Error('Cannot update a wire endpoint');
      if(end==='source')points=points.slice().reverse();
      const old=points[points.length-1],previous=points[points.length-2],next={x:pin.x,y:pin.y};
      const corner=previous.y===old.y?{x:next.x,y:old.y}:{x:old.x,y:next.y};
      points=[...points.slice(0,-1),corner,next].filter((p,i,all)=>i===0||p.x!==all[i-1].x||p.y!==all[i-1].y);
      if(end==='source')points.reverse();
    }
    setWirePoints(ptr(w.id),points);
  }
  return {ref:c.ref,before,after,pins,updated_wires:attached.length};
}
function setWirePoints(object,points) {
  ensureWirePen(object);
  const transform=matrix(object),[a,b,c,d,tx,ty]=transform,det=a*d-b*c;
  if(Math.abs(det)<0.000001)throw new Error('Wire has a singular transform');
  const values=Memory.alloc(points.length*8);
  points.forEach((p,i)=>{const x=p.x-tx,y=p.y-ty;values.add(i*8).writeS32(Math.round((d*x-c*y)/det));values.add(i*8+4).writeS32(Math.round((-b*x+a*y)/det));});
  const graphic=ptrFunction('Od101dll.dll','?GetVertices@CODVerticesComp@@QAEPAVCODVertices@@XZ',['pointer'])(object);
  if(rtti(graphic).name!=='.?AVCODLinkGraphic@@')throw new Error('Unsupported wire graphic type');
  // CODLinkComp::GetVertices dispatches vtable+0xb0 to obtain the wrapped CODMultiLine.
  const line=new NativeFunction(graphic.readPointer().add(0xb0).readPointer(),'pointer',['pointer'],'thiscall')(graphic);
  if(rtti(line).name!=='.?AVCODMultiLine@@')throw new Error('Unsupported wire polyline type');
  native('Od101dll.dll','?SetNewPointsArray@CODVertices@@QAEXPAVCPoint@@H@Z','void',['pointer','pointer','int'])(line,values,points.length);
}
function wirePen(object) {
  return ptrFunction('Od101dll.dll','?GetPen@CODVerticesComp@@QAEPAVCPen@@XZ',['pointer'])(object);
}
function ensureWirePen(object,preferred) {
  if(!wirePen(object).isNull())return;
  const pen=preferred&&!preferred.isNull()?preferred:listChildren(diagram().composite)
    .filter(o=>/LinkComp/.test(rtti(o).name)).map(wirePen).find(p=>!p.isNull());
  if(!pen)throw new Error('No native wire drawing pen is available');
  const graphic=ptrFunction('Od101dll.dll','?GetGraphic@CODComponent@@QAEPAVCODGraphic@@XZ',['pointer'])(object);
  native('Od101dll.dll','?SetPen@CODFullGraphic@@UAEXPAVCPen@@@Z','void',['pointer','pointer'])(graphic,pen);
}
function save(args) {
  const p=project(),value=pathString(args.path),error=Memory.alloc(4);error.writeS32(0);
  const symbol=Process.getModuleByName('DrwEngine.dll').enumerateExports().find(e=>e.name.startsWith('?SaveProjectDocument@CProject'));
  const result=new NativeFunction(symbol.address,'int',['pointer','pointer','pointer','uint8','pointer','uint8','uint8'],'thiscall')(p.proj,value,ptr(0),0,error,0,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);
  return {nativeResult:result,errorCode:error.readS32(),path:args.path};
}
function wire(args) {
  const d=diagram(),source=component(args.source.ref),target=component(args.target.ref);
  const s=source.pins.find(p=>p.name===args.source.pin),t=target.pins.find(p=>p.name===args.target.pin);
  if(!s||!t)throw new Error('Named pin does not exist');
  const tree=ptrFunction('DrwEngine.dll','?GetFirstTreeInstanceForSheet@CProject@@QAEPAVCTreeInstance@@PAVCDrwSubSheet@@@Z',['pointer','pointer'])(d.proj,d.sheet);
  const nativeSymbol=Process.getModuleByName('SCH_CAP.dll').enumerateExports().find(e=>e.name.startsWith('?CreateWireBase@CBackAnnotationTarget'));
  const create=new NativeFunction(nativeSymbol.address,'pointer',['pointer','pointer','pointer','pointer'],'mscdecl');
  if(s.id===t.id)throw new Error('Cannot wire a pin to itself');
  const existing=wires().wires.find(w=>(w.source.id===s.id&&w.target.id===t.id)||(w.source.id===t.id&&w.target.id===s.id));
  if(existing)return {...existing,alreadyConnected:true};
  let points=ptr(0);
  if(args.points && args.points.length) {
    const values=Memory.alloc(args.points.length*8);
    args.points.forEach((p,i)=>{values.add(i*8).writeS32(p.x);values.add(i*8+4).writeS32(p.y);});
    points=Memory.alloc(12);points.writePointer(values);points.add(4).writePointer(values.add(args.points.length*8));points.add(8).writePointer(values.add(args.points.length*8));
  }
  const w=create(tree,ptr(s.id),ptr(t.id),points);
  if(w.isNull())throw new Error('Native wire factory rejected the connection');
  ensureWirePen(w);
  return {...wires().wires.find(item=>item.id===w.toString()),alreadyConnected:false};
}
function wires() {
  const d=diagram(),pins=new Map();
  for(const c of components().components)for(const p of c.pins)pins.set(p.id,{ref:c.ref,pin:p.name});
  const result=[];
  for(const object of listChildren(d.composite)) {
    if(!/CIITLinkComp/.test(rtti(object).name))continue;
    const source=ptrFunction('Od101dll.dll','?GetSourceConnector@CODLinkComp@@QAEPAVCODConnector@@XZ',['pointer'])(object);
    const target=ptrFunction('Od101dll.dll','?GetTargetConnector@CODLinkComp@@QAEPAVCODConnector@@XZ',['pointer'])(object);
    const vertices=Memory.alloc(4),count=Memory.alloc(4);vertices.writePointer(ptr(0));count.writeS32(0);
    native('Od101dll.dll','?GetVertices@CODLinkComp@@QAEXAAPAVCPoint@@AAH@Z','void',['pointer','pointer','pointer'])(object,vertices,count);
    const points=[];const v=vertices.readPointer();
    if(count.readS32()>10000)throw new Error('Invalid native vertex count');
    for(let n=0;!v.isNull()&&n<count.readS32();n++)points.push({x:v.add(n*8).readS32(),y:v.add(n*8+4).readS32()});
    if(!v.isNull())freeNativeArray(v);
    function center(connector){const x=Memory.alloc(4),y=Memory.alloc(4);native('Od101dll.dll','?GetCenter@CODConnector@@UAEXAAH0@Z','void',['pointer','pointer','pointer'])(connector,x,y);return {x:x.readS32(),y:y.readS32()};}
    result.push({id:object.toString(),source:{id:source.toString(),...pins.get(source.toString()),...center(source)},target:{id:target.toString(),...pins.get(target.toString()),...center(target)},points,has_pen:!wirePen(object).isNull()});
  }
  return {path:projectPath(d.proj),wires:result};
}
function freeNativeArray(value) {
  // GetVertices allocates a CPoint[] copy; MFC export 266 is the imported delete[] used by this build.
  if(!functions.has('nativeDeleteArray')) {
    const getProc=ptrFunction('kernel32.dll','GetProcAddress',['pointer','pointer'],'stdcall');
    const address=getProc(Process.getModuleByName('mfc140u.dll').base,ptr(266));
    if(address.isNull())throw new Error('The matching native array deallocator is unavailable');
    functions.set('nativeDeleteArray',new NativeFunction(address,'void',['pointer'],'mscdecl'));
  }
  functions.get('nativeDeleteArray')(value);
}
function inspect() {
  const p = project();
  return { pid: Process.id, arch: Process.arch, projectPath: projectPath(p.proj), projectType: rtti(p.proj),
    modified:!!native('DrwEngine.dll','?IsModified@CProject@@QAE_NXZ','uint8',['pointer'])(p.proj),
    officialAutomation: false, screenshotOrMouse: false };
}
function runJob(job) {
  activeNativeOperation=job.name;
  try {
    clearTimeout(job.timer);
    const handlers = { inspect, enumerate, components, wires, markModified:()=>{native('DrwEngine.dll','?SetAllModified@CProject@@QAEX_N@Z','void',['pointer','uint8'])(project().proj,1);return {modified:true};}, prepareClose:()=>{native('DrwEngine.dll','?SetAllModified@CProject@@QAEX_N@Z','void',['pointer','uint8'])(project().proj,0);return {ready:true};}, move:()=>move(job.args), save:()=>save(job.args), wire:()=>wire(job.args), diagramInfo: () => { const d=diagram();return {sheet:d.sheet.toString(),graph:d.graph.toString(),graphType:rtti(d.graph),candidates:d.candidates}; } };
    const handler=handlers[job.name] || (editorHandlers[job.name] && (()=>editorHandlers[job.name](job.args)));
    if (!handler) throw new Error('Unknown native operation');
    const result = handler();
    setImmediate(() => job.resolve(result));
  } catch (error) { setImmediate(() => job.reject(error)); }
  finally {activeNativeOperation=null;}
}
const drw = Process.getModuleByName('DrwEngine.dll');
const engine = ptrFunction('DrwEngine.dll', '?GetEngineInterface@CEngineInterface@@SAPAV1@XZ', [], 'mscdecl')();
let hwnd = ptrFunction('DrwEngine.dll', '?GetMainWndHandle@CEngineInterface@@IAEPAUHWND__@@XZ', ['pointer'])(engine);
const user = Process.getModuleByName('user32.dll');
// The persistent Netlist Viewer also regenerates on idle, outside an RPC. Keep
// native error collection intact, but use its own noninteractive reporting mode.
// These process-local hooks are removed on detach; no preferences are changed.
const circexp=Process.getModuleByName('CIRCEXP.dll');
Interceptor.attach(circexp.getExportByName('?ErrorInfoBegin@CiaSpiceTmpltExprt@@SAX_N@Z'),{onEnter(args){args[0]=ptr(0);}});
const errorAdd=circexp.enumerateExports().find(e=>e.name.startsWith('?ErrorInfoAdd@CiaSpiceTmpltExprt@@'));
Interceptor.attach(errorAdd.address,{onEnter(args){
  const entry={operation:activeNativeOperation||'background-netlist-viewer',text:args[0].readPointer().readUtf16String()};
  nativeErrorLog.push(entry);send({netlist_error:entry});
}});
const windowThread = new NativeFunction(user.getExportByName('GetWindowThreadProcessId'), 'uint', ['pointer', 'pointer'], 'stdcall');
if (hwnd.isNull()) {
  const owner = Memory.alloc(4);
  const getParent = new NativeFunction(user.getExportByName('GetWindow'), 'pointer', ['pointer', 'uint'], 'stdcall');
  const getClass = new NativeFunction(user.getExportByName('GetClassNameW'), 'int', ['pointer','pointer','int'], 'stdcall');
  const cb = new NativeCallback(w => {
    windowThread(w, owner);
    const className=Memory.alloc(256);getClass(w,className,128);
    if (owner.readU32() === Process.id && /^Multisim\d/.test(className.readUtf16String()) && getParent(w, 4).isNull()) { hwnd = w; return 0; }
    return 1;
  }, 'int', ['pointer', 'int'], 'stdcall');
  keep.push(cb);
  new NativeFunction(user.getExportByName('EnumWindows'), 'int', ['pointer', 'int'], 'stdcall')(cb, 0);
}
const uiThread = windowThread(hwnd, ptr(0)) || Process.enumerateThreads()[0].id;
const wake = new NativeFunction(user.getExportByName('PostThreadMessageW'), 'int', ['uint', 'uint', 'uint', 'int'], 'stdcall');
let draining = false;
function drain() {
  if (draining || Process.getCurrentThreadId() !== uiThread) return;
  draining = true;
  try { const job = jobs.shift(); if (job) runJob(job); } finally { draining = false; }
}
// Dispatch a native window timer on the owning UI thread. Do not hook the application's message pump.
const timerCallback=new NativeCallback(()=>drain(),'void',['pointer','uint','uint','uint'],'stdcall');
keep.push(timerCallback);
const setTimer=new NativeFunction(user.getExportByName('SetTimer'),'uint',['pointer','uint','uint','pointer'],'stdcall');
const killTimer=new NativeFunction(user.getExportByName('KillTimer'),'int',['pointer','uint'],'stdcall');
if(hwnd.isNull())throw new Error('Native main window is not ready');
const timerId=setTimer(hwnd,0x4d4350,30,timerCallback);
if(!timerId)throw new Error('Native UI timer could not be created');
rpc.exports = {
  dispatch(name, args = {}) {
    return new Promise((resolve, reject) => {
      const job = { name, args, resolve, reject };
      job.timer=setTimeout(()=>{const i=jobs.indexOf(job);if(i>=0)jobs.splice(i,1);reject(new Error('Native host did not process the request within 15 seconds'));},15000);
      jobs.push(job);
      if (!wake(uiThread, 0, 0, 0)) { jobs.splice(jobs.indexOf(job), 1); reject(new Error('Native host UI thread could not be scheduled')); }
    });
  },
  close() { killTimer(hwnd,timerId);return true; },
  identity() { return { pid: Process.id, uiThread, hwnd: hwnd.toString(), nativeModules: Process.enumerateModules().length }; }
  ,diagnostics(){return {netlist_errors:nativeErrorLog.slice(-100)};}
};
