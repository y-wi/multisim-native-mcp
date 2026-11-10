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
function parameterInfo(args) {
  const c=component(args.ref),ci=ciObject(ptr(c.id));
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
  return {before,after:parameterInfo(args)};
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
    for(const p of params.parameters)if(p.value!==null)setParameter({ref:result.component.id,index:p.index,value:p.value});
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
  return {ref:c.ref,before,after:matrix(object),pins:updateAttachedGeometry(c.ref,attached)};
}
function copyTransform(source,target,x,y) {
  const graphic=object=>method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(object);
  const transform=object=>method('Od101dll.dll','?GetTransformer@CODGraphic@@QAEP','pointer',['pointer'])(graphic(object));
  const st=transform(source),tt=transform(target);if(st.isNull()||tt.isNull())throw new Error('Native component transform unavailable');
  method('Od101dll.dll','??4CODTransformer@@QAEAAV0@ABV0@@Z','pointer',['pointer','pointer'])(tt,st);
  const current=matrix(target);
  const dx=Math.round(x-current[4]),dy=Math.round(y-current[5]);
  // Even MoveComponentBy(0,0) resnaps a rotated symbol's anchor in this build.
  if(dx||dy)method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,target,dx,dy);
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
function readSheets() {
  const d=diagram();
  return d.candidates.filter(s=>/CSCH_CAPSubSheet/.test(s.name)).map((s,index)=>{
    const title=method('DrwEngine.dll','?GetTitle@CDrwSubSheet@@','pointer',['pointer'])(s.pointer).readPointer().readUtf16String();
    const page=method('DrwEngine.dll','?GetPageName@CDrwSubSheet@@','pointer',['pointer'])(s.pointer).readPointer().readUtf16String();
    return {index,id:s.pointer.toString(),title,page,selected:s.pointer.equals(d.sheet)};
  });
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
  const original=projectPath(project().proj),modified=inspect().modified,result=save(args);
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
  const sql=pathString("SELECT TOP "+limit+" SYS_COMPONENT.Component_Name, SYS_COMPONENT.Component_ID, SYS_COMPONENT.Family_ID FROM SYS_COMPONENT"+(term?" WHERE SYS_COMPONENT.Component_Name LIKE '*"+term+"*'":"")+" ORDER BY SYS_COMPONENT.Component_Name");
  method('Database.dll','?OpenSQLDirectSet@CDBComponent@@','void',['pointer','pointer'])(db,sql.readPointer());
  const results=[];
  try {
    if(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db))method('Database.dll','?MoveFirstRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
    while(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db)&&results.length<limit) {
      const item={};
      for(const column of ['Component_Name']) {
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
  const origin=matrix(object);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(d.graph,object,Math.round(args.x-origin[4]),Math.round(args.y-origin[5]));
  return {component:component(object.toString())};
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
  ensureWirePen(object);return object;
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
  const path=pathString(args.path);
  const sheet=diagram().sheet;
  // CDrwSubSheet's exported implementation is a false-returning stub. Slot 350 is
  // the verified CSCH_CAPSubSheet override in this ABI profile.
  const ok=new NativeFunction(sheet.readPointer().add(350*4).readPointer(),'uint8',['pointer','pointer'],'thiscall')(sheet,path);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(path);
  if(!ok)throw new Error('Native image exporter failed');return {path:args.path};
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
  return {session:session.toString(),state:method('SCH_CAP.dll','?GetSimulationState@CMultisimExtension@@','int',['pointer'])(ext),remote_initialized:!!method('SpiceifsSch.dll','?IsSimulationInitialized@CSchSpiceSession@SpiceifsSch@@','uint8',['pointer'])(session),status,error_count:errorCount,errors,error_text:instanceString('SHARUTIL.dll','?GetErrorString@CGuiFEObj@@',frontend)};
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
    const before=simulationInfo().error_count,start=Date.now();
    const result=method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer'])(session,Memory.allocUtf16String(command));
    const after=simulationInfo(),errors=after.errors.filter(e=>e.code!==0&&(after.error_count<before||e.index>=before));
    trace.push({stage,command,result,elapsed_ms:Date.now()-start,errors});return {result,errors};
  };
  shell('clear-plots','destroy all');shell('clear-circuit','remcirc');
  let sent;
  if(args.source_path) {
    const file=new File(args.source_path,'w');file.write(text.content+'\n.end\n');file.close();
    sent=shell('load-netlist','source "'+args.source_path.replace(/\\/g,'/')+'"').result;
  } else sent=method('SpiceifsSch.dll','?SendNetlist@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer','uint8','pointer'])(session,stdString(text.content+'\n.end\n',false),0,stdString('',true));
  if(trace.length&&trace[trace.length-1].errors.length)return {failed:true,stage:'load-netlist',trace,...simulationInfo()};
  const command=args.analysis==='op'?'op':args.analysis==='ac'?`ac ${args.ac_sweep} ${args.ac_points} ${args.ac_start} ${args.ac_stop}`:`tran ${args.step} ${args.stop}${args.use_initial_conditions?' uic':''}`;
  send({analysis_started:true,command});
  const completed=shell('analysis',command);
  return {prepared,initialize_result:initialized,sent,result:completed.result,command,trace,failed:completed.result!==0||completed.errors.length>0,stage:'analysis',...simulationInfo()};
}
function simulationExport(args) {
  const session=simSession(),run=method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer']);
  const ascii=run(session,Memory.allocUtf16String('set filetype=ascii'));
  const result=run(session,Memory.allocUtf16String('write "'+args.path.replace(/\\/g,'/')+'" all'));
  method('SCH_CAP.dll','?SetSimulationState@CMultisimExtension@@','void',['pointer','int','uint8','uint8'])(extension(),0,0,0);
  return {ascii,result,path:args.path,...simulationInfo()};
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
const editorHandlers={
  componentBounds,
  simulationCommand:args=>({result:method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer'])(simSession(),Memory.allocUtf16String(args.command)),...simulationInfo()}),
  parameters:parameterInfo,setParameter,rename:renameComponent,copy:copyComponent,remove:removeObject,transform:transformComponent,route:routeWire,sheets:readSheets,
  electricalPorts:args=>{
    const ci=ciObject(ptr(component(args.ref).id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci),ports=[];
    for(let n=0;n<count;n++){const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,n);ports.push({id:port.toString(),name:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',port)});}
    return {ref:args.ref,ports};
  },
  snapshot,restoreSnapshot,librarySearch,place:placeComponent,addText,labelWire,modelInfo,setModelText,createSubcircuit,createPort,sheetTitle,sheetSize,splitWire,connectEndpoint,reconnect:reconnectWire,replace:replaceComponent,exportImage,netlist,menus,selectSheet,projects,selectProject,createSheet,newProject,simulationInfo,simulate,simulationExport,
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
