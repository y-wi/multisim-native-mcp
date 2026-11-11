// Additional native editor operations. Kept in the same Frida realm as host_agent.js.
const prefixFunctions=new Map();
let doubleGetter=null;
function parameterDouble(attr,index) {
  if(!doubleGetter) {
    const target=Process.getModuleByName('CIRCEXP.dll').getExportByName('?GetParam@CiaParamList@@QBENH@Z').toUInt32();
    const bytes=[0x55,0x8b,0xec,0x8b,0x4d,8,0xff,0x75,12,0xb8,...[0,8,16,24].map(n=>(target>>>n)&255),0xff,0xd0,0x8b,0x45,16,0xdd,0x18,0x8b,0xe5,0x5d,0xc2,12,0];
    const code=Memory.alloc(Process.pageSize);code.writeByteArray(bytes);Memory.protect(code,Process.pageSize,'r-x');keep.push(code);
    doubleGetter=new NativeFunction(code,'void',['pointer','int','pointer'],'stdcall');
  }
  const out=Memory.alloc(8);doubleGetter(attr,index,out);return out.readDouble();
}
function method(dll,prefix,result,args,abi='thiscall') {
  const key=[dll,prefix,result,args,abi].join('|');
  if(!prefixFunctions.has(key)) {
    const exports=Process.getModuleByName(dll).enumerateExports(),exact=exports.find(e=>e.name===prefix);
    const matches=exact?[exact]:exports.filter(e=>e.name.startsWith(prefix));
    if(matches.length!==1)throw new Error('Expected one native method: '+dll+' '+prefix+'; found '+matches.length);
    prefixFunctions.set(key,native(dll,matches[0].name,result,args,abi));
  }
  return prefixFunctions.get(key);
}
function treeInstance() {const d=diagram();return method('DrwEngine.dll','?GetFirstTreeInstanceForSheet@CProject@@','pointer',['pointer','pointer'])(d.proj,d.sheet);}
function activateSheet() {
  const view=method('DrwEngine.dll','?ShowSheet@CProject@@','pointer',['pointer','uint8','uint8'],'mscdecl')(treeInstance(),0,1);
  return view;
}
function ciObject(object) {return method('Od101dll.dll','?GetCiComponent@CIITSymbolComp@@','pointer',['pointer'])(basePointer(object,'.?AUIRefDesable@@'));}
function extension() {
  const p=project().proj,count=method('DrwEngine.dll','?GetExtensionCount@CProject@@','uint',['pointer'])(p);
  for(let n=0;n<count;n++){const e=method('DrwEngine.dll','?GetExtensionByIndex@CProject@@','pointer',['pointer','uint'])(p,n);if(/CMultisimExtension/.test(rtti(e).name))return e;}
  throw new Error('Native Multisim project extension not found');
}
function initializeProject() {
  const p=project().proj,type=method('SCH_CAP.dll','?GetThisClass@CMultisimExtension@@','pointer',[],'stdcall')();
  const ext=method('DrwEngine.dll','?GetOrCreateExtension@CProject@@','pointer',['pointer','pointer'])(p,type);
  method('DrwEngine.dll','?InitializeExtensions@CProject@@','void',['pointer'])(p);
  method('DrwEngine.dll','?BuildTreeInstances@CProject@@','void',['pointer'])(p);cachedDiagram=null;
  return {tree:treeInstance().toString(),ext:ext.toString()};
}
function readCStringResult(fn,args) {
  const result=Memory.alloc(4);result.writePointer(ptr(0));fn(result,...args);
  const p=result.readPointer(),value=p.isNull()?'':p.readUtf16String();
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(result);return value;
}
function instanceString(dll,prefix,object,args=[],types=[]) {
  const fn=method(dll,prefix,'pointer',['pointer','pointer',...types]);
  return readCStringResult((out,...a)=>fn(object,out,...a),args);
}
function parameterInfo(args,source=null) {
  const c=source||component(args.ref),ci=ciObject(ptr(c.id));
  const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2);
  const parameters=[];
  if(!attr.isNull() && /CiaParamList/.test(rtti(attr).name)) {
    const count=method('CIRCEXP.dll','?GetParamCount@CiaParamList@@','int',['pointer'])(attr);
    const exprCount=method('CIRCEXP.dll','?GetExprParamCount@CiaParamList@@','int',['pointer'])(attr);
    for(let n=0;n<Math.min(256,Math.max(count,exprCount));n++)parameters.push({index:n,value:n<count?parameterDouble(attr,n):null,expression:n<exprCount?instanceString('CIRCEXP.dll','?GetExprParam@CiaParamList@@',attr,[n],['int']):null});
  }
  const info=[];
  const coll=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,4);
  if(!coll.isNull() && /CiaCollString/.test(rtti(coll).name)) {
    for(let n=0;n<5;n++)info.push(instanceString('CIRCEXP.dll','?GetParam@CiaCollString@@',coll,[n],['int']));
  }
  const descriptor={RESISTOR_VIRTUAL:['resistance','Ohm'],CAPACITOR_VIRTUAL:['capacitance','F'],INDUCTOR_VIRTUAL:['inductance','H'],DC_POWER:['voltage','V']}[info[1]];
  if(descriptor)for(const p of parameters){if(p.index===1)Object.assign(p,{name:descriptor[0],unit:descriptor[1],role:'value'});else if(p.index===0)p.role='model_option';}
  return {ref:c.ref,ci:ci.toString(),info,parameters};
}
function setParameter(args) {
  const before=parameterInfo(args),c=component(args.ref),ci=ciObject(ptr(c.id));
  if(!before.parameters.some(p=>p.index===args.index))throw new Error('Parameter index does not exist');
  if(args.expression!==undefined) {
    const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2),text=pathString(args.expression);
    const ok=method('CIRCEXP.dll','?SetExprParam@CiaParamList@@','uint8',['pointer','int','pointer','int'])(attr,args.index,text,1);
    native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
    if(!ok)throw new Error('Native expression setter rejected the value');
  } else {
    method('CIRCEXP.dll','?SetDoubleParam@CiElement@@','void',['pointer','double','int'])(ci,args.value,args.index);
    const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2),text=pathString(String(args.value));
    method('CIRCEXP.dll','?SetExprParam@CiaParamList@@','uint8',['pointer','int','pointer','int'])(attr,args.index,text,1);
    native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
  }
  const labels=refreshComponentValue(c.id,true);
  return {before,after:parameterInfo({ref:c.id}),labels};
}
function replaceComponent(args) {
  const old=component(args.ref),attached=wires().wires.filter(w=>w.source.ref===old.ref||w.target.ref===old.ref);
  let temporary='MCP_REPLACEMENT';while(components().components.some(c=>c.ref===temporary))temporary+='X';
  const created=placeComponent({...args,ref:temporary,x:Math.round(old.transform[4]),y:Math.round(old.transform[5])}).component;
  copyTransform(ptr(old.id),ptr(created.id),old.transform[4],old.transform[5]);
  const pinMap=args.pin_map||{};
  for(const w of attached)for(const end of ['source','target'])if(w[end].ref===old.ref && !created.pins.some(p=>p.name===(pinMap[w[end].pin]||w[end].pin)))throw new Error('Replacement has no matching pin '+w[end].pin+'; provide pin_map');
  for(const w of attached)removeObject({id:w.id});removeObject({ref:old.ref});
  renameComponent({ref:created.id,new_ref:old.ref});
  const links=[];
  for(const w of attached){const endpoints={};for(const end of ['source','target'])endpoints[end]=w[end].ref===old.ref?{ref:old.ref,pin:pinMap[w[end].pin]||w[end].pin}:w[end].ref?{ref:w[end].ref,pin:w[end].pin}:{junction_id:w[end].id};links.push(connectEndpoint(endpoints));}
  return {component:component(old.ref),reconnected_wires:links.length};
}
function renameComponent(args) {
  if(components().components.some(c=>c.ref===args.new_ref))throw new Error('Reference already exists');
  const c=component(args.ref),mgr=method('SCH_CAP.dll','?GetRefDesMgr@CMultisimExtension@@','pointer',['pointer','uint'])(extension(),0),text=pathString(args.new_ref);
  method('SCH_CAP.dll','?RenameComponent@CIITHierRefDesManager@@','void',['pointer','pointer','pointer','pointer'])(mgr,ptr(c.id),treeInstance(),text);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
  let after=component(c.id);
  if(after.ref!==args.new_ref && after.local_ref!==args.new_ref) {
    method('CIRCEXP.dll','?SetLocalName@CiElement@@','int',['pointer','pointer'])(ciObject(ptr(c.id)),Memory.allocUtf16String(args.new_ref));
    method('SCH_CAP.dll','?SyncRefDesManager@CMultisimExtension@@','int',['pointer','uint8'])(extension(),1);
    after=component(c.id);
  }
  if(after.ref!==args.new_ref && after.local_ref!==args.new_ref)throw new Error('Native reference rename did not persist');
  return after;
}
function copyComponent(args) {
  const source=component(args.ref),cache=method('SCH_CAP.dll','?GetDBCache@CMultisimExtension@@','pointer',['pointer'])(extension()),retriever=Memory.alloc(256);
  method('SCH_CAP.dll','??0CComponentInfoRetrieve@@','pointer',['pointer','pointer'])(retriever,cache);
  try {
    const record=method('SCH_CAP.dll','?RetrieveComponentInfoFromDB@CComponentInfoRetrieve@@','pointer',['pointer','pointer'])(retriever,ciObject(ptr(source.id)));
    if(record.isNull())throw new Error('Native component record could not be retrieved');
    const result=generateRecord(record,{...args,ref:args.new_ref});
    if(JSON.stringify(source.pins.map(p=>p.name))!==JSON.stringify(result.component.pins.map(p=>p.name)))throw new Error('Native copied section has a different pin map; use explicit library placement for this section');
    // The retrieved record preserves graphics but leaves CiPort names empty in
    // this build. Restore their original native order/names before any wiring.
    const sourceCi=ciObject(ptr(source.id)),targetCi=ciObject(ptr(result.component.id));
    const count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(sourceCi);
    if(count!==method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(targetCi))throw new Error('Native copy electrical port count mismatch');
    for(let n=0;n<count;n++){
      const getPort=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int']);
      const name=returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',getPort(sourceCi,n));
      if(!name)throw new Error('Source component has an unnamed electrical port');
      method('CIRCEXP.dll','?SetLocalName@CiElement@@','int',['pointer','pointer'])(getPort(targetCi,n),Memory.allocUtf16String(name));
    }
    copyTransform(ptr(source.id),ptr(result.component.id),args.x,args.y);
    const params=parameterInfo({ref:source.id});
    for(const p of params.parameters)if(p.expression!==null)setParameter({ref:result.component.id,index:p.index,expression:p.expression});else if(p.value!==null)setParameter({ref:result.component.id,index:p.index,value:p.value});
    return {component:component(result.component.id)};
  } finally {method('SCH_CAP.dll','??1CComponentInfoRetrieve@@','void',['pointer'])(retriever);}
}
function removeObject(args) {
  let id=args.id;
  if(args.ref)id=component(args.ref).id;
  if(!enumerate().objects.some(c=>c.id===id))throw new Error('Object does not exist on the selected sheet');
  const symbol=components().components.find(c=>c.id===id);
  if(symbol)for(const wire of wires().wires.filter(w=>w.source.ref===symbol.ref||w.target.ref===symbol.ref))removeObject({id:wire.id});
  const list=Memory.alloc(256);
  method('Od101dll.dll','??0CODCompList@@QAE@PAVCODComponent@@@Z','pointer',['pointer','pointer'])(list,ptr(id));
  try {
    method('SCH_CAP.dll','?DoDelete@CIITDiagram@@QAEHPAVCTreeInstance@@PAVCODCompList@@_N2222PAVCIITView@@PAVCNetSplitInfo@@@Z','int',['pointer','pointer','pointer',...Array(5).fill('uint8'),'pointer','pointer'])(diagram().graph,treeInstance(),list,0,1,0,0,0,activateSheet(),ptr(0));
  } finally {method('Od101dll.dll','??1CODCompList@@UAE@XZ','void',['pointer'])(list);}
  return {deleted:!enumerate().objects.some(c=>c.id===id),id};
}
function updateAttachedGeometry(ref,attached) {
  const pins=component(ref).pins;
  for(const wire of attached) {
    let points=wire.points;
    for(const end of ['source','target'])if(wire[end].ref===ref) {
      const pin=pins.find(p=>p.id===wire[end].id);if(!pin)throw new Error('Transformed pin lost its attachment');
      if(end==='source')points=points.slice().reverse();
      const old=points.at(-1),previous=points.at(-2),next={x:pin.x,y:pin.y};
      const corner=previous.y===old.y?{x:next.x,y:old.y}:{x:old.x,y:next.y};
      points=[...points.slice(0,-1),corner,next].filter((p,i,a)=>!i||p.x!==a[i-1].x||p.y!==a[i-1].y);
      if(end==='source')points.reverse();
    }
    setWirePoints(ptr(wire.id),points);
  }
  return pins;
}
function transformComponent(args) {
  const c=component(args.ref),object=ptr(c.id),before=matrix(object),attached=wires().wires.filter(w=>w.source.ref===c.ref||w.target.ref===c.ref);
  const x=c.pins.length?c.pins.reduce((a,p)=>a+p.x,0)/c.pins.length:before[4],y=c.pins.length?c.pins.reduce((a,p)=>a+p.y,0)/c.pins.length:before[5];
  const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(object);
  if(args.angle!==undefined)method('Od101dll.dll','?Rotate@CODGraphic@@','void',['pointer','float','float','float'])(graphic,args.angle,x,y);
  else method('Od101dll.dll','?Scale@CODGraphic@@','void',['pointer','float','float','float','float'])(graphic,args.axis==='horizontal'?-1:1,args.axis==='vertical'?-1:1,x,y);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,object,0,0);
  refreshComponentValue(c.id,false);
  straightenComponentLabels(c.id);
  arrangeComponentLabels(c.id);
  return {ref:c.ref,before,after:matrix(object),pins:updateAttachedGeometry(c.ref,attached),labels:componentLabels({ref:c.id}).labels};
}
function copyTransform(source,target,x,y) {
  const graphic=object=>method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(object);
  const transform=object=>method('Od101dll.dll','?GetTransformer@CODGraphic@@QAEP','pointer',['pointer'])(graphic(object));
  const st=transform(source),tt=transform(target);if(st.isNull()||tt.isNull())throw new Error('Native component transform unavailable');
  method('Od101dll.dll','??4CODTransformer@@QAEAAV0@ABV0@@Z','pointer',['pointer','pointer'])(tt,st);
  const current=matrix(target);
  const dx=Math.round(x-current[4]),dy=Math.round(y-current[5]);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,target,dx,dy);
}
function routeWire(args) {
  const w=wires().wires.find(w=>w.id===args.id);if(!w)throw new Error('Wire ID does not exist');
  if(args.points.length<2)throw new Error('At least two route points are required');
  for(const [endpoint,index] of [['source',0],['target',args.points.length-1]]) {
    const x=Memory.alloc(4),y=Memory.alloc(4);
    method('Od101dll.dll','?GetCenter@CODConnector@@UAEXAAH0','void',['pointer','pointer','pointer'])(ptr(w[endpoint].id),x,y);
    if(args.points[index].x!==x.readS32()||args.points[index].y!==y.readS32())throw new Error('Route endpoints must match the attached native connectors');
  }
  setWirePoints(ptr(w.id),args.points);
  return wires().wires.find(w=>w.id===w.id&&w.id===args.id);
}
function repairWireGeometry() {
  const before=wires().wires,changed=[],alignedComponents=[],alignedJunctions=[];
  const moveNative=method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int']);
  for(const c of components().components)if(c.pins.some(p=>!p.graphics_aligned)||c.transform.slice(4).some(v=>Math.abs(v-Math.round(v))>.0001)){
    moveNative(diagram().graph,ptr(c.id),0,0);alignedComponents.push(c.ref);
  }
  const junctions=new Map();
  for(const wire of before)for(const end of ['source','target'])if(!wire[end].ref)junctions.set(wire[end].id,wire[end]);
  for(const [id,j] of junctions)if(!j.graphics_aligned){
    moveNative(diagram().graph,ptr(id),Math.round(j.x-j.graphic_position.x),Math.round(j.y-j.graphic_position.y));alignedJunctions.push(id);
  }
  const selected=wires().wires;
  for(const wire of selected){
    if(wire.points.length<2)throw new Error('Wire '+wire.id+' has no editable route');
    let points=wire.points.map(p=>({...p}));
    for(const end of ['source','target']){
      if(end==='target')points.reverse();
      const old=points[0],next=points[1],actual={x:wire[end].x,y:wire[end].y};
      if(points.length>2){if(old.x===next.x)next.x=actual.x;else if(old.y===next.y)next.y=actual.y;}
      points[0]=actual;
      if(end==='target')points.reverse();
    }
    if(points.length===2&&points[0].x!==points[1].x&&points[0].y!==points[1].y)points.splice(1,0,{x:points[0].x,y:points[1].y});
    points=points.filter((p,i,a)=>!i||p.x!==a[i-1].x||p.y!==a[i-1].y);
    if(points.length===1)points.push({...points[0]});
    if(JSON.stringify(points)===JSON.stringify(wire.points))continue;
    setWirePoints(ptr(wire.id),points);changed.push(wire.id);
  }
  const after=wires().wires,lookup=new Map(after.map(w=>[w.id,w]));
  const intact=before.length===after.length&&before.every(w=>{const a=lookup.get(w.id);return a&&a.source.id===w.source.id&&a.target.id===w.target.id;});
  if(!intact)throw new Error('Wire geometry repair changed an electrical connection');
  const mismatches=selected.filter(w=>{const a=lookup.get(w.id);return ['source','target'].some((end,i)=>{const p=a.points[i?a.points.length-1:0];return p.x!==a[end].x||p.y!==a[end].y;});}).map(w=>w.id);
  const graphics=after.flatMap(w=>['source','target'].filter(end=>!w[end].graphics_aligned).map(end=>({wire:w.id,end})));
  if(mismatches.length||graphics.length)throw new Error('Geometry repair left '+mismatches.length+' route and '+graphics.length+' graphic endpoint mismatches');
  if(changed.length||alignedComponents.length||alignedJunctions.length)method('DrwEngine.dll','?SetAllModified@CProject@@','void',['pointer','uint8'])(project().proj,1);
  return {checked_wires:selected.length,changed_wires:changed.length,wire_ids:changed,aligned_components:alignedComponents,aligned_junctions:alignedJunctions,electrical_connections_unchanged:intact,remaining_mismatches:mismatches,remaining_graphic_mismatches:graphics};
}
function readSheets() {
  const d=diagram();
  return d.candidates.filter(s=>/CSCH_CAPSubSheet/.test(s.name)).map((s,index)=>{
    const title=method('DrwEngine.dll','?GetTitle@CDrwSubSheet@@','pointer',['pointer'])(s.pointer).readPointer().readUtf16String();
    const page=method('DrwEngine.dll','?GetPageName@CDrwSubSheet@@','pointer',['pointer'])(s.pointer).readPointer().readUtf16String();
    const doc=method('SCH_CAP.dll','?GetDocument@CSCH_CAPSubSheet@@','pointer',['pointer'])(s.pointer);
    const graph=doc.isNull()?ptr(0):method('SCH_CAP.dll','?GetDiagram@CSCH_CAPDoc@@','pointer',['pointer'])(doc);
    return {index,id:s.pointer.toString(),title,page,selected:s.pointer.equals(d.sheet),...(graph.isNull()?{width:null,height:null,bounds:null}:pageGeometry(graph))};
  });
}
function pageGeometry(graph=diagram().graph) {
  const values=Array.from({length:6},()=>Memory.alloc(4));
  method('Od101dll.dll','?GetPageInfo@CODDiagram@@','void',['pointer',...Array(6).fill('pointer')])(graph,...values);
  const prefs=new NativeFunction(graph.readPointer().add(0x5c).readPointer(),'pointer',['pointer'],'thiscall')(graph);
  if(prefs.isNull())throw new Error('Sheet preferences are unavailable');
  const read=key=>{const name=pathString(key),out=Memory.alloc(8);out.writeDouble(0);
    if(!method('PREFS.dll','?GetPrefsAsDouble@CPreferences@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),out))throw new Error('Missing sheet preference: '+key);return out.readDouble();};
  const width=Math.round(read('Sheet Width')),height=Math.round(read('Sheet Height'));
  return {width,height,units:'sheet_units',units_per_inch:96,origin:{x:0,y:0},bounds:{left:0,top:0,right:width,bottom:height},
    paper_width:Math.round(values[1].readFloat()*96),paper_height:Math.round(values[0].readFloat()*96)};
}
function selectSheet(args) {
  const sheets=readSheets(),sheet=sheets.find(s=>args.id?s.id===args.id:s.index===args.index);
  if(!sheet)throw new Error('Schematic sheet not found');selectedSheetId=sheet.id;cachedDiagram=null;objectHandles.clear();
  activateSheet();
  const info=components();return {sheet,path:info.path,component_count:info.components.length};
}
function projects() {
  const p=project(),count=method('DrwEngine.dll','?GetProjectCount@CWorkSpace@@','uint',['pointer'])(p.workspace),result=[];
  for(let index=0;index<count;index++){const obj=ptrFunction('DrwEngine.dll','?GetProject@CWorkSpace@@QAEPAVCProject@@I@Z',['pointer','uint'])(p.workspace,index);result.push({index,id:obj.toString(),path:projectPath(obj),selected:index===selectedProjectIndex});}
  return {projects:result};
}
function selectProject(args) {
  if(!projects().projects.some(p=>p.index===args.index))throw new Error('Project index not found');
  selectedProjectIndex=args.index;selectedSheetId=null;cachedDiagram=null;activateSheet();return inspect();
}
function createSheet(args) {
  const d=diagram(),root=d.candidates.find(s=>s.name==='.?AVCDrwSubSheet@@')||d.candidates[0];
  const kind=Memory.alloc(64),name=pathString(args.title),page=pathString(args.page||String(readSheets().length+1));
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(kind,Memory.allocUtf16String('SCH_CAPDESIGN'));
  const sheet=method('DrwEngine.dll','?CreateNewTarget@CProject@@','pointer',['pointer','pointer','pointer','pointer','pointer','int','uint','uint8','pointer'])(d.proj,root.pointer,kind,name,page,0,0,0,ptr(0));
  method('Library.dll','??1CPoolString@@','void',['pointer'])(kind);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(page);
  if(sheet.isNull())throw new Error('Native sheet creation returned null');cachedDiagram=null;
  if(!method('SCH_CAP.dll','?OnNewDocument@CSCH_CAPSubSheet@@','uint8',['pointer'])(sheet))throw new Error('New sheet document initialization failed');
  return readSheets();
}
function newProject(args) {
  const before=projects().projects;
  const path=pathString(args.path),title=pathString(args.title||'MCP Circuit');
  const type=method('DrwEngine.dll','?GetThisClass@CDrwSubSheet@@','pointer',[],'stdcall')();
  const created=method('DrwEngine.dll','?CreateNewProject@CWorkSpace@@','pointer',['pointer','pointer','pointer','pointer','uint8'])(project().workspace,path,title,type,1);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(path);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(title);
  if(created.isNull())throw new Error('Native new-project command failed');
  const after=projects().projects,newest=after.find(p=>!before.some(b=>b.id===p.id));
  if(!newest)throw new Error('New native project was not found');selectedProjectIndex=newest.index;selectedSheetId=null;cachedDiagram=null;
  const vector=Memory.alloc(12);vector.writeByteArray(new Uint8Array(12));
  method('DrwEngine.dll','?GetAllSheetsInProject@CProject@@','void',['pointer','pointer'])(created,vector);
  const root=vector.readPointer().readPointer(),kind=Memory.alloc(64),sheetTitle=pathString(args.title||'MCP Circuit'),page=pathString('1');
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(kind,Memory.allocUtf16String('SCH_CAPDESIGN'));
  const sheet=method('DrwEngine.dll','?CreateNewTarget@CProject@@','pointer',['pointer','pointer','pointer','pointer','pointer','int','uint','uint8','pointer'])(created,root,kind,sheetTitle,page,0,0,0,ptr(0));
  method('Library.dll','??1CPoolString@@','void',['pointer'])(kind);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(sheetTitle);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(page);
  if(!method('SCH_CAP.dll','?OnNewDocument@CSCH_CAPSubSheet@@','uint8',['pointer'])(sheet))throw new Error('New project document initialization failed');
  initializeProject();cachedDiagram=null;activateSheet();
  return {...inspect(),sheets:readSheets(),component_count:components().components.length};
}
function setProjectPath(path) {
  const value=pathString(path);
  const ok=method('DrwEngine.dll','?SetProjectFilePath@CProject@@','uint8',['pointer','pointer','uint8','uint8'])(project().proj,value,0,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);return !!ok;
}
function snapshot(args) {
  const original=projectPath(project().proj),modified=inspect().modified,result=save({...args,preserve_geometry:true});
  if(!setProjectPath(original))throw new Error('Unable to restore project path after checkpoint');
  if(modified)method('DrwEngine.dll','?SetAllModified@CProject@@','void',['pointer','uint8'])(project().proj,1);
  return {...result,original_path:original,modified};
}
function restoreSnapshot(args) {
  const p=project();
  method('DrwEngine.dll','?SetAllModified@CProject@@','void',['pointer','uint8'])(p.proj,0);
  const closed=method('DrwEngine.dll','?FileCloseProject@CWorkspaceContainer@@','int',['pointer','pointer','uint8'])(p.container,p.proj,0);
  selectedSheetId=null;cachedDiagram=null;objectHandles.clear();
  const value=pathString(args.path);
  const opened=method('DrwEngine.dll','?FileOpen@CWorkspaceContainer@@QAE?AW4EOpenResult@1@ABVCPathString@@_N1@Z','int',['pointer','pointer','uint8','uint8'])(p.container,value,0,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);
  const target=projects().projects.find(p=>p.path.toLowerCase()===args.path.toLowerCase());
  if(!target)throw new Error('Restored native project was not found');selectedProjectIndex=target.index;cachedDiagram=null;
  if(args.original_path)setProjectPath(args.original_path);
  if(args.sheet_index!==undefined)selectSheet({index:args.sheet_index});
  if(args.modified)method('DrwEngine.dll','?SetAllModified@CProject@@','void',['pointer','uint8'])(project().proj,1);
  return {closed,opened,...inspect(),components:components().components.length};
}
function masterDb() {
  const h=method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')();
  const group=method('SCH_CAP.dll','?GetDatabasePtrGroup@CComponentHandler@@','pointer',['pointer'])(h);
  if(!method('Database.dll','?GetLoadedDBCount@CDatabasePtrGroup@@','uint',['pointer'])(group)) {
    const manager=method('LibraryAccess.dll','?GetDatabaseManager@CDatabaseManager@@SAP','pointer',[],'mscdecl')();
    const files=method('LibraryAccess.dll','?GetDatabaseFileManager@CDatabaseManager@@','pointer',['pointer'])(manager);
    method('Database.dll','?OpenDatabases@CDatabasePtrGroup@@','uint',['pointer','uint8','pointer','pointer'])(group,0,files,ptr(0));
  }
  const db=method('Database.dll','?GetDbPtrMaster@CDatabasePtrGroup@@','pointer',['pointer'])(group);
  if(db.isNull())throw new Error('Master component library is unavailable');return db;
}
function librarySearch(args) {
  const db=masterDb(),limit=Math.min(100,Math.max(1,args.limit||20)),term=(args.query||'').replace(/'/g,"''");
  const filters=[];
  if(term)filters.push("c.Component_Name LIKE '*"+term+"*'");
  if(args.family)filters.push("f.Family_Name='"+args.family.replace(/'/g,"''")+"'");
  if(args.group)filters.push("g.Family_Group='"+args.group.replace(/'/g,"''")+"'");
  const sql=pathString("SELECT TOP "+limit+" c.Component_Name, c.Component_ID, c.Family_ID, f.Family_Name, g.Family_Group AS Group_Name FROM (SYS_COMPONENT AS c LEFT JOIN SYS_CONFIGURATION AS f ON c.Family_ID=f.Family_ID) LEFT JOIN SYS_CONFIGURATION_GROUPS AS g ON f.Family_Group_ID=g.Family_Group_ID"+(filters.length?' WHERE '+filters.join(' AND '):'')+" ORDER BY c.Component_Name");
  method('Database.dll','?OpenSQLDirectSet@CDBComponent@@','void',['pointer','pointer'])(db,sql.readPointer());
  const results=[];
  try {
    if(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db))method('Database.dll','?MoveFirstRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
    while(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db)&&results.length<limit) {
      const item={};
      for(const column of ['Component_Name','Family_Name','Group_Name']) {
        const key=pathString(column),out=pathString('');
        const ok=method('Database.dll','?GetFieldValue_SQLDirectSet@CDBComponent@@QAE_NABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@AAV23@@Z','uint8',['pointer','pointer','pointer'])(db,key,out);
        if(ok)item[column]=out.readPointer().readUtf16String();
        native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(key);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(out);
      }
      for(const column of ['Component_ID','Family_ID']) {
        const key=pathString(column),out=Memory.alloc(4);out.writeS32(0);
        const ok=method('Database.dll','?GetFieldValue_SQLDirectSet@CDBComponent@@QAE_NABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@AAJ@Z','uint8',['pointer','pointer','pointer'])(db,key,out);
        if(ok)item[column]=out.readS32();native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(key);
      }
      results.push(item);method('Database.dll','?MoveNextRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
    }
  } finally {method('Database.dll','?CloseSQLDirectSet@CDBComponent@@','void',['pointer'])(db);}
  return {query:args.query,results};
}
function placeComponent(args) {
  masterDb();
  const handler=method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')(),record=Memory.alloc(2048);
  method('compedit.dll','??0CDataRecordComponent@@QAE@XZ','pointer',['pointer'])(record);
  const values=[args.family||'',args.group||'',args.name,args.manufacturer||''].map(pathString);
  try {
    const found=method('SCH_CAP.dll','?PrepDataRecordForNewComponent@CComponentHandler@@','uint8',['pointer','pointer','pointer','pointer','pointer','int','int','pointer','uint8'])(handler,...values,0,-1,record,0);
    if(!found)throw new Error('The native library could not resolve this component name/family/group');
    return generateRecord(record,args);
  } finally {for(const v of values)native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(v);method('compedit.dll','??1CDataRecordComponent@@UAE@XZ','void',['pointer'])(record);}
}
function generateRecord(record,args) {
  activateSheet();
  if(args.ref && components().components.some(c=>c.ref===args.ref))throw new Error('Reference already exists on this sheet');
  const d=diagram(),handler=method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')(),name=pathString(''),out=Memory.alloc(4);out.writePointer(ptr(0));
  if(treeInstance().isNull())throw new Error('Selected sheet has no native tree instance');
  // The first two integer arguments are section index and place flag, NOT coordinates.
  const result=method('SCH_CAP.dll','?GenerateNewComponentFromDataRecord@CComponentHandler@@','int',['pointer','pointer','pointer','int','int','pointer','pointer','int','int','pointer','pointer','pointer'])(handler,out,name,1,1,d.graph,treeInstance(),1,0,ptr(0),ptr(0),record);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);
  const object=out.readPointer();if(object.isNull())throw new Error('Native component factory returned null: '+result);
  let c=component(object.toString());
  const others=components().components.filter(p=>p.id!==c.id),stem=(c.local_ref.match(/^[A-Za-z_]+/)||['X'])[0];let suffix=1;
  while(others.some(p=>p.ref===stem+suffix))suffix++;
  const ref=args.ref||(!others.some(p=>p.ref===c.local_ref)?c.local_ref:stem+suffix);
  if(c.ref!==ref)renameComponent({ref:c.id,new_ref:ref});
  const origin=matrix(object),anchor=args.anchor||'origin';
  let point={x:origin[4],y:origin[5]};
  if(anchor==='pin'){
    point=c.pins.find(p=>p.name===args.pin);
    if(!point)throw new Error('Placement anchor pin not found: '+args.pin+'; available pins: '+c.pins.map(p=>p.name).join(', '));
  }else if(anchor==='center'){
    const b=symbolBodyBounds(c);point={x:(b.left+b.right)/2,y:(b.top+b.bottom)/2};
  }
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(d.graph,object,Math.round(args.x-point.x),Math.round(args.y-point.y));
  for(const parameter of args.parameters||[])setParameter({ref:c.id,...parameter});
  c=component(object.toString());
  const metadata=parameterInfo({ref:c.id});
  const body=symbolBodyBounds(c),actual=anchor==='pin'?c.pins.find(p=>p.name===args.pin):anchor==='center'?{x:(body.left+body.right)/2,y:(body.top+body.bottom)/2}:{x:c.transform[4],y:c.transform[5]};
  const placement={anchor,...(anchor==='pin'?{pin:args.pin}:{}),requested:{x:args.x,y:args.y},actual:{x:actual.x,y:actual.y},origin:{x:c.transform[4],y:c.transform[5]},body_bounds:body};
  const page=pageGeometry(),offPage=body.left<0||body.top<0||body.right>page.width||body.bottom>page.height;
  const warnings=offPage?[{code:'outside_page',reference:c.ref,message:'Component is outside the page; move the circuit inside or resize the sheet before saving. Image fit_content changes export framing only.'}]:[];
  for(const p of metadata.parameters)if(p.role==='value'&&p.value===null&&!p.expression?.trim())warnings.push({code:'unset_value',reference:c.ref,index:p.index,name:p.name,message:'Set the primary component value before analysis.'});
  return {component:{...c,library:{family:metadata.info[0],name:metadata.info[1],symbol_family:metadata.info[2],model:metadata.info[3]},default_reference_prefix:stem},parameters:metadata.parameters,page,
    placement,warnings};
}
function allocateObject(className,constructor,args,types) {
  const type=method('Od101dll.dll','?GetThisClass@'+className+'@@','pointer',[],'stdcall')();
  const size=type.add(4).readU32();if(size<4||size>65536)throw new Error('Invalid native object size');
  const getProc=ptrFunction('kernel32.dll','GetProcAddress',['pointer','pointer'],'stdcall');
  const address=getProc(Process.getModuleByName('mfc140u.dll').base,ptr(1511));
  const object=new NativeFunction(address,'pointer',['uint'],'mscdecl')(size);
  method('Od101dll.dll',constructor,'pointer',['pointer',...types])(object,...args);return object;
}
function addText(args) {
  const object=allocateObject('CODTextComp','??0CODTextComp@@QAE@PB_W@Z',[Memory.allocUtf16String(args.text)],['pointer']);
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(diagram().graph,object,args.x,args.y,treeInstance(),0);
  return {id:object.toString(),text:instanceString('Od101dll.dll','?GetText@CODTextComp@@',object,[treeInstance()],['pointer'])};
}
function labelWire(args) {
  const w=wires().wires.find(w=>w.id===args.id);if(!w)throw new Error('Wire does not exist');
  const node=method('SCH_CAP.dll','?GetNode@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));
  const connection=basePointer(ptr(w.id),'.?AVCElectricalConnectionBase@@');
  const container=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(treeInstance());
  const proxy=Memory.alloc(128),pool=Memory.alloc(64);
  method('DrwEngine.dll','??0CTreeInstanceProxy@@QAE@PAVCTreeInstance@@@Z','pointer',['pointer','pointer'])(proxy,treeInstance());
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(pool,Memory.allocUtf16String(args.name));
  method('SchematicCapture.dll','?SetUserNamed@CElectricalConnectionBase@@','pointer',['pointer','pointer','pointer','pointer','uint8'])(connection,container,proxy,pool,1);
  method('SchematicCapture.dll','?SetNetNameHidden@CElectricalConnectionBase@@','void',['pointer','uint8'])(connection,0);
  method('Od101dll.dll','?SetShowWhenUsingNetSettings@CODLinkComp@@','void',['pointer','uint8'])(ptr(w.id),1);
  method('DrwEngine.dll','??1CTreeInstanceProxy@@','void',['pointer'])(proxy);method('Library.dll','??1CPoolString@@','void',['pointer'])(pool);
  let label=method('SCH_CAP.dll','?GetNodeText@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));
  if(label.isNull()) {
    label=allocateObject('CODNodeTextComp','??0CODNodeTextComp@@QAE@PB_W@Z',[Memory.allocUtf16String(args.name)],['pointer']);
    method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(diagram().graph,label,w.points[0].x,w.points[0].y-18,treeInstance(),0);
    method('SCH_CAP.dll','?SetNodeText@CIITLinkComp@@','void',['pointer','pointer'])(ptr(w.id),label);
    method('Od101dll.dll','?AddLinkComp@CODNodeTextComp@@','void',['pointer','pointer'])(label,ptr(w.id));
  }
  method('Od101dll.dll','?SetTextNoUpdate@CODTextComp@@','void',['pointer','pointer'])(label,Memory.allocUtf16String(args.name));
  return {id:w.id,node:node.toString(),name:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',node),label:label.toString()};
}
function modelInfo(args) {
  const ci=ciObject(ptr(component(args.ref).id)),model=method('CIRCEXP.dll','?GetModel@CiElement@@','pointer',['pointer'])(ci),attributes=[];
  if(model.isNull())return {ref:args.ref,model:null,attributes};
  for(let index=0;index<512;index++){
    const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(model,index);
    if(attr.isNull())continue;
    const item={index,type:rtti(attr).name};
    try{basePointer(attr,'.?AVCiaCString@@');item.text=method('CIRCEXP.dll','?GetString@CiaCString@@','pointer',['pointer'])(attr).readPointer().readUtf16String();}catch(_){}
    attributes.push(item);
  }
  return {ref:args.ref,model:model.toString(),attributes};
}
function setModelText(args) {
  const info=modelInfo(args);if(!info.model)throw new Error('Component has no explicit native SPICE model');
  const entry=info.attributes.find(a=>a.index===1&&a.text!==undefined);if(!entry)throw new Error('Native model is not a supported text model');
  const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ptr(info.model),1);
  const selected=selectedSheetId,affected=[];
  try {
    for(const sheet of readSheets()){
      selectedSheetId=sheet.id;cachedDiagram=null;
      for(const c of components().components)if(method('CIRCEXP.dll','?GetModel@CiElement@@','pointer',['pointer'])(ciObject(ptr(c.id))).toString()===info.model)affected.push({sheet_index:sheet.index,ref:c.ref});
    }
  } finally {selectedSheetId=selected;cachedDiagram=null;}
  method('CIRCEXP.dll','?SetString@CiaCString@@','int',['pointer','pointer'])(attr,Memory.allocUtf16String(args.text));
  method('CIRCEXP.dll','?SetChanged@CiModel@@','void',['pointer','int'])(ptr(info.model),1);
  return {before:entry.text,after:modelInfo(args).attributes.find(a=>a.index===1).text,affected_refs:affected};
}
function createSubcircuit(args) {
  const d=diagram(),parent=treeInstance(),kind=Memory.alloc(64),name=pathString(args.title),page=pathString('1');
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(kind,Memory.allocUtf16String('SCH_CAPDESIGN'));
  const sheet=method('DrwEngine.dll','?CreateNewTarget@CProject@@','pointer',['pointer','pointer','pointer','pointer','pointer','int','uint','uint8','pointer'])(d.proj,d.sheet,kind,name,page,0,0,0,ptr(0));
  method('Library.dll','??1CPoolString@@','void',['pointer'])(kind);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(page);
  if(sheet.isNull()||!method('SCH_CAP.dll','?OnNewDocument@CSCH_CAPSubSheet@@','uint8',['pointer'])(sheet))throw new Error('Native child sheet initialization failed');
  const tree=method('DrwEngine.dll','?GetFirstTreeInstanceForSheet@CProject@@','pointer',['pointer','pointer'])(d.proj,sheet);
  const sc=method('DrwEngine.dll','?GetSheetComponent@CTreeInstance@@','pointer',['pointer'])(tree);
  const doc=method('SCH_CAP.dll','?GetDocument@CSCH_CAPSubSheet@@','pointer',['pointer'])(sheet);
  const vtable=doc.readPointer();
  new NativeFunction(vtable.add(0x14c).readPointer(),'void',['pointer','uint8'],'thiscall')(doc,1);
  const symbol=new NativeFunction(vtable.add(0x184).readPointer(),'pointer',['pointer','uint8'],'thiscall')(doc,0);
  if(symbol.isNull())throw new Error('Native subcircuit symbol generation failed');
  const block=method('SCH_CAP.dll','?CreateObject@CHierBlock@@','pointer',[],'stdcall')();
  method('SCH_CAP.dll','?SetDocument@CHierBlock@@','void',['pointer','pointer'])(block,doc);
  method('SCH_CAP.dll','?SetSubcircuit@CHierBlock@@','void',['pointer','int'])(block,1);
  method('SCH_CAP.dll','?SetSheetComponent@CHierBlock@@','void',['pointer','pointer'])(block,sc);
  // These inline ownership links have no exported setters. Match the native
  // serializer's verified 14.3 layout (1ffc63-1ffca7), guarded by DLL hashes.
  symbol.add(0x15c).writePointer(block);symbol.add(0x160).writePointer(sc);
  symbol.add(0x164).writeU32(sc.add(0x10).readU32());sc.add(0xa4).writePointer(symbol);
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(d.graph,symbol,args.x,args.y,parent,0);
  renameComponent({ref:symbol.toString(),new_ref:args.ref||args.title});
  cachedDiagram=null;return {symbol_id:symbol.toString(),symbol_type:rtti(symbol),sheet_id:sheet.toString(),block:block.toString(),sheets:readSheets(),components:components().components};
}
function createPort(args) {
  const d=diagram(),tree=treeInstance(),container=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(tree);
  const factory=method('SCH_CAP.dll','?CreateHierConnectorFactory@CSCH_CAPSubSheet@@','pointer',['pointer','int','pointer'])(d.sheet,args.mode||0,container);
  if(factory.isNull())throw new Error('Native hierarchical connector factory is unavailable');
  const vector=Memory.alloc(12);vector.writeByteArray(new Uint8Array(12));
  const name=Memory.alloc(64),point=Memory.alloc(8);point.writeS32(args.x);point.add(4).writeS32(args.y);
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(name,Memory.allocUtf16String(args.name));
  const iface=new NativeFunction(factory.readPointer().readPointer(),'pointer',['pointer','pointer','pointer'],'thiscall')(factory,name,tree);
  const symbol=iface.isNull()?ptr(0):iface.sub(rtti(iface).offset);
  method('Library.dll','??1CPoolString@@','void',['pointer'])(name);
  if(symbol.isNull())throw new Error('Native hierarchical connector creation failed');
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(d.graph,symbol,args.x,args.y,tree,0);
  const parent=method('DrwEngine.dll','?GetParent@CTreeInstance@@','pointer',['pointer'])(tree),sc=method('DrwEngine.dll','?GetSheetComponent@CTreeInstance@@','pointer',['pointer'])(tree);
  const block=method('SCH_CAP.dll','?GetHierBlock@CSheetComponentMSM@@','pointer',['pointer'])(sc);
  if(!parent.isNull()&&!block.isNull())method('SCH_CAP.dll','?UpdateSymbol@CHierBlock@@','int',['pointer','pointer','uint8'])(block,parent,1);
  return {symbol_id:symbol.toString(),type:rtti(symbol),components:components().components};
}
function sheetTitle(args) {
  const name=pathString(args.title);
  method('DrwEngine.dll','?SetTitle@CDrwSubSheet@@','void',['pointer','pointer','uint8'])(diagram().sheet,name,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);return {sheets:readSheets()};
}
function sheetSize(args) {
  const d=diagram(),prefs=new NativeFunction(d.graph.readPointer().add(0x5c).readPointer(),'pointer',['pointer'],'thiscall')(d.graph);
  if(prefs.isNull())throw new Error('Selected diagram has no native circuit preferences');
  const floats=Array.from({length:6},()=>Memory.alloc(4));
  method('Od101dll.dll','?GetPageInfo@CODDiagram@@','void',['pointer',...Array(6).fill('pointer')])(d.graph,...floats);
  const before=floats.map(p=>p.readFloat());
  for(const [key,value] of Object.entries({'Sheet Width':args.width,'Sheet Height':args.height,'Sheet Width In Inch':args.width/96,'Sheet Height In Inch':args.height/96})) {
    // Native setters take CString by value and destroy those two copies.
    const name=pathString(key),text=pathString(String(value));
    method('PREFS.dll','?SetPrefsAsString@CIITCircuitPrefs@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),text.readPointer());
  }
  // CODDiagram's first two page-info fields are page height and page width.
  floats[0].writeFloat(args.height/96);floats[1].writeFloat(args.width/96);
  method('Od101dll.dll','?SetPageInfo@CODDiagram@@','void',['pointer',...Array(6).fill('pointer')])(d.graph,...floats);
  const rect=Memory.alloc(16),halfW=Math.round(args.width/96*25.4*500000),halfH=Math.round(args.height/96*25.4*500000);
  method('EwbBase.dll','??0CUTRect@@QAE@HHHH@Z','pointer',['pointer','int','int','int','int'])(rect,-halfW,halfH,halfW,-halfH);
  method('DrwEngine.dll','?SetWorkArea@CDrwSubSheet@@','void',['pointer','pointer'])(d.sheet,rect);
  return {width:args.width,height:args.height,before_page_info:before,page_info:floats.map(p=>p.readFloat())};
}
function connectNative(source,target,points) {
  let vector=ptr(0);
  if(points&&points.length){const values=Memory.alloc(points.length*8);points.forEach((p,n)=>{values.add(n*8).writeS32(p.x);values.add(n*8+4).writeS32(p.y);});vector=Memory.alloc(12);vector.writePointer(values);vector.add(4).writePointer(values.add(points.length*8));vector.add(8).writePointer(values.add(points.length*8));}
  const object=method('SCH_CAP.dll','?CreateWireBase@CBackAnnotationTarget@@','pointer',['pointer','pointer','pointer','pointer'],'mscdecl')(treeInstance(),source,target,vector);
  if(object.isNull())throw new Error('Native wire creation failed');
  ensureWirePen(object);
  const link=wires().wires.find(w=>w.id===object.toString());
  if(!points&&link.points.length>1&&(link.points[0].x!==link.source.x||link.points[0].y!==link.source.y||link.points.at(-1).x!==link.target.x||link.points.at(-1).y!==link.target.y)) {
    const a=link.source,b=link.target;
    setWirePoints(object,[{x:a.x,y:a.y},{x:a.x,y:b.y},{x:b.x,y:b.y}].filter((p,i,all)=>!i||p.x!==all[i-1].x||p.y!==all[i-1].y));
  }
  return object;
}
function splitWire(args) {
  const w=wires().wires.find(w=>w.id===args.id);if(!w)throw new Error('Wire does not exist');
  let segment=-1;
  for(let n=1;n<w.points.length;n++){const a=w.points[n-1],b=w.points[n];if((args.x-a.x)*(b.y-a.y)===(args.y-a.y)*(b.x-a.x)&&args.x>=Math.min(a.x,b.x)&&args.x<=Math.max(a.x,b.x)&&args.y>=Math.min(a.y,b.y)&&args.y<=Math.max(a.y,b.y)){segment=n;break;}}
  if(segment<0)throw new Error('Junction must lie on an existing wire segment');
  ensureWirePen(ptr(w.id));
  const pen=wirePen(ptr(w.id));
  removeObject({id:w.id});
  // CreateWireBase inherits the destination connector's pen. A null junction
  // pen silently creates electrically connected but invisible split segments.
  const junction=allocateObject('CODPinComp','??0CODPinComp@@QAE@VCPoint@@PAVCPen@@@Z',[args.x,args.y,pen],['int','int','pointer']);
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(diagram().graph,junction,0,0,treeInstance(),0);
  const cx=Memory.alloc(4),cy=Memory.alloc(4);method('Od101dll.dll','?GetCenter@CODConnector@@UAEXAAH0','void',['pointer','pointer','pointer'])(junction,cx,cy);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,junction,args.x-cx.readS32(),args.y-cy.readS32());
  const p={x:args.x,y:args.y};
  const first=connectNative(ptr(w.source.id),junction,[...w.points.slice(0,segment),p]);
  const second=connectNative(junction,ptr(w.target.id),[p,...w.points.slice(segment)]);
  setWirePoints(first,[...w.points.slice(0,segment),p]);setWirePoints(second,[p,...w.points.slice(segment)]);
  return {junction_id:junction.toString(),wire_ids:[first.toString(),second.toString()]};
}
function connectEndpoint(args) {
  const resolve=e=>{
    if(e.ref){const c=component(e.ref),p=c.pins.find(p=>p.name===e.pin);if(!p)throw new Error('Pin not found');return ptr(p.id);}
    if(!enumerate().objects.some(o=>o.id===e.junction_id&&/CODPinComp/.test(o.name)))throw new Error('Junction ID not found');return ptr(e.junction_id);
  };
  const object=connectNative(resolve(args.source),resolve(args.target),args.points);
  if(args.points)routeWire({id:object.toString(),points:args.points});
  return wires().wires.find(w=>w.id===object.toString());
}
function reconnectWire(args) {
  const old=wires().wires.find(w=>w.id===args.id);if(!old)throw new Error('Wire not found');
  const endpoint=end=>old[end].ref?{ref:old[end].ref,pin:old[end].pin}:{junction_id:old[end].id};
  const source=args.source||endpoint('source'),target=args.target||endpoint('target');
  // Validate named endpoint resolution before deleting the previous native wire.
  for(const e of [source,target])if(e.ref){if(!component(e.ref).pins.some(p=>p.name===e.pin))throw new Error('Replacement endpoint pin not found');}
  removeObject({id:old.id});return connectEndpoint({source,target,points:args.points});
}
function exportImage(args) {
  if(!args.interactive)synchronizeGraphics();
  const d=diagram(),before=pageGeometry(),region=args.region||{left:0,top:0,right:before.width,bottom:before.height};
  const prefs=new NativeFunction(d.graph.readPointer().add(0x5c).readPointer(),'pointer',['pointer'],'thiscall')(d.graph);
  const displayKeys={'Bounds ON':args.show_frame===true,'Border ON':args.show_frame===true,'Title Block ON':args.show_frame===true,'Simplified Title Block ON':args.show_frame===true,'Grid ON':args.show_grid===true,'Simplified Grid ON':args.show_grid===true},displayBefore={};
  const setPreference=(key,value)=>{const name=pathString(key),text=pathString(String(value));method('PREFS.dll','?SetPrefsAsString@CIITCircuitPrefs@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),text.readPointer());};
  const setSize=(w,h)=>{for(const [key,value] of Object.entries({'Sheet Width':w,'Sheet Height':h,'Sheet Width In Inch':w/96,'Sheet Height In Inch':h/96})) {
    const name=pathString(key),text=pathString(String(value));method('PREFS.dll','?SetPrefsAsString@CIITCircuitPrefs@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),text.readPointer());
  }};
  const root=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(d.composite);
  let bitmap=ptr(0),translated=false;
  try {
    for(const [key,enabled] of Object.entries(displayKeys)){
      const name=pathString(key),out=Memory.alloc(8);out.writeDouble(0);
      if(method('PREFS.dll','?GetPrefsAsDouble@CPreferences@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),out)){displayBefore[key]=out.readDouble();setPreference(key,enabled?1:0);}
    }
    if(args.region){setSize(region.right-region.left,region.bottom-region.top);method('Od101dll.dll','?Translate@CODGraphic@@','void',['pointer','float','float'])(root,-region.left,-region.top);translated=true;}
    bitmap=method('SCH_CAP.dll','?WriteCircuitImageToBitmap@CSCH_CAPSubSheet@@','pointer',['pointer','pointer','uint8','double'])(d.sheet,treeInstance(),0,(args.render_scale||1)*100);
    if(bitmap.isNull())throw new Error('Native bitmap renderer failed');
    const handle=bitmap.add(4).readPointer(),description=Memory.alloc(24);
    if(!method('gdi32.dll','GetObjectW','int',['pointer','int','pointer'],'stdcall')(handle,24,description))throw new Error('Native bitmap dimensions unavailable');
    const width=description.add(4).readS32(),height=description.add(8).readS32(),stride=Math.ceil(width*3/4)*4;
    if(width<=0||height<=0||width*height>32000000)throw new Error('Native bitmap exceeds 32 million pixels');
    const size=stride*height,header=Memory.alloc(40),buffer=Memory.alloc(size+54);header.writeByteArray(new Uint8Array(40));
    header.writeU32(40);header.add(4).writeS32(width);header.add(8).writeS32(height);header.add(12).writeU16(1);header.add(14).writeU16(24);header.add(20).writeU32(size);
    const dc=method('user32.dll','GetDC','pointer',['pointer'],'stdcall')(ptr(0));
    let rows;
    try {rows=method('gdi32.dll','GetDIBits','int',['pointer','pointer','uint','uint','pointer','pointer','uint'],'stdcall')(dc,handle,0,height,buffer.add(54),header,0);}
    finally {method('user32.dll','ReleaseDC','int',['pointer','pointer'],'stdcall')(ptr(0),dc);}
    if(rows!==height)throw new Error('Native bitmap readback failed');
    buffer.writeByteArray(new Uint8Array(54));buffer.writeU16(0x4d42);buffer.add(2).writeU32(size+54);buffer.add(10).writeU32(54);Memory.copy(buffer.add(14),header,40);
    writeNativeFile(args.path,buffer,size+54);
    return {path:args.path,width,height,render_scale:args.render_scale||1,region};
  } finally {
    if(!bitmap.isNull())new NativeFunction(bitmap.readPointer().readPointer(),'pointer',['pointer','uint'],'thiscall')(bitmap,1);
    if(translated)method('Od101dll.dll','?Translate@CODGraphic@@','void',['pointer','float','float'])(root,region.left,region.top);
    if(args.region)setSize(before.width,before.height);
    for(const [key,value] of Object.entries(displayBefore))setPreference(key,value);
  }
}
function synchronizeGraphics() {
  return repairWireGeometry();
}
function writeNativeFile(path,data,length) {
  const text=typeof data==='string',size=length===undefined?(text?unescape(encodeURIComponent(data)).length:data.byteLength):length;
  const buffer=length!==undefined?data:text?Memory.allocUtf8String(data):Memory.alloc(Math.max(1,size));
  if(length===undefined&&!text&&size)buffer.writeByteArray(data);
  const module=Process.getModuleByName('kernel32.dll');
  const create=new SystemFunction(module.getExportByName('CreateFileW'),'pointer',['pointer','uint','uint','pointer','uint','uint','pointer'],'stdcall');
  const write=new SystemFunction(module.getExportByName('WriteFile'),'int',['pointer','pointer','uint','pointer','pointer'],'stdcall');
  const close=new NativeFunction(module.getExportByName('CloseHandle'),'int',['pointer'],'stdcall');
  const opened=create(Memory.allocUtf16String(path),0x40000000,1,ptr(0),2,0x80,ptr(0));
  if(opened.value.equals(ptr(-1)))throw new Error('Cannot create native output '+path+' (Windows error '+opened.lastError+')');
  try {
    const count=Memory.alloc(4);let offset=0;
    while(offset<size){
      count.writeU32(0);const result=write(opened.value,buffer.add(offset),Math.min(size-offset,1048576),count,ptr(0));
      if(!result.value||!count.readU32())throw new Error('Cannot write native output '+path+' (Windows error '+result.lastError+')');
      offset+=count.readU32();
    }
  } finally {close(opened.value);}
  return {path,bytes:size};
}
function netlist() {
  const firstError=nativeErrorLog.length;
  method('SCH_CAP.dll','?SyncRefDesManager@CMultisimExtension@@','int',['pointer','uint8'])(extension(),1);
  const generator=method('SCH_CAP.dll','?GetNetlistGeneration@CMultisimExtension@@','pointer',['pointer'])(extension()),out=Memory.alloc(4),errors=pathString(''),failed=Memory.alloc(1);out.writePointer(ptr(0));failed.writeU8(0);
  method('SCH_CAP.dll','?GenNetlistToString@CNetlistGeneration@@','pointer',['pointer','pointer','uint8','uint8','uint8','uint8','pointer','pointer'])(generator,out,0,0,0,0,errors,failed);
  const content=out.readPointer().isNull()?'':out.readPointer().readUtf8String(),messages=errors.readPointer().readUtf16String();
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(out);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(errors);
  const capturedErrors=nativeErrorLog.slice(firstError);
  return {content,messages:[messages,...capturedErrors.map(e=>e.text)].filter(Boolean).join('\n'),errors:capturedErrors,failed:!!failed.readU8()||capturedErrors.length>0};
}
function menus() {
  const getMenu=method('user32.dll','GetMenu','pointer',['pointer'],'stdcall'),getCount=method('user32.dll','GetMenuItemCount','int',['pointer'],'stdcall'),sub=method('user32.dll','GetSubMenu','pointer',['pointer','int'],'stdcall'),id=method('user32.dll','GetMenuItemID','uint',['pointer','int'],'stdcall'),getText=method('user32.dll','GetMenuStringW','int',['pointer','uint','pointer','int','uint'],'stdcall');
  function list(menu){const result=[];for(let n=0;n<getCount(menu);n++){const text=Memory.alloc(1024);getText(menu,n,text,512,0x400);const child=sub(menu,n);result.push({id:id(menu,n),text:text.readUtf16String(),children:child.isNull()?[]:list(child)});}return result;}
  const handle=getMenu(hwnd);return {hwnd:hwnd.toString(),menu:handle.toString(),items:handle.isNull()?[]:list(handle)};
}
function simSession() {
  const manager=method('SpiceifsSch.dll','?GetSessionManager@CSchSpiceSessionManager@SpiceifsSch@@','pointer',[],'mscdecl')();
  const session=method('SpiceifsSch.dll','?GetMainSession@CSchSpiceSessionManager@SpiceifsSch@@','pointer',['pointer'])(manager);
  if(session.isNull())throw new Error('Native simulator main session is unavailable');return session;
}
function simulationInfo() {
  const session=simSession(),ext=extension();
  const status=method('SCH_CAP.dll','?GetCurrentSimulationStatustext@CMultisimExtension@@','pointer',['pointer'])(ext).readPointer().readUtf16String();
  const errorCount=method('SpiceifsSch.dll','?GetSpiceErrorCount@CSchSpiceSession@SpiceifsSch@@','uint',['pointer'])(session),errors=[];
  for(let n=Math.max(0,errorCount-100);n<errorCount;n++){const cmd=Memory.alloc(4),code=Memory.alloc(4);if(method('SpiceifsSch.dll','?GetSpiceError@CSchSpiceSession@SpiceifsSch@@','uint8',['pointer','uint','pointer','pointer'])(session,n,cmd,code))errors.push({index:n,command:cmd.readS32(),code:code.readS32()});}
  const frontend=method('SHARUTIL.dll','?GetGuiFEObject@CGuiFEObj@@','pointer',[],'mscdecl')();
  const actualErrors=errors.filter(e=>e.code!==0);
  return {session:session.toString(),state:method('SCH_CAP.dll','?GetSimulationState@CMultisimExtension@@','int',['pointer'])(ext),remote_initialized:!!method('SpiceifsSch.dll','?IsSimulationInitialized@CSchSpiceSession@SpiceifsSch@@','uint8',['pointer'])(session),status,error_count:actualErrors.length,errors:actualErrors,native_status_record_count:errorCount,native_status_records:errors,error_text:instanceString('SHARUTIL.dll','?GetErrorString@CGuiFEObj@@',frontend)};
}
function interactiveDisplays() {
  const order=[19,16,15,17,13,14,18],digits={'1111110':'0','0110000':'1','1101101':'2','1111001':'3','0110011':'4','1011011':'5','1011111':'6','1110000':'7','1111111':'8','1111011':'9'};
  return components().components.filter(c=>['A','B','C','D','E','F','G'].every(name=>c.pins.some(p=>p.name===name))).flatMap(c=>{
    const info=parameterInfo({ref:c.id});if(!/^SEVEN_SEG_COM_A$/.test(info.info[1]||''))return [];
    const segments=order.map(index=>!!method('Od101dll.dll','?GetSubComponentPrp@CIITSymbolComp@@QAEKW4GRAPHICPROPERTY@@JPAVCTreeInstance@@@Z','uint',['pointer','int','int','pointer'])(ptr(c.id),0,index,treeInstance()));
    return [{ref:c.ref,model:info.info[1],segment_order:'abcdefg',segments,active:segments.some(Boolean),decoded:digits[segments.map(Number).join('')]??null,source:'native runtime graphic properties'}];
  });
}
function exportInteractiveImage(args) {
  const state=simulationInfo();
  if(!state.remote_initialized||![1,2].includes(state.state))throw new Error('Start interactive simulation before capturing its runtime image');
  const displays=interactiveDisplays();
  if(args.active_component){
    const selected=displays.find(d=>d.ref===args.active_component);
    if(!selected)throw new Error('active_component must identify a supported SEVEN_SEG_COM_A display on this sheet');
    if(selected.decoded===null)return {ready:false,state:state.state,display_states:displays};
  }
  const image=exportImage({...args,interactive:true});
  const after=interactiveDisplays();
  if(JSON.stringify(displays)!==JSON.stringify(after))return {ready:false,state:state.state,display_states:after};
  return {ready:true,...image,capture_mode:'instantaneous',display_states:displays,simulation:interactiveStatus()};
}
let interactiveConfiguration={},interactiveStartup=null,interactiveLastStart=null,interactiveOptionsHook=null;
function rewriteInteractiveCommand(command,configuration) {
  const parts=command.trim().split(/\s+/);
  if(parts[0]!=='tran'||parts[1]!=='-env-options'||!(Number(parts[3])>=1e25))return null;
  if(parts.length<6||![2,3,4,5].every(i=>Number.isFinite(Number(parts[i])))||Number(parts[2])<=0||Number(parts[5])<=0)
    throw new Error('Unsupported native interactive transient parameters');
  let flags=parts.slice(6);
  if(configuration.time_step!==undefined){parts[2]=String(configuration.time_step);flags=flags.filter(f=>f!=='auto_tstep');}
  if(configuration.max_time_step!==undefined){parts[5]=String(configuration.max_time_step);flags=flags.filter(f=>f!=='auto_tmax');}
  if(configuration.real_time!==undefined){flags=flags.filter(f=>f!=='throttle');if(configuration.real_time)flags.push('throttle');}
  return {command:[...parts.slice(0,6),...flags].join(' '),time_step:Number(parts[2]),max_time_step:Number(parts[5]),real_time:flags.includes('throttle')};
}
function closeInteractiveOptions() {
  if(interactiveOptionsHook)interactiveOptionsHook.detach();
  interactiveOptionsHook=null;interactiveStartup=null;interactiveConfiguration={};interactiveLastStart=null;
}
function interactiveOptions(args={}) {
  const changes=args.configuration||{};
  if(args.reset)closeInteractiveOptions();
  else if(Object.keys(changes).length){
    interactiveConfiguration={...interactiveConfiguration,...changes};interactiveLastStart=null;
    if(!interactiveOptionsHook){
      const address=Process.getModuleByName('SpiceifsSch.dll').getExportByName('?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@QAE?AW4ESimMsgErrorCode@2@PB_W@Z');
      interactiveOptionsHook=Interceptor.attach(address,{onEnter(parameters){
        if(!interactiveStartup||Date.now()>interactiveStartup.expires)return;
        if(Process.getCurrentThreadId()!==uiThread||!this.context.ecx.equals(interactiveStartup.session)||activeNativeOperation==='simulate')return;
        try {
          if(!project().proj.equals(interactiveStartup.project))return;
          const original=parameters[0].readUtf16String(),effective=rewriteInteractiveCommand(original,interactiveConfiguration);
          if(!effective)return;
          this.commandStorage=Memory.allocUtf16String(effective.command);parameters[0]=this.commandStorage;
          this.appliedOptions=interactiveLastStart={applied:true,command_pending:true,native_result:null,original_command:original,effective_command:effective.command,time_step:effective.time_step,max_time_step:effective.max_time_step,real_time:effective.real_time};
          interactiveStartup=null;
        } catch(error){interactiveLastStart={applied:false,error:String(error)};interactiveStartup=null;}
      },onLeave(result){if(this.appliedOptions){this.appliedOptions.command_pending=false;this.appliedOptions.native_result=result.toInt32();if(result.toInt32()!==0)this.appliedOptions.applied=false;}}});
    }
  }
  return {configured:Object.keys(interactiveConfiguration).length>0,scope:'session',applies_to:'MCP interactive start',persisted_in_circuit:false,configuration:{...interactiveConfiguration},last_start:interactiveLastStart};
}
function interactiveStatus(args={}) {
  const info=simulationInfo(),names={'-1':'unprepared',0:'stopped',1:'running',2:'paused'},panes=[];
  const getClass=method('user32.dll','GetClassNameW','int',['pointer','pointer','int'],'stdcall');
  const callback=new NativeCallback(window=>{
    const name=Memory.alloc(256);getClass(window,name,128);
    if(name.readUtf16String()==='msctls_statusbar32'){
      const sendMessage=method('user32.dll','SendMessageW','int',['pointer','uint','uint','pointer'],'stdcall');
      const count=sendMessage(window,0x406,0,ptr(0));
      for(let n=0;n<Math.min(count,32);n++){
        const length=sendMessage(window,0x40c,n,ptr(0))&65535;
        if(!length||length>4096)continue;
        const text=Memory.alloc((length+1)*2);sendMessage(window,0x40d,n,text);panes.push(text.readUtf16String());
      }
    }
    return 1;
  },'int',['pointer','pointer'],'stdcall');
  method('user32.dll','EnumChildWindows','int',['pointer','pointer','pointer'],'stdcall')(hwnd,callback,ptr(0));
  const time=panes.map(text=>text.match(/(?:^|:)\s*([0-9]+(?:[.,][0-9]+)?(?:e[+-]?[0-9]+)?)\s*(ns|us|µs|μs|ms|s)\s*$/i)).find(Boolean);
  return {...info,state_name:names[info.state]||'unknown',simulation_time_s:time?Number(time[1].replace(',','.'))*({ns:1e-9,us:1e-6,'µs':1e-6,'μs':1e-6,ms:1e-3,s:1}[time[2].toLowerCase()]):null,status_panes:panes,interactive_options:interactiveOptions(),...(args.include_displays?{display_readout_available:info.remote_initialized&&[1,2].includes(info.state),display_states:info.remote_initialized&&[1,2].includes(info.state)?interactiveDisplays():[]}:{})};
}
function interactiveCommand(args) {
  const names={start:'UnifiedSimulationPlay',resume:'UnifiedSimulationPlay',pause:'UnifiedSimulationPause',stop:'UnifiedSimulationStop'};
  if(!names[args.action])throw new Error('Choose start, pause, resume or stop');
  const handler=method('PlugInManagement.dll','?GetUserInterfaceHandler@CUserInterfaceHandler@@','pointer',[],'mscdecl')();
  const id=method('PlugInManagement.dll','?GetCommandID@CUserInterfaceHandler@@','uint16',['pointer','uint16','pointer'])(handler,25,Memory.allocUtf16String(names[args.action]));
  if(id===65535)throw new Error('Native interactive command is unavailable: '+names[args.action]);
  if(args.action==='start'){
    activateSheet();interactiveLastStart=null;
    if(Object.keys(interactiveConfiguration).length)interactiveStartup={session:simSession(),project:project().proj,expires:Date.now()+15000};
  } else if(args.action==='stop')interactiveStartup=null;
  const queued=method('user32.dll','PostMessageW','int',['pointer','uint','uint','int'],'stdcall')(hwnd,0x111,id,0);
  if(!queued)throw new Error('Native interactive command could not be queued');
  return {action:args.action,command_id:id,requested:true};
}
function simulate(args) {
  const session=simSession();
  if(args.action==='stop')return {result:method('SpiceifsSch.dll','?StopSimulation@CSchSpiceSession@SpiceifsSch@@','int',['pointer'])(session),...simulationInfo()};
  if(args.action==='pause')return {result:method('SpiceifsSch.dll','?SetPausePending@CSchSpiceSession@SpiceifsSch@@','int',['pointer','uint8','uint8'])(session,1,1),...simulationInfo()};
  const text=netlist();if(text.failed)throw new Error(text.messages||'Netlist generation failed');
  function stdString(value,wide) {
    const data=wide?Memory.allocUtf16String(value):Memory.allocUtf8String(value),size=wide?value.length:unescape(encodeURIComponent(value)).length,s=Memory.alloc(24);s.writeByteArray(new Uint8Array(24));s.writePointer(data);s.add(16).writeU32(size);s.add(20).writeU32(Math.max(size,wide?8:16));keep.push(data);return s;
  }
  let prepared=null;
  if(!method('SpiceifsSch.dll','?IsSimulationInitialized@CSchSpiceSession@SpiceifsSch@@','uint8',['pointer'])(session)) {
    const object=method('SHARUTIL.dll','?GetGuiFEObject@CGuiFEObj@@','pointer',[],'mscdecl')(),variant=Memory.alloc(128),output=pathString(''),failed=Memory.alloc(1);failed.writeU8(0);
    method('SHARUTIL.dll','??0IITVariant@@QAE@XZ','pointer',['pointer'])(variant);
    prepared=method('SHARUTIL.dll','?Resimulate@CGuiFEObj@@','int',['pointer','pointer','pointer','int','uint8','uint8','uint8','pointer','pointer'])(object,variant,output,0,0,0,0,treeInstance(),failed);
    method('SHARUTIL.dll','??1IITVariant@@','void',['pointer'])(variant);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(output);
    if(prepared!==0||failed.readU8())throw new Error('Native simulator preparation failed: '+prepared);
  }
  if(session.add(0x18).readPointer().isNull())throw new Error('Native simulator transport is not initialized');
  const initialized=method('SpiceifsSch.dll','?SessionInit@CSchSpiceSession@SpiceifsSch@@','int',['pointer'])(session);
  // Remove old circuits and plots so a failed run cannot masquerade as a previous successful result.
  const trace=[];
  const shell=(stage,command)=>{
    const before=simulationInfo().native_status_record_count,start=Date.now();
    const result=method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer'])(session,Memory.allocUtf16String(command));
    const after=simulationInfo(),errors=after.native_status_records.filter(e=>e.code!==0&&(after.native_status_record_count<before||e.index>=before));
    trace.push({stage,command,result,elapsed_ms:Date.now()-start,errors});return {result,errors};
  };
  shell('clear-plots','destroy all');shell('clear-circuit','remcirc');
  let sent;
  if(args.source_path) {
    writeNativeFile(args.source_path,text.content+'\n.end\n');
    sent=shell('load-netlist','source "'+args.source_path.replace(/\\/g,'/')+'"').result;
  } else sent=method('SpiceifsSch.dll','?SendNetlist@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer','uint8','pointer'])(session,stdString(text.content+'\n.end\n',false),0,stdString('',true));
  if(trace.length&&trace[trace.length-1].errors.length)return {failed:true,stage:'load-netlist',trace,...simulationInfo()};
  const command=args.analysis==='op'?'op':args.analysis==='ac'?`ac ${args.ac_sweep} ${args.ac_points} ${args.ac_start} ${args.ac_stop}`:`tran ${args.step} ${args.stop}${args.use_initial_conditions?' uic':''}`;
  send({analysis_started:true,command});
  const completed=shell('analysis',command);
  const errors=trace.filter(t=>t.stage==='load-netlist'||t.stage==='analysis').flatMap(t=>t.errors);
  return {...simulationInfo(),prepared,initialize_result:initialized,sent,result:completed.result,command,trace,failed:completed.result!==0||errors.length>0,stage:'analysis',error_count:errors.length,errors};
}
function simulationExport(args) {
  const session=simSession(),run=method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer']);
  const ascii=run(session,Memory.allocUtf16String('set filetype=ascii'));
  const result=run(session,Memory.allocUtf16String('write "'+args.path.replace(/\\/g,'/')+'" all'));
  method('SCH_CAP.dll','?SetSimulationState@CMultisimExtension@@','void',['pointer','int','uint8','uint8'])(extension(),0,0,0);
  return {ascii,result,path:args.path,...simulationInfo()};
}
function symbolBodyBounds(c) {
  const rect=Memory.alloc(16);
  method('Od101dll.dll','?GetRealBoxWithoutPins_WithBorderRect@CIITSymbolComp@@','pointer',['pointer','pointer'])(ptr(c.id),rect);
  const [x1,y1,x2,y2]=[0,4,8,12].map(n=>rect.add(n).readS32());
  return {left:Math.min(x1,x2),top:Math.min(y1,y2),right:Math.max(x1,x2),bottom:Math.max(y1,y2)};
}
function componentBounds() {
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  return {components:components().components.map(c=>{
    const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(ptr(c.id)),rect=Memory.alloc(16);
    method('Od101dll.dll','?GetBox@CODGraphic@@QAEXAAVCRect@@AAVCODInstContext@@@Z','void',['pointer','pointer','pointer'])(graphic,rect,context);
    const [x1,y1,x2,y2]=[0,4,8,12].map(n=>rect.add(n).readS32());
    return {...c,bounds:{left:Math.min(x1,x2),top:Math.min(y1,y2),right:Math.max(x1,x2),bottom:Math.max(y1,y2)}};
  })};
}
function contentBounds() {
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A'),rects=[];
  for(const object of listChildren(diagram().composite)) {
    if(/CIITLinkComp/.test(rtti(object).name))continue;
    const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(object),rect=Memory.alloc(16);
    if(graphic.isNull())continue;
    method('Od101dll.dll','?GetBox@CODGraphic@@QAEXAAVCRect@@AAVCODInstContext@@@Z','void',['pointer','pointer','pointer'])(graphic,rect,context);
    const [x1,y1,x2,y2]=[0,4,8,12].map(n=>rect.add(n).readS32());
    if(x1===x2&&y1===y2)continue;
    rects.push({left:Math.min(x1,x2),top:Math.min(y1,y2),right:Math.max(x1,x2),bottom:Math.max(y1,y2)});
  }
  for(const w of wires().wires)if(w.points.length)rects.push({left:Math.min(...w.points.map(p=>p.x)),top:Math.min(...w.points.map(p=>p.y)),right:Math.max(...w.points.map(p=>p.x)),bottom:Math.max(...w.points.map(p=>p.y))});
  return rects.length?{left:Math.min(...rects.map(r=>r.left)),top:Math.min(...rects.map(r=>r.top)),right:Math.max(...rects.map(r=>r.right)),bottom:Math.max(...rects.map(r=>r.bottom))}:null;
}
function circuitState(args={}) {
  const state=componentBounds(),page=pageGeometry();
  for(const c of state.components)c.labels=componentLabels({ref:c.id},c).labels;
  if(args.include_parameters)for(const c of state.components){const p=parameterInfo({ref:c.id},c);c.parameters=p.parameters;c.library={family:p.info[0],name:p.info[1],symbol_family:p.info[2],model:p.info[3]};}
  return {sheets:readSheets(),page,components:state.components,wires:wires().wires,content_bounds:contentBounds()};
}
function projectCircuitState(args={}) {
  const previous=selectedSheetId,states=[],sheets=readSheets();
  try {
    for(const sheet of sheets){selectSheet({index:sheet.index});states.push({sheet_index:sheet.index,...circuitState(args)});}
  } finally {selectedSheetId=previous;cachedDiagram=null;}
  return {states};
}
function verifySavedCopy(args) {
  const context=project(),original=context.proj,originalSheet=selectedSheetId,value=pathString(args.path);let loaded=null;
  try {
    const result=method('DrwEngine.dll','?FileOpen@CWorkspaceContainer@@QAE?AW4EOpenResult@1@ABVCPathString@@_N1@Z','int',['pointer','pointer','uint8','uint8'])(project().container,value,0,0);
    const found=projects().projects.find(p=>p.path.toLowerCase()===args.path.toLowerCase());
    if(!found||ptr(found.id).equals(original))throw new Error('Saved verification copy could not be opened: '+result);
    loaded=ptr(found.id);selectedProjectIndex=found.index;selectedSheetId=null;cachedDiagram=null;
    return projectCircuitState(args);
  } finally {
    native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);
    if(loaded){
      method('DrwEngine.dll','?SetAllModified@CProject@@QAEX_N@Z','void',['pointer','uint8'])(loaded,0);
      method('DrwEngine.dll','?FileCloseProject@CWorkspaceContainer@@','int',['pointer','pointer','uint8'])(context.container,loaded,0);
    }
    selectedProjectIndex=0;selectedSheetId=null;cachedDiagram=null;
    const found=projects().projects.find(p=>ptr(p.id).equals(original));
    if(!found)throw new Error('Original document is unavailable after save verification');
    selectedProjectIndex=found.index;selectedSheetId=originalSheet;cachedDiagram=null;activateSheet();
  }
}
function componentLabels(args,source=null) {
  const c=source||component(args.ref),context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  const labels=[];
  for(const child of listChildren(ptr(c.id))) {
    const type=rtti(child).name;
    if(!/CIITSymTextComp(?:Name|Value)/.test(type))continue;
    const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(child),r=Memory.alloc(16);
    method('Od101dll.dll','?GetBox@CODGraphic@@QAEXAAVCRect@@AAVCODInstContext@@@Z','void',['pointer','pointer','pointer'])(graphic,r,context);
    const corners=[[r.readS32(),r.add(4).readS32()],[r.add(8).readS32(),r.add(12).readS32()]].map(([x,y])=>({x,y}));
    const bounds={left:Math.min(...corners.map(p=>p.x)),top:Math.min(...corners.map(p=>p.y)),right:Math.max(...corners.map(p=>p.x)),bottom:Math.max(...corners.map(p=>p.y))};
    const text=instanceString('Od101dll.dll','?GetText@CODTextComp@@',child,[treeInstance()],['pointer']);
    labels.push({id:child.toString(),kind:/CompValue/.test(type)?'value':'reference',text,bounds,center:{x:(bounds.left+bounds.right)/2,y:(bounds.top+bounds.bottom)/2}});
  }
  return {reference:c.ref,labels};
}
function moveComponentLabel(args) {
  const c=component(args.ref),labels=componentLabels(args).labels.filter(l=>l.kind===(args.kind||'reference'));
  if(labels.length!==1)throw new Error('Expected one native '+(args.kind||'reference')+' label');
  const label=labels[0],dx=args.x-label.center.x,dy=args.y-label.center.y,p=c.transform,l=matrix(ptr(label.id));
  const [a,b,d,e]=p,det=a*e-b*d;
  const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(ptr(label.id));
  const transformer=method('Od101dll.dll','?GetTransformer@CODGraphic@@QAEP','pointer',['pointer'])(graphic);
  method('Od101dll.dll','?TranslateAbs@CODTransformer@@','void',['pointer','float','float'])(transformer,l[4]+(e*dx-d*dy)/det,l[5]+(-b*dx+a*dy)/det);
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  method('Od101dll.dll','?Update@CODComponent@@UAEXAAVCODInstContext@@_N@Z','void',['pointer','pointer','uint8'])(ptr(label.id),context,0);
  return componentLabels(args);
}
let valueTextSlot=null;
function refreshComponentValue(ref,reflow=false) {
  const c=component(ref),label=componentLabels({ref:c.id},c).labels.find(l=>l.kind==='value');
  if(!label)return [];
  if(valueTextSlot===null){
    const mod=Process.getModuleByName('Od101dll.dll'),target=mod.enumerateExports().find(e=>e.name.startsWith('?CreateValueText@CODDiagram@@')).address;
    const table=mod.getExportByName('??_7CODDiagram@@6B@');
    for(let n=0;n<512;n++)if(table.add(n*4).readPointer().equals(target)){valueTextSlot=n;break;}
    if(valueTextSlot===null)throw new Error('Native value formatter virtual method is unavailable');
  }
  const graph=diagram().graph,fn=new NativeFunction(graph.readPointer().add(valueTextSlot*4).readPointer(),'pointer',['pointer','pointer','pointer','uint8','uint8','pointer'],'thiscall');
  const text=readCStringResult(out=>fn(graph,out,ptr(c.id),0,0,treeInstance()),[]);
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  method('Od101dll.dll','?SetText@CODTextComp@@','void',['pointer','pointer','pointer'])(ptr(label.id),Memory.allocUtf16String(text),context);
  method('Od101dll.dll','?Update@CODComponent@@UAEX','void',['pointer','pointer','uint8'])(ptr(label.id),context,0);
  if(reflow)arrangeComponentLabels(c.id);
  return componentLabels({ref:c.id}).labels;
}
function straightenComponentLabels(ref) {
  const c=component(ref),[a,b,d,e]=c.transform;
  for(const label of componentLabels({ref:c.id},c).labels){
    const lm=matrix(ptr(label.id)),angle=Math.atan2(b*lm[0]+e*lm[1],a*lm[0]+d*lm[1])*180/Math.PI;
    const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(ptr(label.id));
    if(Math.abs(angle)>0.001){
      method('Od101dll.dll','?Rotate@CODGraphic@@','void',['pointer','float','float','float'])(graphic,-angle,0,0);
      moveComponentLabel({ref:c.id,kind:label.kind,x:label.center.x,y:label.center.y});
    }
  }
}
function arrangeComponentLabels(ref) {
  const c=component(ref),body=symbolBodyBounds(c),labels=componentLabels({ref:c.id},c).labels.filter(l=>l.text);
  const overlaps=(a,b)=>a.left<b.right+2&&a.right>b.left-2&&a.top<b.bottom+2&&a.bottom>b.top-2;
  if(!labels.some(l=>overlaps(l.bounds,body))&&!labels.some((l,i)=>labels.slice(i+1).some(o=>overlaps(l.bounds,o.bounds))))return;
  const heights=labels.map(l=>l.bounds.bottom-l.bounds.top),total=heights.reduce((a,b)=>a+b,0)+4*(labels.length-1);
  let y=(body.top+body.bottom-total)/2;
  labels.forEach((l,i)=>{moveComponentLabel({ref:c.id,kind:l.kind,x:body.right+9+(l.bounds.right-l.bounds.left)/2,y:y+heights[i]/2});y+=heights[i]+4;});
}
const editorHandlers={
  componentBounds,synchronizeGraphics,circuitState,projectCircuitState,verifySavedCopy,componentLabels,moveLabel:moveComponentLabel,
  simulationCommand:args=>({result:method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer'])(simSession(),Memory.allocUtf16String(args.command)),...simulationInfo()}),
  parameters:parameterInfo,setParameter,rename:renameComponent,copy:copyComponent,remove:removeObject,transform:transformComponent,route:routeWire,repairWireGeometry,sheets:readSheets,
  electricalPorts:args=>{
    const ci=ciObject(ptr(component(args.ref).id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci),ports=[];
    for(let n=0;n<count;n++){const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,n);ports.push({id:port.toString(),name:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',port)});}
    return {ref:args.ref,ports};
  },
  setProjectPath:args=>setProjectPath(args.path),snapshot,restoreSnapshot,librarySearch,place:placeComponent,addText,labelWire,modelInfo,setModelText,createSubcircuit,createPort,sheetTitle,sheetSize,splitWire,connectEndpoint,reconnect:reconnectWire,replace:replaceComponent,exportImage,exportInteractiveImage,interactiveOptions,interactiveStatus,interactiveCommand,netlist,menus,selectSheet,projects,selectProject,createSheet,newProject,simulationInfo,simulate,simulationExport,
  dbInfo:()=>{
    const db=masterDb(),manager=method('LibraryAccess.dll','?GetDatabaseManager@CDatabaseManager@@SAP','pointer',[],'mscdecl')(),files=method('LibraryAccess.dll','?GetDatabaseFileManager@CDatabaseManager@@','pointer',['pointer'])(manager),record=method('LibraryAccess.dll','?GetMasterDatabaseFile@CDatabaseFileManager@@','pointer',['pointer'])(files),strings=[];
    for(let offset=0;offset<128;offset+=4)try{const value=record.add(offset).readPointer().readUtf16String(520);if(value&&/^[A-Za-z]:|Master|Database/i.test(value))strings.push({offset,value});}catch(_){}
    const tableId=method('Database.dll','?GetCompTableID@CDBComponent@@','int',['pointer'])(db);
    const tableName=method('Database.dll','?GetTableName@CDBComponent@@','pointer',['pointer','uint'])(db,tableId).readPointer().readUtf16String();
    return {db:db.toString(),type:rtti(db),validity:db.add(12).readU8(),driver:db.add(16).readPointer().toString(),strings,tableId,tableName,last_sql:instanceString('Database.dll','?GetSQLString_SQLDirectSet@CDBComponent@@',db),last_sql2:instanceString('Database.dll','?GetSQLString_SQLDirectSet_2@CDBComponent@@',db)};
  },
  simDebug:()=>{
    const object=method('SHARUTIL.dll','?GetGuiFEObject@CGuiFEObj@@','pointer',[],'mscdecl')(),interfaces=[];
    const count=method('SHARUTIL.dll','?GetInterfaceCount@CGuiFEObj@@','uint',['pointer'])(object);
    for(let n=0;n<count;n++){const item=method('SHARUTIL.dll','?GetInterface@CGuiFEObj@@','pointer',['pointer','uint'])(object,n),address=item.readPointer().add(4).readPointer(),mod=Process.findModuleByAddress(address);interfaces.push({id:item.toString(),type:rtti(item),resimulate:{module:mod.name,rva:address.sub(mod.base).toString()}});}
    const session=simSession();return {object:object.toString(),active:object.add(0x90).readPointer().toString(),interfaces,remote:session.add(0xc8).readU8(),transport:session.add(0x18).readPointer().toString(),session_bytes:Array.from(new Uint8Array(session.readByteArray(48)))};
  },
  diagramDebug:()=>{
    const d=diagram();function bases(p){const locator=p.readPointer().sub(4).readPointer(),h=locator.add(16).readPointer(),a=h.add(12).readPointer(),all=[];for(let n=0;n<h.add(8).readU32();n++){const b=a.add(n*4).readPointer();all.push({type:b.readPointer().add(8).readUtf8String(),offset:b.add(8).readS32()});}return all;}
    return {proj:d.proj.toString(),sheet:d.sheet.toString(),sheet_type:rtti(d.sheet),sheet_bases:bases(d.sheet),doc:d.doc.toString(),doc_type:rtti(d.doc),doc_bases:bases(d.doc),graph:d.graph.toString(),raw_graph:d.doc.add(0x3a0).readPointer().toString()};
  },
  wireDetails:args=>wires().wires.filter(w=>!args.id||w.id===args.id),
  initializeProject,
  connectivity:()=>({wires:wires().wires.map(w=>{const n=method('SCH_CAP.dll','?GetNode@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));return {id:w.id,node:n.toString(),name:n.isNull()?null:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',n)};}),components:components().components.map(c=>({ref:c.ref,nodes:c.pins.map((p,index)=>{const n=method('CIRCEXP.dll','?GetNode@CiComponent@@','pointer',['pointer','int'])(ciObject(ptr(c.id)),index);return n.toString();})}))}),
  editorInfo:()=>({handler:method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')().toString(),extension:extension().toString(),objects:components().components.map(c=>({id:c.id,ref:c.ref,local_ref:c.local_ref,ci:ciObject(ptr(c.id)).toString()}))})};
// Simulator transport sends control requests independently of a busy UI-thread analysis.
rpc.exports.control=action=>{
  if(!['pause','resume','stop'].includes(action))throw new Error('Unknown simulator control');
  const transport=simSession().add(0x18).readPointer();if(transport.isNull())throw new Error('Simulator is not prepared');
  const result=action==='stop'?method('spiceifs.dll','?StopSimulation@CXSpiceSimInterface@xspiceif@@','int',['pointer'])(transport):method('spiceifs.dll','?SimPause@CXSpiceSimInterface@xspiceif@@','int',['pointer','int','uint8','uint8'])(transport,1,0,action==='pause'?1:0);
  return {action,native_result:result,requested:true};
};
