// Additional native editor operations. Kept in the same Frida realm as host_agent.js.
const prefixFunctions=new Map();
let doubleGetter=null;
let originalWiringOptions=null;
let nodeInfoOffset=null;
let nativeRouteFunction=null;
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
function componentLibraryInfo(ci) {
  const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,4);
  if(attr.isNull()||!/CiaCollString/.test(rtti(attr).name))return [];
  return Array.from({length:5},(_,index)=>instanceString('CIRCEXP.dll','?GetParam@CiaCollString@@',attr,[index],['int']));
}
const PARAMETER_DESCRIPTORS={
  RESISTOR_VIRTUAL:{0:{role:'model_option'},1:{name:'resistance',unit:'Ohm',role:'value'}},
  CAPACITOR_VIRTUAL:{0:{role:'model_option'},1:{name:'capacitance',unit:'F',role:'value'}},
  INDUCTOR_VIRTUAL:{0:{role:'model_option'},1:{name:'inductance',unit:'H',role:'value'}},
  DC_POWER:{0:{role:'model_option'},1:{name:'voltage',unit:'V',role:'value'}},
  DC_CURRENT:{0:{role:'model_option'},1:{name:'current',unit:'A',role:'value'}},
  VDD:{0:{name:'voltage',unit:'V',role:'value'}},
  VCC:{0:{name:'voltage',unit:'V',role:'value'}},
  VSS:{0:{name:'voltage',unit:'V',role:'value'}},
  VEE:{0:{name:'voltage',unit:'V',role:'value'}},
  AC_POWER:{0:{role:'model_option'},1:{name:'voltage_rms',unit:'V',role:'value'},5:{name:'frequency',unit:'Hz'},13:{name:'ac_magnitude',unit:'V'}},
  AC_VOLTAGE:{0:{role:'model_option'},1:{name:'voltage_pk',unit:'V',role:'value'},5:{name:'frequency',unit:'Hz'},13:{name:'ac_magnitude',unit:'V'}},
  CLOCK_VOLTAGE:{0:{role:'model_option'},1:{name:'frequency',unit:'Hz',role:'value'},3:{name:'duty_cycle',unit:'%'},5:{name:'voltage',unit:'V'},7:{name:'rise_time',unit:'s'},9:{name:'fall_time',unit:'s'}},
  PULSE_VOLTAGE:{0:{role:'model_option'},1:{name:'initial_value',unit:'V'},3:{name:'pulsed_value',unit:'V'},7:{name:'rise_time',unit:'s'},9:{name:'fall_time',unit:'s'},11:{name:'pulse_width',unit:'s'},13:{name:'period',unit:'s'}},
  OPAMP_3T_VIRTUAL:{0:{role:'model_option'},7:{name:'open_loop_gain'},9:{name:'input_resistance',unit:'Ohm'},11:{name:'output_resistance',unit:'Ohm'},15:{name:'v_pos',unit:'V'},17:{name:'v_neg',unit:'V'}},
  POTENTIOMETER_VIRTUAL:{3:{name:'wiper_step',unit:'%'},5:{name:'resistance',unit:'Ohm',role:'value'}},
  POTENTIOMETER_RATED:{3:{name:'wiper_step',unit:'%'},7:{name:'resistance',unit:'Ohm',role:'value'},9:{name:'rated_power',unit:'W'}},
  POTENTIOMETER1_5K:{3:{name:'wiper_step',unit:'%'}}
};
function parameterInfo(args,source=null) {
  const c=source||component(args.ref),sym=ptr(c.id),ci=ciObject(sym);
  const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2);
  const parameters=[];
  if(!attr.isNull() && /CiaParamList/.test(rtti(attr).name)) {
    const count=method('CIRCEXP.dll','?GetParamCount@CiaParamList@@','int',['pointer'])(attr);
    const exprCount=method('CIRCEXP.dll','?GetExprParamCount@CiaParamList@@','int',['pointer'])(attr);
    for(let n=0;n<Math.max(count,exprCount);n++)parameters.push({index:n,value:n<count?parameterDouble(attr,n):null,expression:n<exprCount?instanceString('CIRCEXP.dll','?GetExprParam@CiaParamList@@',attr,[n],['int']):null});
  }
  const info=componentLibraryInfo(ci);
  const partKey=(info[1]||'').toUpperCase();
  const slots=PARAMETER_DESCRIPTORS[partKey]||((info[3]||'').toUpperCase()==='VCC'&&/^(VDD|VCC|VSS|VEE)$/i.test(info[1]||'')?PARAMETER_DESCRIPTORS.VCC:null)||((info[0]||'').toUpperCase()==='LED'&&parameters.length>=2?{0:{role:'model_option'},1:{name:'on_current',unit:'A',role:'value'}}:null);
  if(slots)for(const p of parameters)if(slots[p.index])Object.assign(p,slots[p.index]);
  const isInst=typeof isInstrumentSymbol==='function'&&isInstrumentSymbol(sym);
  return {ref:c.ref,ci:ci.toString(),info,parameters,...(isInst?{is_instrument:true,instrument_manager:instrumentManagerForSymbol(sym),instrument_type:instrumentTypeForSymbol(sym),hint:'This object is a virtual instrument. Use native_get_instrument_settings and native_set_instrument_settings to inspect or configure it.'}:{})};
}
function setParameter(args,displayExpression=null) {
  const target=component(args.ref);
  if(typeof isInstrumentSymbol==='function'&&isInstrumentSymbol(ptr(target.id))){
    throw new Error(target.ref+' is a virtual instrument ('+instrumentManagerForSymbol(ptr(target.id))+'); use native_set_instrument_settings instead of native_set_parameter.');
  }
  const hasValue=args.value!==undefined,hasExpr=args.expression!==undefined;
  if(hasValue===hasExpr)throw new Error('Provide exactly one of value or expression');
  if(hasValue&&(typeof args.value!=='number'||!Number.isFinite(args.value)))throw new Error('Parameter value must be a finite number');
  if(hasExpr&&(typeof args.expression!=='string'||!args.expression.trim()||args.expression.includes('\0')))throw new Error('Parameter expression must be a non-empty string');
  const before=parameterInfo(args),c=component(args.ref),ci=ciObject(ptr(c.id));
  let index=args.index;
  if(index===undefined||index===null){
    const wantName=args.name,wantRole=args.role||(wantName?undefined:'value');
    const matches=before.parameters.filter(p=>(!wantName||p.name===wantName)&&(!wantRole||p.role===wantRole));
    if(matches.length!==1){
      const available=before.parameters.filter(p=>p.name||p.role).map(p=>`${p.index}:${p.name||p.role}`).join(', ')||'none';
      throw new Error(`Expected one matching parameter slot for ${JSON.stringify({name:wantName,role:wantRole})} on ${c.ref}; found ${matches.length} (available: ${available})`);
    }
    index=matches[0].index;
  } else if(typeof index!=='number'||!Number.isInteger(index)||index<0) {
    throw new Error('Parameter index must be a non-negative integer');
  }
  const slot=before.parameters.find(p=>p.index===index);
  if(!slot)throw new Error('Parameter index does not exist');
  if(hasExpr) {
    const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2),text=pathString(args.expression);
    const ok=method('CIRCEXP.dll','?SetExprParam@CiaParamList@@','uint8',['pointer','int','pointer','int'])(attr,index,text,1);
    native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
    if(!ok)throw new Error('Native expression setter rejected the value');
  } else {
    // Supply models can store voltage only as an expression. Ordinary numeric slots may
    // start without a numeric entry, so still initialize them through the native setter.
    const expressionOnlySupply=index===0&&slot.value===null&&/^(VDD|VCC|VSS|VEE)$/i.test(before.info[1]||'');
    if(!expressionOnlySupply)method('CIRCEXP.dll','?SetDoubleParam@CiElement@@','void',['pointer','double','int'])(ci,args.value,index);
    const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(ci,2),text=pathString(displayExpression??String(args.value));
    const ok=method('CIRCEXP.dll','?SetExprParam@CiaParamList@@','uint8',['pointer','int','pointer','int'])(attr,index,text,1);
    native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
    if(!ok)throw new Error('Native expression setter rejected the value');
  }
  const labels=refreshComponentValue(c.id,true);
  return {before,after:parameterInfo({ref:c.id}),labels};
}
function replaceComponent(args) {
  const old=component(args.ref),attached=attachedWires(old,wires().wires);
  const created=temporaryWiring({connect_touching:false},()=>placeComponent({...args,ref:undefined,x:Math.round(old.transform[4]),y:Math.round(old.transform[5])}).component);
  copyTransform(ptr(old.id),ptr(created.id),old.transform[4],old.transform[5]);
  straightenComponentLabels(created.id);
  arrangeComponentLabels(created.id);
  const pinMap=args.pin_map||{};
  for(const w of attached)for(const end of ['source','target'])if(ownsEndpoint(old,w[end]) && !created.pins.some(p=>p.name===(pinMap[w[end].pin]||w[end].pin))){
    removeObject({id:created.id});
    throw new Error('Replacement has no matching pin '+w[end].pin+'; provide pin_map');
  }
  for(const w of attached)removeObject({id:w.id});
  removeObject({id:old.id});
  if(!/^(VDD|VSS|VCC|VEE|GND|DGND|AGND)$/i.test(args.name||'')&&component(created.id).ref!==old.ref&&!components().components.some(c=>c.id!==created.id&&c.ref===old.ref)){
    renameComponent({ref:created.id,new_ref:old.ref});
  }
  straightenComponentLabels(created.id);
  arrangeComponentLabels(created.id);
  const links=[];
  for(const w of attached){
    const endpoints={};
    for(const end of ['source','target'])
      endpoints[end]=ownsEndpoint(old,w[end])?{ref:created.id,pin:pinMap[w[end].pin]||w[end].pin}:w[end].ref?{ref:w[end].component_id||w[end].ref,pin:w[end].pin}:{junction_id:w[end].id};
    links.push(connectEndpoint(endpoints));
  }
  return {component:component(created.id),reconnected_wires:links.length};
}
function syncReferenceLabel(id,refText) {
  const label=componentLabels({ref:id}).labels.find(l=>l.kind==='reference');
  if(!label||label.text===refText)return;
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  method('Od101dll.dll','?SetText@CODTextComp@@','void',['pointer','pointer','pointer'])(ptr(label.id),Memory.allocUtf16String(refText),context);
  method('Od101dll.dll','?Update@CODComponent@@UAEX','void',['pointer','pointer','uint8'])(ptr(label.id),context,0);
}
function syncInstanceReference(manager,componentState,newRef) {
  if(componentState.ref===newRef||componentState.local_ref!==newRef)return;
  const info=method('SCH_CAP.dll','?GetInstanceRefDesInfo@CIITHierRefDesManager@@','pointer',['pointer','pointer','pointer'])(manager,treeInstance(),Memory.allocUtf16String(newRef));
  if(info.isNull())return;
  const currentNumber=method('SCH_CAP.dll','?GetIRNumber@CIITHierRefDesInfo@@','int',['pointer'])(info);
  // The native manager may allocate a different number while retaining the requested local name.
  // Only change the numeric suffix of an ordinary reference; leave section and hierarchy references alone.
  const suffix=String(currentNumber);
  if(currentNumber<0||!componentState.ref.endsWith(suffix))return;
  const prefix=componentState.ref.slice(0,-suffix.length);
  if(!newRef.startsWith(prefix))return;
  const requestedSuffix=newRef.slice(prefix.length),number=requestedSuffix===''?-1:Number(requestedSuffix);
  if(requestedSuffix!==''&&(!/^\d+$/.test(requestedSuffix)||String(number)!==requestedSuffix||number>2147483647))return;
  method('SCH_CAP.dll','?SetIRNumber@CIITHierRefDesInfo@@','void',['pointer','int'])(info,number);
}
function renameComponent(args) {
  const target=component(args.ref);
  if(rtti(ptr(target.id)).name==='.?AVCIITHierConnector@@')return updatePort({id:target.id,name:args.new_ref}).component;
  if(components().components.some(c=>c.id!==target.id&&c.ref===args.new_ref))throw new Error('Reference already exists');
  const libraryName=id=>{try{return parameterInfo({ref:id}).info[1]||'';}catch(_){return '';}};
  const initialShared=/^(GROUND|VDD|VSS|VCC|VEE|GND|DGND|AGND)$/i.test(libraryName(target.id));
  if(target.ref===args.new_ref&&target.local_ref===args.new_ref){
    if(!initialShared)syncReferenceLabel(target.id,target.ref);
    return component(target.id);
  }
  const c=target,mgr=method('SCH_CAP.dll','?GetRefDesMgr@CMultisimExtension@@','pointer',['pointer','uint'])(extension(),0),text=pathString(args.new_ref);
  method('SCH_CAP.dll','?RenameComponent@CIITHierRefDesManager@@','void',['pointer','pointer','pointer','pointer'])(mgr,ptr(c.id),treeInstance(),text);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(text);
  let after=component(c.id);
  const isSharedSupply=initialShared;
  if((after.ref!==args.new_ref && after.local_ref!==args.new_ref)||(!isSharedSupply && after.local_ref!==args.new_ref)) {
    method('CIRCEXP.dll','?SetLocalName@CiElement@@','int',['pointer','pointer'])(ciObject(ptr(c.id)),Memory.allocUtf16String(args.new_ref));
    method('SCH_CAP.dll','?SyncRefDesManager@CMultisimExtension@@','int',['pointer','uint8'])(extension(),1);
    after=component(c.id);
  }
  if(after.ref!==args.new_ref && after.local_ref!==args.new_ref)throw new Error('Native reference rename did not persist');
  if(!isSharedSupply){
    syncInstanceReference(mgr,after,args.new_ref);
    syncReferenceLabel(c.id,component(c.id).ref);
  }
  return component(c.id);
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
    straightenComponentLabels(result.component.id);
    arrangeComponentLabels(result.component.id);
    const params=parameterInfo({ref:source.id});
    for(const p of params.parameters)if(p.expression!==null&&p.expression!=='')setParameter({ref:result.component.id,index:p.index,expression:p.expression});else if(p.value!==null)setParameter({ref:result.component.id,index:p.index,value:p.value});
    arrangeComponentLabels(result.component.id);
    return {component:component(result.component.id)};
  } finally {method('SCH_CAP.dll','??1CComponentInfoRetrieve@@','void',['pointer'])(retriever);}
}
function removeObject(args) {
  let id=args.id||args.object_id;const ref=args.ref||args.component_ref;
  if(ref)id=component(ref).id;
  if(!enumerate().objects.some(c=>c.id===id))throw new Error('Object does not exist on the selected sheet');
  const nativeType=rtti(ptr(id)).name,hierarchicalPort=/^\.\?AVCIIT(?:Bus)?HierConnector@@$/.test(nativeType);
  if(rtti(ptr(id)).name==='.?AVCODNodeTextComp@@'){
    const owners=wires().wires.filter(w=>method('SCH_CAP.dll','?GetNodeText@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id)).equals(ptr(id)));
    for(const wire of owners){
      const connection=basePointer(ptr(wire.id),'.?AVCElectricalConnectionBase@@');
      method('SchematicCapture.dll','?UnSetUserNamed@CElectricalConnectionBase@@','void',['pointer'])(connection);
      method('SchematicCapture.dll','?SetNetNameHidden@CElectricalConnectionBase@@','void',['pointer','uint8'])(connection,1);
    }
    method('Od101dll.dll','?DeleteComponent@CODDiagram@@','void',['pointer','pointer','pointer','int'])(diagram().graph,treeInstance(),ptr(id),0);
    if(enumerate().objects.some(c=>c.id===id))throw new Error('Native generated net-label deletion failed: '+id);
    return {deleted:true,id,generated_net_label:true,affected_wire_ids:owners.map(w=>w.id),topology_changed:true};
  }
  const symbol=components().components.find(c=>c.id===id);
  if(symbol)for(const wire of attachedWires(symbol,wires().wires))removeObject({id:wire.id});
  const list=Memory.alloc(256);
  method('Od101dll.dll','??0CODCompList@@QAE@PAVCODComponent@@@Z','pointer',['pointer','pointer'])(list,ptr(id));
  try {
    // The fourth boolean updates CNKNodeInfo. Hierarchical port deletion needs
    // this native bookkeeping as well as removing its graphics and parent pins.
    method('SCH_CAP.dll','?DoDelete@CIITDiagram@@QAEHPAVCTreeInstance@@PAVCODCompList@@_N2222PAVCIITView@@PAVCNetSplitInfo@@@Z','int',['pointer','pointer','pointer',...Array(5).fill('uint8'),'pointer','pointer'])(diagram().graph,treeInstance(),list,0,1,0,hierarchicalPort?1:0,0,activateSheet(),ptr(0));
  } finally {method('Od101dll.dll','??1CODCompList@@UAE@XZ','void',['pointer'])(list);}
  if(enumerate().objects.some(c=>c.id===id))throw new Error('Native deletion did not remove '+id+' ('+rtti(ptr(id)).name+'); deleting a generated net label requires changing its wire label settings');
  return {deleted:true,id,topology_changed:nativeType!=='.?AVCODTextComp@@',...(hierarchicalPort?{hierarchical_port:true,node_info_updated:true}:{})};
}
function updateAttachedGeometry(id,attached) {
  const c=component(id),pins=c.pins;
  for(const wire of attached) {
    let points=wire.points.length>=2?wire.points.map(p=>({...p})):wire.points.length===1?[{...wire.points[0]},{...wire.points[0]}]:[{x:wire.source.x,y:wire.source.y},{x:wire.target.x,y:wire.target.y}];
    for(const end of ['source','target'])if(ownsEndpoint(c,wire[end])) {
      const pin=pins.find(p=>p.id===wire[end].id);if(!pin)throw new Error('Transformed pin lost its attachment');
      if(end==='source')points=points.slice().reverse();
      const old=points.at(-1),previous=points.at(-2),next={x:pin.x,y:pin.y};
      const corner=previous.y===old.y?{x:next.x,y:old.y}:{x:old.x,y:next.y};
      points=[...points.slice(0,-1),corner,next].filter((p,i,a)=>!i||p.x!==a[i-1].x||p.y!==a[i-1].y);
      if(points.length===1)points.push({...points[0]});
      if(end==='source')points.reverse();
    }
    if(points.length===1)points.push({...points[0]});
    setWirePoints(ptr(wire.id),points);
  }
  return pins;
}
function transformComponent(args) {
  const hasAngle=args.angle!==undefined,hasAxis=args.axis!==undefined;
  if(hasAngle===hasAxis)throw new Error('Provide exactly one of angle or axis');
  if(hasAngle&&(typeof args.angle!=='number'||!Number.isFinite(args.angle)))throw new Error('Rotation must be finite');
  if(hasAxis&&!['horizontal','vertical'].includes(args.axis))throw new Error('Invalid mirror axis');
  const c=component(args.ref),object=ptr(c.id),before=matrix(object),attached=attachedWires(c,wires().wires);
  const x=c.pins.length?c.pins.reduce((a,p)=>a+p.x,0)/c.pins.length:before[4],y=c.pins.length?c.pins.reduce((a,p)=>a+p.y,0)/c.pins.length:before[5];
  const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(object);
  if(hasAngle)method('Od101dll.dll','?Rotate@CODGraphic@@','void',['pointer','float','float','float'])(graphic,args.angle,x,y);
  else method('Od101dll.dll','?Scale@CODGraphic@@','void',['pointer','float','float','float','float'])(graphic,args.axis==='horizontal'?-1:1,args.axis==='vertical'?-1:1,x,y);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,object,0,0);
  refreshComponentValue(c.id,false);
  straightenComponentLabels(c.id);
  arrangeComponentLabels(c.id);
  return {id:c.id,ref:c.ref,before,after:matrix(object),pins:updateAttachedGeometry(c.id,attached),labels:componentLabels({ref:c.id}).labels};
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
  return wires().wires.find(w=>w.id===args.id);
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
function openedSheetComponents() {
  if(typeof restoreCurrentProbeLabels==='function')restoreCurrentProbeLabels();
  return components();
}
function selectSheet(args) {
  const sheets=readSheets(),sheet=sheets.find(s=>args.id?s.id===args.id:s.index===args.index);
  if(!sheet)throw new Error('Schematic sheet not found');selectedSheetId=sheet.id;cachedDiagram=null;
  activateSheet();
  const info=openedSheetComponents();return {sheet,path:info.path,component_count:info.components.length};
}
function projects() {
  const p=project(),count=method('DrwEngine.dll','?GetProjectCount@CWorkSpace@@','uint',['pointer'])(p.workspace),result=[];
  for(let index=0;index<count;index++){const obj=ptrFunction('DrwEngine.dll','?GetProject@CWorkSpace@@QAEPAVCProject@@I@Z',['pointer','uint'])(p.workspace,index);result.push({index,id:obj.toString(),path:projectPath(obj),selected:index===selectedProjectIndex});}
  return {projects:result};
}
function selectProject(args) {
  if(!projects().projects.some(p=>p.index===args.index))throw new Error('Project index not found');
  selectedProjectIndex=args.index;selectedSheetId=null;cachedDiagram=null;activateSheet();
  if(typeof restoreCurrentProbeLabels==='function')restoreCurrentProbeLabels();
  return inspect();
}
function openDocument(args) {
  const value=pathString(args.path);
  try {
    method('DrwEngine.dll','?FileOpen@CWorkspaceContainer@@QAE?AW4EOpenResult@1@ABVCPathString@@_N1@Z','int',['pointer','pointer','uint8','uint8'])(project().container,value,0,0);
    const found=projects().projects.find(p=>p.path.toLowerCase()===args.path.toLowerCase());
    if(!found)throw new Error('Native document open did not produce the requested project');
    return selectProject({index:found.index});
  }finally{native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);}
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
  selectedSheetId=null;cachedDiagram=null;
  const value=pathString(args.path);
  const opened=method('DrwEngine.dll','?FileOpen@CWorkspaceContainer@@QAE?AW4EOpenResult@1@ABVCPathString@@_N1@Z','int',['pointer','pointer','uint8','uint8'])(p.container,value,0,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);
  const target=projects().projects.find(p=>p.path.toLowerCase()===args.path.toLowerCase());
  if(!target)throw new Error('Restored native project was not found');selectedProjectIndex=target.index;cachedDiagram=null;
  if(args.original_path)setProjectPath(args.original_path);
  const count=args.sheet_index!==undefined?selectSheet({index:args.sheet_index}).component_count:openedSheetComponents().components.length;
  if(args.modified)method('DrwEngine.dll','?SetAllModified@CProject@@','void',['pointer','uint8'])(project().proj,1);
  return {closed,opened,...inspect(),components:count};
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
function escapeAccessSql(value){return String(value).replace(/'/g,"''");}
function escapeAccessLike(value){return escapeAccessSql(value).replace(/\[/g,'[[]').replace(/\*/g,'[*]').replace(/\?/g,'[?]').replace(/#/g,'[#]');}
function librarySearch(args) {
  const db=masterDb(),limit=args.limit,rawQuery=String(args.query||'');
  const sqlTerm=escapeAccessSql(rawQuery),likeTerm=escapeAccessLike(rawQuery);
  const filters=[];
  if(rawQuery)filters.push("c.Component_Name LIKE '*"+likeTerm+"*'");
  if(args.family)filters.push("f.Family_Name='"+escapeAccessSql(args.family)+"'");
  if(args.group)filters.push("g.Family_Group='"+escapeAccessSql(args.group)+"'");
  if(args.manufacturer)filters.push("c.Manufacturer='"+escapeAccessSql(args.manufacturer)+"'");
  if(args.simulatable_only)filters.push("c.Kind_ID<>2 AND m.Model_ID IS NOT NULL AND m.Model_ID<>'' AND m.Model_ID<>'DUMMY'");
  const orderExpr=rawQuery?
    "IIF(c.Component_Name='"+sqlTerm+"',0,IIF(c.Component_Name LIKE '"+likeTerm+"*',1,2)), c.Component_Name, c.Component_ID, IIF(m.Model_ID='DUMMY',1,0), m.Sec_Order":
    "c.Component_Name, c.Component_ID, IIF(m.Model_ID='DUMMY',1,0), m.Sec_Order";
  const sql=pathString("SELECT c.Component_Name, c.Component_ID, c.Family_ID, c.Manufacturer AS Manufacturer_Name, CLng(c.Kind_ID) AS Kind_ID, f.Family_Name, g.Family_Group AS Group_Name, m.Model_ID AS Model_Name FROM (((SYS_COMPONENT AS c LEFT JOIN SYS_CONFIGURATION AS f ON c.Family_ID=f.Family_ID) LEFT JOIN SYS_CONFIGURATION_GROUPS AS g ON f.Family_Group_ID=g.Family_Group_ID) LEFT JOIN SYS_MAPPING_COMP_MODEL AS m ON c.Component_ID=m.Component_ID)"+(filters.length?' WHERE '+filters.join(' AND '):'')+" ORDER BY "+orderExpr);
  method('Database.dll','?OpenSQLDirectSet@CDBComponent@@','void',['pointer','pointer'])(db,sql.readPointer());
  const results=[],seenIds=new Set();
  try {
    if(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db))method('Database.dll','?MoveFirstRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
    while(!method('Database.dll','?IsEOFRecord_SQLDirectSet@CDBComponent@@','uint8',['pointer'])(db)&&(limit==null||results.length<limit)) {
      const idKey=pathString('Component_ID'),idOut=Memory.alloc(4);idOut.writeS32(0);
      const hasId=method('Database.dll','?GetFieldValue_SQLDirectSet@CDBComponent@@QAE_NABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@AAJ@Z','uint8',['pointer','pointer','pointer'])(db,idKey,idOut);
      native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(idKey);
      const componentId=hasId?idOut.readS32():null;
      if(componentId!==null&&seenIds.has(componentId)){
        method('Database.dll','?MoveNextRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
        continue;
      }
      if(componentId!==null)seenIds.add(componentId);
      const item={...(componentId!==null?{Component_ID:componentId}:{})};
      for(const column of ['Component_Name','Family_Name','Group_Name','Manufacturer_Name','Model_Name']) {
        const key=pathString(column),out=pathString('');
        const ok=method('Database.dll','?GetFieldValue_SQLDirectSet@CDBComponent@@QAE_NABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@AAV23@@Z','uint8',['pointer','pointer','pointer'])(db,key,out);
        item[column]=ok?out.readPointer().readUtf16String():'';
        native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(key);native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(out);
      }
      for(const column of ['Family_ID','Kind_ID']) {
        const key=pathString(column),out=Memory.alloc(4);out.writeS32(0);
        const ok=method('Database.dll','?GetFieldValue_SQLDirectSet@CDBComponent@@QAE_NABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@AAJ@Z','uint8',['pointer','pointer','pointer'])(db,key,out);
        if(ok)item[column]=out.readS32();native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(key);
      }
      item.Simulatable=Boolean(item.Model_Name&&item.Model_Name.toUpperCase()!=='DUMMY'&&item.Kind_ID!==2);
      results.push(item);method('Database.dll','?MoveNextRecord_SQLDirectSet@CDBComponent@@','void',['pointer'])(db);
    }
  } finally {method('Database.dll','?CloseSQLDirectSet@CDBComponent@@','void',['pointer'])(db);}
  const qLower=rawQuery.toLowerCase();
  const rank=name=>{
    if(!qLower)return 0;
    const n=(name||'').toLowerCase();
    return n===qLower?0:n.startsWith(qLower)?1:2;
  };
  results.sort((a,b)=>rank(a.Component_Name)-rank(b.Component_Name)||(a.Component_Name||'').localeCompare(b.Component_Name||'')||((a.Component_ID||0)-(b.Component_ID||0)));
  return {query:args.query,results:limit==null?results:results.slice(0,limit)};
}
function placeComponent(args) {
  masterDb();
  const handler=method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')(),record=Memory.alloc(2048);
  method('compedit.dll','??0CDataRecordComponent@@QAE@XZ','pointer',['pointer'])(record);
  const values=[args.family||'',args.group||'',args.name,args.manufacturer||''].map(pathString);
  try {
    const found=method('SCH_CAP.dll','?PrepDataRecordForNewComponent@CComponentHandler@@','uint8',['pointer','pointer','pointer','pointer','pointer','int','int','pointer','uint8'])(handler,...values,0,-1,record,0);
    if(!found)throw new Error('The native library could not resolve this component name/family/group');
    const result=generateRecord(record,args);
    if(wiringOptions().connect_touching){
      result.touching=connectTouching({refs:[result.component.id]});
      result.component={...result.component,...component(result.component.id)};
    }
    return result;
  } finally {for(const v of values)native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(v);method('compedit.dll','??1CDataRecordComponent@@UAE@XZ','void',['pointer'])(record);}
}
function generateRecord(record,args) {
  activateSheet();
  validatePlacement(args);
  const requestedRef=args.ref;
  const duplicate=args.ref && components().components.some(c=>c.ref===args.ref);
  const powerDefault=/^(GROUND|VDD|VSS|VCC|VEE|GND|DGND|AGND)$/i.test(args.name||'') &&
    (args.ref==='0'||args.ref?.toUpperCase()===args.name.toUpperCase());
  if(duplicate&&!powerDefault)throw new Error('Reference already exists on this sheet');
  if(duplicate)args={...args,ref:undefined};
  const d=diagram(),handler=method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')(),name=pathString(''),out=Memory.alloc(4);out.writePointer(ptr(0));
  if(treeInstance().isNull())throw new Error('Selected sheet has no native tree instance');
  // The first two integer arguments are section index and place flag, NOT coordinates.
  const result=method('SCH_CAP.dll','?GenerateNewComponentFromDataRecord@CComponentHandler@@','int',['pointer','pointer','pointer','int','int','pointer','pointer','int','int','pointer','pointer','pointer'])(handler,out,name,1,1,d.graph,treeInstance(),1,0,ptr(0),ptr(0),record);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);
  const object=out.readPointer();if(object.isNull())throw new Error('Native component factory returned null: '+result);
  let c=component(object.toString());
  const others=components().components.filter(p=>p.id!==c.id),stem=(c.local_ref.match(/^[A-Za-z_]+/)||['X'])[0];let suffix=1;
  while(others.some(p=>p.ref===stem+suffix))suffix++;
  // Global supply symbols deliberately share a canonical reference. Their
  // object IDs, not a fabricated ref suffix, identify the placed instances.
  const sharedPower=/^(VDD|VSS|VCC|VEE|GND|DGND|AGND)$/i.test(args.name||'');
  const ref=args.ref||(sharedPower?c.ref:!others.some(p=>p.ref===c.local_ref)?c.local_ref:stem+suffix);
  if(c.ref!==ref)renameComponent({ref:c.id,new_ref:ref});
  // Match standalone transform order, then resolve the final anchor.
  if(args.angle!==undefined)transformComponent({ref:c.id,angle:args.angle});
  if(args.mirror_axis!==undefined)transformComponent({ref:c.id,axis:args.mirror_axis});
  c=component(c.id);
  const origin=matrix(object),anchor=args.anchor||'origin';
  let point={x:origin[4],y:origin[5]};
  if(anchor==='pin'){
    point=c.pins.find(p=>p.name===args.pin);
    if(!point)throw new Error('Placement anchor pin not found: '+args.pin+'; available pins: '+c.pins.map(p=>p.name).join(', '));
  }else if(anchor==='center'){
    const b=symbolBodyBounds(c);point={x:(b.left+b.right)/2,y:(b.top+b.bottom)/2};
  }
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(d.graph,object,Math.round(args.x-point.x),Math.round(args.y-point.y));
  const initialMeta=parameterInfo({ref:c.id});
  const parameters=(args.parameters||[]).map(p=>{
    if(p.index!==undefined&&p.index!==null)return p;
    const wantName=p.name,wantRole=p.role||(wantName?undefined:'value');
    const matches=initialMeta.parameters.filter(s=>(!wantName||s.name===wantName)&&(!wantRole||s.role===wantRole));
    if(matches.length!==1){
      const available=initialMeta.parameters.filter(s=>s.name||s.role).map(s=>`${s.index}:${s.name||s.role}`).join(', ')||'none';
      throw new Error(`Expected one matching parameter slot for ${JSON.stringify({name:wantName,role:wantRole})} on ${c.ref}; found ${matches.length} (available: ${available})`);
    }
    return {...p,index:matches[0].index};
  });
  if('value' in args||'expression' in args){
    const slots=initialMeta.parameters.filter(p=>p.role==='value');
    if(slots.length!==1)throw new Error('Primary value slot is ambiguous; provide indexed parameters');
    if(parameters.some(p=>p.index===slots[0].index))throw new Error('Primary value supplied twice');
    const value=args.expression??args.value;
    parameters.push({index:slots[0].index,[typeof value==='string'?'expression':'value']:value});
  }
  if(args.params){
    for(const [paramName,val] of Object.entries(args.params)){
      const slots=initialMeta.parameters.filter(p=>p.name===paramName);
      if(slots.length!==1){
        const available=initialMeta.parameters.filter(s=>s.name).map(s=>s.name).join(', ')||'none';
        throw new Error(`Unknown parameter name ${JSON.stringify(paramName)} on ${c.ref} (available: ${available})`);
      }
      if(parameters.some(p=>p.index===slots[0].index))throw new Error(`Parameter ${JSON.stringify(paramName)} supplied twice`);
      parameters.push({index:slots[0].index,[typeof val==='string'?'expression':'value']:val});
    }
  }
  const primary=initialMeta.parameters.filter(p=>p.role==='value').map(p=>p.index);
  for(const parameter of parameters){
    const display='value' in parameter&&primary.includes(parameter.index)?engineeringExpression(parameter.value):null;
    setParameter({ref:c.id,...parameter},display);
  }
  c=component(object.toString());
  const metadata=parameterInfo({ref:c.id});
  const body=symbolBodyBounds(c),actual=anchor==='pin'?c.pins.find(p=>p.name===args.pin):anchor==='center'?{x:(body.left+body.right)/2,y:(body.top+body.bottom)/2}:{x:c.transform[4],y:c.transform[5]};
  const placement={coordinate_system:'sheet_units',pin_offsets:c.pins.map(p=>({name:p.name,dx:p.x-actual.x,dy:p.y-actual.y})),anchor,...(anchor==='pin'?{pin:args.pin}:{}),requested:{x:args.x,y:args.y},actual:{x:actual.x,y:actual.y},origin:{x:c.transform[4],y:c.transform[5]},body_bounds:body};
  const page=pageGeometry(),offPage=body.left<0||body.top<0||body.right>page.width||body.bottom>page.height;
  const warnings=offPage?[{code:'outside_page',reference:c.ref,message:'Component is outside the page. Use fit_content or a region to include it in the exported image.'}]:[];
  if(duplicate)warnings.push({code:'reference_auto_assigned',requested_ref:requestedRef,reference:c.ref,component_id:c.id,message:'Multisim assigned this power-symbol instance. Global supply references may be shared; use the unique component ID or a workflow binding.'});
  for(const p of metadata.parameters)if(p.role==='value'&&p.value===null&&!p.expression?.trim())warnings.push({code:'unset_value',reference:c.ref,index:p.index,name:p.name,message:'Set the primary component value before analysis.'});
  return {component:{...c,library:{family:metadata.info[0],name:metadata.info[1],symbol_family:metadata.info[2],model:metadata.info[3]},default_reference_prefix:stem},parameters:metadata.parameters,page,
    placement,labels:componentLabels({ref:c.id}).labels,warnings};
}
function engineeringExpression(value){
  if(value===0)return '0';
  const prefixes={[-15]:'f',[-12]:'p',[-9]:'n',[-6]:'u',[-3]:'m',0:'',3:'k',6:'Meg',9:'G',12:'T'};
  const exponent=Math.floor(Math.log10(Math.abs(value))/3)*3;
  if(!(exponent in prefixes))return String(value);
  // Avoid binary floating-point tails in displayed engineering values.
  return String(Number((value/10**exponent).toPrecision(15)))+prefixes[exponent];
}
function allocateObject(className,constructor,args,types) {
  const type=method('Od101dll.dll','?GetThisClass@'+className+'@@','pointer',[],'stdcall')();
  const size=type.add(4).readU32();if(size<4)throw new Error('Invalid native object size');
  const getProc=ptrFunction('kernel32.dll','GetProcAddress',['pointer','pointer'],'stdcall');
  const address=getProc(Process.getModuleByName('mfc140u.dll').base,ptr(1511));
  const object=new NativeFunction(address,'pointer',['uint'],'mscdecl')(size);
  method('Od101dll.dll',constructor,'pointer',['pointer',...types])(object,...args);return object;
}
function addText(args) {
  const object=allocateObject('CODTextComp','??0CODTextComp@@QAE@PB_W@Z',[Memory.allocUtf16String(args.text)],['pointer']);
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(diagram().graph,object,args.x,args.y,treeInstance(),0);
  return textObjects().find(t=>t.id===object.toString());
}
function textObjects() {
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  return listChildren(diagram().composite).filter(o=>rtti(o).name==='.?AVCODTextComp@@').map(o=>{
    const graphic=method('Od101dll.dll','?GetGraphic@CODComponent@@QAEP','pointer',['pointer'])(o),rect=Memory.alloc(16);
    method('Od101dll.dll','?GetBox@CODGraphic@@QAEXAAVCRect@@AAVCODInstContext@@@Z','void',['pointer','pointer','pointer'])(graphic,rect,context);
    const [x1,y1,x2,y2]=[0,4,8,12].map(n=>rect.add(n).readS32()),transform=matrix(o);
    return {id:o.toString(),text:instanceString('Od101dll.dll','?GetText@CODTextComp@@',o,[treeInstance()],['pointer']),
      x:transform[4],y:transform[5],transform,bounds:{left:Math.min(x1,x2),top:Math.min(y1,y2),right:Math.max(x1,x2),bottom:Math.max(y1,y2)}};
  });
}
function updateText(args) {
  const before=textObjects().find(t=>t.id===args.id);if(!before)throw new Error('Free text object does not exist on the selected sheet: '+args.id);
  const object=ptr(before.id),context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  if(args.text!==undefined)method('Od101dll.dll','?SetText@CODTextComp@@','void',['pointer','pointer','pointer'])(object,Memory.allocUtf16String(args.text),context);
  if(args.x!==undefined||args.y!==undefined)method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,object,(args.x??before.x)-before.x,(args.y??before.y)-before.y);
  method('Od101dll.dll','?Update@CODComponent@@UAEXAAVCODInstContext@@_N@Z','void',['pointer','pointer','uint8'])(object,context,0);
  return {...textObjects().find(t=>t.id===args.id),before};
}
function deleteText(args) {
  if(!textObjects().some(t=>t.id===args.id))throw new Error('Free text object does not exist on the selected sheet: '+args.id);
  return removeObject(args);
}
function labelWire(args) {
  if(typeof args.name!=='string'||!args.name.trim()||args.name.includes('\0'))throw new Error('Wire net name must not be empty');
  const allWires=wires().wires,w=allWires.find(x=>x.id===args.id);if(!w)throw new Error('Wire does not exist');
  const node=method('SCH_CAP.dll','?GetNode@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));
  const currentTree=treeInstance();
  const container=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(currentTree);
  const network=wireNetworks(allWires),wNet=network(w.source.id),requested=args.name.toLowerCase();
  const isExplicitOrGlobalNet=name=>Boolean(name&&!/^[1-9]\d*$/.test(name));
  const currentWireSpice=spiceNetName(basePointer(ptr(w.id),'.?AVCSCH_CAPElectricalConnection@@'),true);
  const sameGlobalRail=name=>Boolean(name&&currentWireSpice&&name.toLowerCase()===currentWireSpice.toLowerCase()&&isExplicitOrGlobalNet(currentWireSpice));
  const checkSheetConflicts=isCurrentSheet=>{
    const sheetWires=isCurrentSheet?allWires:wires().wires;
    for(const other of sheetWires){
      if(isCurrentSheet&&(other.id===w.id||network(other.source.id)===wNet))continue;
      const otherNode=method('SCH_CAP.dll','?GetNode@CIITLinkComp@@','pointer',['pointer'])(ptr(other.id));
      if(!node.isNull()&&!otherNode.isNull()&&node.equals(otherNode))continue;
      const otherConn=basePointer(ptr(other.id),'.?AVCSCH_CAPElectricalConnection@@');
      const otherSpice=spiceNetName(otherConn,true);
      const existing=persistentWireLabel(other.id)?.name
        ||(otherNode.isNull()?null:(nativeWireLabel(other.id).user_named?returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',otherNode):null))
        ||(isExplicitOrGlobalNet(otherSpice)?otherSpice:null);
      if(existing&&existing.toLowerCase()===requested&&!sameGlobalRail(existing))
        throw new Error(`Net name ${JSON.stringify(args.name)} already exists on another net; Multisim requires unique wire net names (connect with a wire, junction, power symbol, or On-Page connector instead).`);
    }
    for(const c of components().components){
      const libName=componentLibraryInfo(ciObject(ptr(c.id)))[1]||'';
      if(!/^(GROUND|VDD|VSS|VCC|VEE|GND|DGND|AGND)$/i.test(libName))continue;
      const ci=ciObject(ptr(c.id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci);
      for(let idx=0;idx<count;idx++){
        const pinObj=c.pins[idx];
        if(isCurrentSheet&&pinObj&&network(pinObj.id)===wNet)continue;
        const portNode=method('CIRCEXP.dll','?GetNode@CiComponent@@','pointer',['pointer','int'])(ci,idx);
        if(!node.isNull()&&!portNode.isNull()&&node.equals(portNode))continue;
        const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,idx);
        const railName=spiceNetName(port)||(portNode.isNull()?null:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',portNode)||null)||(/^GROUND$/i.test(libName)?'0':c.ref);
        if(railName&&railName.toLowerCase()===requested&&!sameGlobalRail(railName))
          throw new Error(`Net name ${JSON.stringify(args.name)} already exists on another net; Multisim requires unique wire net names (connect with a wire, junction, power symbol, or On-Page connector instead).`);
      }
    }
  };
  checkSheetConflicts(true);
  const allSheets=readSheets();
  if(allSheets.length>1){
    const currentSheetId=diagram().sheet.toString(),savedSheetId=selectedSheetId;
    const currentParent=method('DrwEngine.dll','?GetParent@CTreeInstance@@','pointer',['pointer'])(currentTree);
    try{
      for(const sheet of allSheets){
        if(sheet.id===currentSheetId)continue;
        selectedSheetId=sheet.id;cachedDiagram=null;
        const sheetTree=treeInstance();
        const sheetContainer=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(sheetTree);
        const sheetParent=method('DrwEngine.dll','?GetParent@CTreeInstance@@','pointer',['pointer'])(sheetTree);
        if(sheetContainer.equals(container)||(currentParent.isNull()&&sheetParent.isNull()))checkSheetConflicts(false);
      }
    }finally{selectedSheetId=savedSheetId;cachedDiagram=null;}
  }
  const connection=basePointer(ptr(w.id),'.?AVCElectricalConnectionBase@@');
  const proxy=Memory.alloc(128),pool=Memory.alloc(64);
  method('DrwEngine.dll','??0CTreeInstanceProxy@@QAE@PAVCTreeInstance@@@Z','pointer',['pointer','pointer'])(proxy,treeInstance());
  method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(pool,Memory.allocUtf16String(args.name));
  method('SchematicCapture.dll','?SetUserNamed@CElectricalConnectionBase@@','pointer',['pointer','pointer','pointer','pointer','uint8'])(connection,container,proxy,pool,1);
  if(!node.isNull())method('CIRCEXP.dll','?SetLocalName@CiElement@@','int',['pointer','pointer'])(node,Memory.allocUtf16String(args.name));
  method('SchematicCapture.dll','?SetNetNameHidden@CElectricalConnectionBase@@','void',['pointer','uint8'])(connection,0);
  method('Od101dll.dll','?SetShowWhenUsingNetSettings@CODLinkComp@@','void',['pointer','uint8'])(ptr(w.id),1);
  method('DrwEngine.dll','??1CTreeInstanceProxy@@','void',['pointer'])(proxy);method('Library.dll','??1CPoolString@@','void',['pointer'])(pool);
  let label=method('SCH_CAP.dll','?GetNodeText@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));
  if(label.isNull()) {
    const anchor=w.points[0]||w.source;
    label=allocateObject('CODNodeTextComp','??0CODNodeTextComp@@QAE@PB_W@Z',[Memory.allocUtf16String(args.name)],['pointer']);
    method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(diagram().graph,label,anchor.x,anchor.y-18,treeInstance(),0);
    method('SCH_CAP.dll','?SetNodeText@CIITLinkComp@@','void',['pointer','pointer'])(ptr(w.id),label);
    method('Od101dll.dll','?AddLinkComp@CODNodeTextComp@@','void',['pointer','pointer'])(label,ptr(w.id));
  }
  method('Od101dll.dll','?SetTextNoUpdate@CODTextComp@@','void',['pointer','pointer'])(label,Memory.allocUtf16String(args.name));
  const resolvedName=node.isNull()?(persistentWireLabel(w.id)?.name||args.name):(returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',node)||persistentWireLabel(w.id)?.name||args.name);
  return {id:w.id,node:node.toString(),name:resolvedName,label:label.toString(),topology_changed:true};
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
  const target=component(args.ref);
  if(typeof isInstrumentSymbol==='function'&&isInstrumentSymbol(ptr(target.id))){
    throw new Error(target.ref+' is a virtual instrument whose SPICE subcircuit is generated dynamically from its settings; use native_set_instrument_settings instead.');
  }
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
  try {
    for(const sheet of readSheets()){
      selectSheet({index:sheet.index});
      for(const c of components().components)if(method('CIRCEXP.dll','?GetModel@CiElement@@','pointer',['pointer'])(ciObject(ptr(c.id))).toString()===info.model)
        refreshComponentValue(c.id);
    }
  }finally{selectedSheetId=selected;cachedDiagram=null;activateSheet();}
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
  updateParentSymbol();
  return {symbol_id:symbol.toString(),type:rtti(symbol),components:components().components};
}
function updateParentSymbol() {
  const tree=treeInstance(),parent=method('DrwEngine.dll','?GetParent@CTreeInstance@@','pointer',['pointer'])(tree),sc=method('DrwEngine.dll','?GetSheetComponent@CTreeInstance@@','pointer',['pointer'])(tree);
  const block=method('SCH_CAP.dll','?GetHierBlock@CSheetComponentMSM@@','pointer',['pointer'])(sc);
  if(!parent.isNull()&&!block.isNull())method('SCH_CAP.dll','?UpdateSymbol@CHierBlock@@','int',['pointer','pointer','uint8'])(block,parent,1);
}
function updatePort(args) {
  const before=component(args.id),object=ptr(before.id);
  if(rtti(object).name!=='.?AVCIITHierConnector@@')throw new Error('Object is not a hierarchical connector');
  if(args.name!==undefined&&args.name!==before.local_ref){
    if(!args.name.length)throw new Error('Hierarchical connector name must not be empty');
    const tree=treeInstance(),container=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(tree),name=Memory.alloc(64);
    method('Library.dll','??0CPoolString@@QAE@PB_W@Z','pointer',['pointer','pointer'])(name,Memory.allocUtf16String(args.name));
    // This virtual implementation receives the CConnector interface subobject.
    try{method('SCH_CAP.dll','?SetName@CIITHierConnector@@','void',['pointer','pointer','pointer','pointer'])(basePointer(object,'.?AVCConnector@@'),container,tree,name);}
    finally{method('Library.dll','??1CPoolString@@','void',['pointer'])(name);}
    updateParentSymbol();
    if(component(before.id).local_ref!==args.name)throw new Error('Native hierarchical connector rename failed');
  }
  const moved=args.x!==undefined||args.y!==undefined?move({ref:before.id,dx:(args.x??before.transform[4])-before.transform[4],dy:(args.y??before.transform[5])-before.transform[5]}):null;
  return {component:component(before.id),before,movement:moved,topology_changed:(args.name!==undefined&&args.name!==before.local_ref)||!!moved?.topology_changed};
}
function sheetTitle(args) {
  if(!method('DrwEngine.dll','?GetParent@CTreeInstance@@','pointer',['pointer'])(treeInstance()).isNull())return updateSheet({title:args.title,page:args.title});
  const name=pathString(args.title);
  // The root window caption follows the filename on reopen. Persist the native
  // page name as well; changing only SetTitle previously changed a live caption.
  method('DrwEngine.dll','?SetPageName@CDrwSubSheet@@','void',['pointer','pointer','uint8'])(diagram().sheet,name,1);
  method('DrwEngine.dll','?SetTitle@CDrwSubSheet@@','void',['pointer','pointer','uint8'])(diagram().sheet,name,0);
  native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);return {sheets:readSheets()};
}
function updateSheet(args) {
  const d=diagram(),before=readSheets().find(s=>s.selected);
  // Setters update the drawing; workspace notifications migrate hierarchical reference maps.
  if(args.title!==undefined){
    const old=pathString(before.title),name=pathString(args.title);
    try{
      method('DrwEngine.dll','?SetTitle@CDrwSubSheet@@','void',['pointer','pointer','uint8'])(d.sheet,name,0);
      method('DrwEngine.dll','?RenameSheet@CWorkspaceContainer@@','void',['pointer','pointer','pointer','pointer'])(d.container,old,name,d.sheet);
    }
    finally{for(const v of [old,name])native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(v);}
  }
  if(args.page!==undefined){
    const old=pathString(before.page),page=pathString(args.page);
    try{
      method('DrwEngine.dll','?SetPageName@CDrwSubSheet@@','void',['pointer','pointer','uint8'])(d.sheet,page,1);
      method('DrwEngine.dll','?RenamePage@CWorkspaceContainer@@','void',['pointer','pointer','pointer','pointer'])(d.container,old,page,d.sheet);
    }
    finally{for(const v of [old,page])native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(v);}
  }
  if(args.width!==undefined||args.height!==undefined){const current=pageGeometry();sheetSize({width:args.width??current.width,height:args.height??current.height});}
  return {sheet:readSheets().find(s=>s.selected),sheets:readSheets(),topology_changed:args.title!==undefined||args.page!==undefined};
}
function sheetSize(args) {
  if(['width','height'].some(k=>Math.round(args[k]/96*25.4*500000)>2147483647))throw new Error('Sheet dimensions exceed the native signed 32-bit CUTRect work-area format');
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
function wiringSettings() {
  return method('SCH_CAP.dll','?GetSCH_CAPDocTypeSettings@@','pointer',[],'mscdecl')();
}
function wiringOptions(args={}) {
  const settings=wiringSettings();
  if(settings.isNull())throw new Error('Native schematic wiring settings are unavailable');
  const fields={autowire_on_connection:['IsAutowireOnConnection','SetAutowireOnConnection','uint8'],
    autowire_on_move:['IsAutowireOnMove','SetAutowireOnMove','uint8'],
    connect_touching:['IsAutowirePinTouching','SetAutowirePinTouching','uint8'],
    move_connection_limit:['GetAutowirePinConnections','SetAutowirePinConnections','int']};
  const read=()=>Object.fromEntries(Object.entries(fields).map(([key,[get,,type]])=>{
    const value=method('SCH_CAP.dll','?'+get+'@CSCH_CAPDocTypeSettings@@',type,['pointer'])(settings);
    return [key,type==='uint8'?!!value:value];
  }));
  for(const key of Object.keys(args))if(key!=='reset'&&!(key in fields))throw new Error('Unknown wiring option: '+key);
  for(const [key,value] of Object.entries(args))if(key==='move_connection_limit'){
    if(!Number.isInteger(value)||value<1||value>2147483647)throw new Error('move_connection_limit must be a positive signed 32-bit integer');
  }else if(typeof value!=='boolean')throw new Error(key+' must be boolean');
  if(args.reset&&Object.keys(args).length>1)throw new Error('Use reset alone to restore wiring options');
  const before=read();
  const changes=args.reset?(originalWiringOptions||{}):args;
  if(Object.keys(changes).some(k=>k in fields)&&!originalWiringOptions)originalWiringOptions=before;
  for(const [key,value] of Object.entries(changes))if(key in fields){
    const [,set,type]=fields[key];method('SCH_CAP.dll','?'+set+'@CSCH_CAPDocTypeSettings@@','void',['pointer',type])(settings,type==='uint8'?Number(value):value);
  }
  if(args.reset)originalWiringOptions=null;
  return {...read(),backend:'multisim-native',scope:'session',restored_on_close:true};
}
function closeWiringOptions(){if(originalWiringOptions)wiringOptions({reset:true});}
function persistWiringOptions() {
  const before=wiringOptions(),keys=['autowire_on_connection','autowire_on_move','connect_touching','move_connection_limit'];
  method('SCH_CAP.dll','?SaveSettings@CSCH_CAPDocTypeSettings@@','void',['pointer'])(wiringSettings());
  method('SCH_CAP.dll','?LoadSettings@CSCH_CAPDocTypeSettings@@','void',['pointer'])(wiringSettings());
  const after=wiringOptions();
  if(keys.some(k=>before[k]!==after[k]))throw new Error('Native application wiring preferences failed reload verification');
  originalWiringOptions=null;
  return {...after,scope:'application',persisted_in_circuit:false,saved_to_application:true,restored_on_close:false};
}
function temporaryWiring(options,callback){
  const before=wiringOptions();
  try{wiringOptions(options);return callback();}
  finally{wiringOptions(Object.fromEntries(Object.keys(options).map(k=>[k,before[k]])));}
}
function nativeDrop(object,dx=0,dy=0){
  const d=diagram(),tree=treeInstance();
  const getProc=ptrFunction('kernel32.dll','GetProcAddress',['pointer','pointer'],'stdcall');
  const allocate=new NativeFunction(getProc(Process.getModuleByName('mfc140u.dll').base,ptr(1511)),'pointer',['uint'],'mscdecl');
  const list=allocate(28);if(list.isNull())throw new Error('Native component list allocation failed');
  method('Od101dll.dll','??0CODCompList@@QAE@PAVCODComponent@@@Z','pointer',['pointer','pointer'])(list,object);
  // DropComponentsOnDiagram transfers the heap action/list to the native undo engine.
  const action=allocateObject('CODMoveAct','??0CODMoveAct@@QAE@PAVCTreeInstance@@PAVCODCompList@@MM@Z',
    [tree,list,dx,dy],['pointer','pointer','float','float']);
  method('Od101dll.dll','?SetActDiagram@CODAction@@','void',['pointer','pointer'])(action,d.graph);
  const result=method('SCH_CAP.dll','?DropComponentsOnDiagram@@','int',
    ['pointer','pointer','pointer',...Array(7).fill('uint8'),'pointer','uint8'],'mscdecl')
    (d.graph,tree,action,1,1,1,0,0,0,0,ptr(0),0);
  if(result<0)throw new Error('Native component drop failed: '+result);
  return result;
}
function nativeNodeInfo(){
  const graph=diagram().graph;
  if(nodeInfoOffset!==null){const p=graph.add(nodeInfoOffset).readPointer();if(!p.isNull()&&p.add(4).readPointer().equals(graph))return p;}
  // Resolve the member used by the exported rotation handler's call to Relink.
  // Validate its back-reference instead of fixing a build-specific member offset.
  const module=Process.getModuleByName('SCH_CAP.dll'),exports=module.enumerateExports();
  const start=exports.find(e=>e.name.startsWith('?Advanced_Rotate_Flip@CIITDiagram@@'))?.address;
  const target=exports.find(e=>e.name.startsWith('?Relink@CNKNodeInfo@@'))?.address;
  if(!start||!target)throw new Error('Native movement relinking interface is unavailable');
  const bytes=new Uint8Array(start.readByteArray(0x4000)),view=new DataView(bytes.buffer);
  for(let n=0;n<bytes.length-5;n++)if(bytes[n]===0xe8&&start.add(n+5+view.getInt32(n+1,true)).equals(target)){
    for(let k=n-6;k>=Math.max(0,n-80);k--)if(bytes[k]===0x8b&&(bytes[k+1]&0xf8)===0x88){
      const offset=view.getUint32(k+2,true);if(offset<16||offset>4096)continue;
      try{const p=graph.add(offset).readPointer();if(!p.isNull()&&p.add(4).readPointer().equals(graph)){nodeInfoOffset=offset;return p;}}catch(_){}
    }
  }
  throw new Error('Native movement relinking context could not be resolved');
}
function relinkNativeComponent(object){
  const d=diagram(),tree=treeInstance(),info=nativeNodeInfo(),list=Memory.alloc(64);
  method('Od101dll.dll','??0CODCompList@@QAE@PAVCODComponent@@@Z','pointer',['pointer','pointer'])(list,object);
  try{
    method('SCH_CAP.dll','?UpdateForNodeInfo@CNKNodeInfo@@','void',['pointer','pointer','uint8'])(info,tree,0);
    method('SCH_CAP.dll','?Relink@CNKNodeInfo@@','void',['pointer','pointer','pointer','pointer','uint8','uint8','uint8'])(info,tree,d.graph,list,0,0,0);
  }finally{method('Od101dll.dll','??1CODCompList@@UAE@XZ','void',['pointer'])(list);}
}
function routeEndsMatch(wire){return wire.points.length>=2&&['source','target'].every((end,n)=>{
  const p=wire.points[n?wire.points.length-1:0];return p.x===wire[end].x&&p.y===wire[end].y;
});}
function nativeRouteInBounds(source,target){
  const page=pageGeometry();return [source,target].every(p=>p.x>=0&&p.y>=0&&p.x<=page.width&&p.y<=page.height);
}
function orthogonalRoutePoints(s,t){
  const points=[{x:s.x,y:s.y},{x:s.x,y:t.y},{x:t.x,y:t.y}].filter((p,i,a)=>!i||p.x!==a[i-1].x||p.y!==a[i-1].y);
  if(points.length===1)points.push({...points[0]});return points;
}
function persistentWireLabel(id){
  const connection=basePointer(ptr(id),'.?AVCElectricalConnectionBase@@');
  const user_named=!!method('SchematicCapture.dll','?IsUserNamed@CElectricalConnectionBase@@','uint8',['pointer'])(connection);
  if(!user_named)return null;
  const container=method('SchematicCapture.dll','?GetNetContainerFromTreeInstance@CElectricalConnectionBase@@','pointer',['pointer'],'mscdecl')(treeInstance());
  const proxy=Memory.alloc(128);
  method('DrwEngine.dll','??0CTreeInstanceProxy@@QAE@PAVCTreeInstance@@@Z','pointer',['pointer','pointer'])(proxy,treeInstance());
  try{
    const value=Memory.alloc(64);
    method('SchematicCapture.dll','?GetUserNamedName@CElectricalConnectionBase@@','pointer',['pointer','pointer','pointer','pointer'])(connection,value,container,proxy);
    try{return {name:method('Library.dll','?GetCharString@CPoolString@@','pointer',['pointer'])(value).readUtf16String(),hidden:!!method('SchematicCapture.dll','?IsNetNameHidden@CElectricalConnectionBase@@','uint8',['pointer'])(connection)};}
    finally{method('Library.dll','??1CPoolString@@','void',['pointer'])(value);}
  }finally{method('DrwEngine.dll','??1CTreeInstanceProxy@@','void',['pointer'])(proxy);}
}
function nativeWireLabel(id){
  const wire=ptr(id),label=method('SCH_CAP.dll','?GetNodeText@CIITLinkComp@@','pointer',['pointer'])(wire),
    connection=basePointer(wire,'.?AVCElectricalConnectionBase@@');
  return {id:label.isNull()?null:label.toString(),
    text:label.isNull()?null:instanceString('Od101dll.dll','?GetText@CODTextComp@@',label,[treeInstance()],['pointer']),
    hidden:!!method('SchematicCapture.dll','?IsNetNameHidden@CElectricalConnectionBase@@','uint8',['pointer'])(connection),
    user_named:!!method('SchematicCapture.dll','?IsUserNamed@CElectricalConnectionBase@@','uint8',['pointer'])(connection)};
}
function nativeRoutePoints(source,target,wireId){
  if(!nativeRouteInBounds(source,target))return orthogonalRoutePoints(source,target);
  if(!nativeRouteFunction){
    const module=Process.getModuleByName('SCH_CAP.dll'),entry=module.enumerateExports().find(e=>e.name.startsWith('?CreateWireBase@CBackAnnotationTarget@@'));
    if(!entry)throw new Error('Native wire routing factory is unavailable');
    let p=entry.address,targetAddress=null,previous=[];
    for(let n=0;n<1200;n++){
      const instruction=Instruction.parse(p),next=Instruction.parse(instruction.next);
      if(instruction.mnemonic==='call'&&/^0x/.test(instruction.opStr)&&next.mnemonic==='add'&&next.opStr==='esp, 0x30'&&
         previous.length>=2&&previous.at(-1).mnemonic==='lea'&&/^ecx,/.test(previous.at(-1).opStr)&&
         previous.at(-2).mnemonic==='lea'&&/^edx,/.test(previous.at(-2).opStr)){
        targetAddress=ptr(instruction.opStr);break;
      }
      if(instruction.mnemonic==='ret')break;
      previous.push(instruction);p=instruction.next;
    }
    if(!targetAddress||Process.findModuleByAddress(targetAddress)?.name.toLowerCase()!=='sch_cap.dll')
      throw new Error('Native wire routing entry could not be resolved');
    // The internal router uses ECX/EDX arguments with caller stack cleanup.
    // Adapt it to stdcall without rewriting any native application code.
    const bytes=[0x55,0x8b,0xec];
    for(let n=13;n>=2;n--)bytes.push(0xff,0x75,8+n*4);
    bytes.push(0x8b,0x4d,8,0x8b,0x55,12,0xb8,...[0,8,16,24].map(n=>(targetAddress.toUInt32()>>>n)&255),
      0xff,0xd0,0x83,0xc4,0x30,0x8b,0xe5,0x5d,0xc2,0x38,0);
    const code=Memory.alloc(Process.pageSize);code.writeByteArray(bytes);Memory.protect(code,Process.pageSize,'r-x');keep.push(code);
    nativeRouteFunction=new NativeFunction(code,'pointer',
      ['pointer','pointer','pointer','pointer','pointer','int','int','int','pointer',...Array(5).fill('int')],'stdcall');
  }
  const d=diagram(),handler=Memory.alloc(16),context=Memory.alloc(24),count=Memory.alloc(4);
  // Borrow the same drawing context and tree handler layout as CreateWireBase.
  handler.writePointer(treeInstance());handler.add(4).writeU32(255);handler.add(8).writePointer(d.graph);handler.add(12).writePointer(ptr(0));
  context.writeByteArray(new Uint8Array(24));
  context.add(8).writePointer(method('Od101dll.dll','?GetDC@CODInstContext@@','pointer',['pointer'])
    (Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A')));
  context.add(12).writePointer(handler);count.writeS32(0);
  const skip=Memory.alloc(64);
  method('Od101dll.dll','??0CODCompList@@QAE@PAVCODComponent@@@Z','pointer',['pointer','pointer'])(skip,wireId?ptr(wireId):ptr(0));
  let points=ptr(0);
  try{
    points=nativeRouteFunction(context,count,d.graph,d.composite,ptr(0),0,0,1,skip,0,source.x,source.y,target.x,target.y);
    const length=count.readS32();if(points.isNull()||length<2)throw new Error('Native router did not return a valid path');
    const route=Array.from({length},(_,n)=>({x:points.add(n*8).readS32(),y:points.add(n*8+4).readS32()}));
    if(!routeEndsMatch({source,target,points:route}))throw new Error('Native router returned detached endpoints');
    return route;
  }finally{
    method('Od101dll.dll','??1CODCompList@@UAE@XZ','void',['pointer'])(skip);
    if(!points.isNull()){
      const getProc=ptrFunction('kernel32.dll','GetProcAddress',['pointer','pointer'],'stdcall');
      new NativeFunction(getProc(Process.getModuleByName('mfc140u.dll').base,ptr(1513)),'void',['pointer'],'mscdecl')(points);
    }
  }
}
function rerouteNativeWire(args){
  const before=wires().wires.find(w=>w.id===args.id);if(!before)throw new Error('Wire ID does not exist');
  const beforeLabel=nativeWireLabel(before.id);
  const points=nativeRoutePoints(before.source,before.target,before.id);
  setWirePoints(ptr(before.id),points);
  const label=nativeWireLabel(before.id);
  if(beforeLabel.user_named&&JSON.stringify(beforeLabel)!==JSON.stringify(label))throw new Error('Native rerouting changed the existing net label: '+JSON.stringify({before:beforeLabel,after:label}));
  return {wire_id:before.id,points,
    length:points.slice(1).reduce((n,p,i)=>n+Math.abs(p.x-points[i].x)+Math.abs(p.y-points[i].y),0),
    wire:wires().wires.find(w=>w.id===before.id),label,routing_engine:nativeRouteInBounds(before.source,before.target)?'multisim-native':'orthogonal',preserved_wire_id:true};
}
function pointOnWire(point,wire){
  return wire.points.slice(1).some((b,n)=>{
    const a=wire.points[n];return (b.x-a.x)*(point.y-a.y)===(b.y-a.y)*(point.x-a.x)&&
      point.x>=Math.min(a.x,b.x)&&point.x<=Math.max(a.x,b.x)&&point.y>=Math.min(a.y,b.y)&&point.y<=Math.max(a.y,b.y);
  });
}
function wireNetworks(links){
  const parent=new Map();
  const root=id=>{if(!parent.has(id))parent.set(id,id);let r=id;while(parent.get(r)!==r)r=parent.get(r);return r;};
  for(const w of links)parent.set(root(w.source.id),root(w.target.id));return root;
}
function nativeJunctionOnWire(point,wire){
  const d=diagram(),tree=treeInstance(),pen=wirePen(ptr(wire.id)),junction=allocateObject('CODPinComp','??0CODPinComp@@QAE@VCPoint@@PAVCPen@@@Z',
    [point.x,point.y,pen],['int','int','pointer']);
  method('Od101dll.dll','?AddComponent@CODDiagram@@','void',['pointer','pointer','int','int','pointer','uint8'])(d.graph,junction,0,0,tree,0);
  const g=connectorGeometry(junction);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(d.graph,junction,
    Math.round(point.x-g.graphic_position.x),Math.round(point.y-g.graphic_position.y));
  if(connectorGeometry(junction).x!==point.x||connectorGeometry(junction).y!==point.y)throw new Error('Touching junction snapped away from the pin');
  nativeDrop(junction);
  const links=wires().wires.filter(w=>w.source.id===junction.toString()||w.target.id===junction.toString());
  if(links.length<2)throw new Error('Native touching junction did not split the target wire');
  links.forEach(w=>ensureWirePen(ptr(w.id),pen));
  return junction;
}
function connectTouching(args={}){
  const refs=(args.refs||components().components.map(c=>c.id)).map(ref=>component(ref).id),before=wires().wires,connections=[];
  return temporaryWiring({connect_touching:true},()=>{
    for(const ref of refs){
      for(const pin of component(ref).pins)if(!pin.connections){
        const links=wires().wires,network=wireNetworks(links);
        if(new Set(links.filter(w=>pointOnWire(pin,w)).map(w=>network(w.source.id))).size>1)
          throw new Error('Pin '+ref+'.'+pin.name+' touches a crossing of different nets; connect its intended wire explicitly');
      }
      if(args.drop!==false)nativeDrop(ptr(component(ref).id));
      for(const name of component(ref).pins.map(p=>p.name)){
        const pin=component(ref).pins.find(p=>p.name===name);
        if(pin.connections)continue;
        const links=wires().wires,network=wireNetworks(links);
        const hits=links.filter(w=>pointOnWire(pin,w));
        if(new Set(hits.map(w=>network(w.source.id))).size>1)
          throw new Error('Pin '+ref+'.'+name+' touches a crossing of different nets; connect its intended wire explicitly');
        if(!hits.length)continue;
        const hit=hits[0],endpoint=[hit.source,hit.target].find(p=>p.x===pin.x&&p.y===pin.y);
        const target=endpoint?ptr(endpoint.id):nativeJunctionOnWire(pin,hit);
        connectNative(ptr(pin.id),target,[{x:pin.x,y:pin.y},{x:pin.x,y:pin.y}]);
        connections.push({ref:component(ref).ref,component_id:ref,pin:name,kind:endpoint?'connector':'wire_branch'});
      }
    }
    const after=wires().wires,ids=new Set(after.map(w=>w.id)),old=new Set(before.map(w=>w.id));
    const added=after.filter(w=>!old.has(w.id)).map(w=>w.id),removed=before.filter(w=>!ids.has(w.id)).map(w=>w.id);
    return {backend:'multisim-native',connections,added_wire_ids:added,removed_wire_ids:removed,
      topology_changed:!!(added.length||removed.length),handles_invalidated:!!removed.length};
  });
}
function moveWithNativeWiring(args){
  const c=component(args.ref),before=matrix(ptr(c.id)),previous=wires().wires,attached=attachedWires(c,previous),options=wiringOptions();
  const outside=c.pins.some(p=>!nativeRouteInBounds(p,{x:p.x+args.dx,y:p.y+args.dy}));
  if(outside){
    const moved=movePreservingGeometry(args),touching=options.connect_touching?connectTouching({refs:[c.id],drop:false}):null;
    return {...moved,routing_engine:'preserve',touching,topology_changed:!!touching?.topology_changed};
  }
  const reroute=options.autowire_on_move&&c.pins.reduce((n,p)=>n+p.connections,0)<options.move_connection_limit;
  if(!reroute&&!options.connect_touching)return {...movePreservingGeometry(args),routing_engine:'preserve'};
  nativeDrop(ptr(c.id),args.dx,args.dy);
  if(reroute){relinkNativeComponent(ptr(c.id));for(const w of attachedWires(component(c.id),wires().wires))ensureWirePen(ptr(w.id));}
  else updateAttachedGeometry(c.id,attached);
  const touching=options.connect_touching?connectTouching({refs:[c.id],drop:false}):null;
  const after=wires().wires;
  if(attachedWires(component(c.id),after).some(w=>!routeEndsMatch(w)))throw new Error('Native movement left a wire endpoint detached');
  const signature=links=>JSON.stringify(links.map(w=>[w.id,w.source.id,w.target.id]).sort());
  const changed=signature(previous)!==signature(after);
  if(touching){touching.topology_changed=changed;touching.added_wire_ids=after.filter(w=>!previous.some(p=>p.id===w.id)).map(w=>w.id);
    touching.removed_wire_ids=previous.filter(w=>!after.some(p=>p.id===w.id)).map(w=>w.id);touching.handles_invalidated=!!touching.removed_wire_ids.length;}
  return {id:c.id,ref:c.ref,before,after:matrix(ptr(c.id)),pins:component(c.id).pins,updated_wires:attached.length,
    routing_engine:reroute?'multisim-native':'preserve',touching,topology_changed:changed};
}
function connectNative(source,target,points) {
  const s=connectorGeometry(source),t=connectorGeometry(target);
  if(!points){
    if(!wiringOptions().autowire_on_connection||!nativeRouteInBounds(s,t))points=orthogonalRoutePoints(s,t);
  }
  let vector=ptr(0);
  if(points&&points.length){const values=Memory.alloc(points.length*8);points.forEach((p,n)=>{values.add(n*8).writeS32(p.x);values.add(n*8+4).writeS32(p.y);});vector=Memory.alloc(12);vector.writePointer(values);vector.add(4).writePointer(values.add(points.length*8));vector.add(8).writePointer(values.add(points.length*8));}
  const object=method('SCH_CAP.dll','?CreateWireBase@CBackAnnotationTarget@@','pointer',['pointer','pointer','pointer','pointer'],'mscdecl')(treeInstance(),source,target,vector);
  if(object.isNull())throw new Error('Native wire creation failed');
  ensureWirePen(object);
  if(points)setWirePoints(object,points);
  const link=wires().wires.find(w=>w.id===object.toString());
  if(!points&&link.points.length>1&&(link.points[0].x!==link.source.x||link.points[0].y!==link.source.y||link.points.at(-1).x!==link.target.x||link.points.at(-1).y!==link.target.y)) {
    throw new Error('Native router returned endpoints outside the electrical connectors; no fallback route was applied');
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
function moveJunction(args) {
  if(!enumerate().objects.some(o=>o.id===args.id&&o.name==='.?AVCODPinComp@@'))throw new Error('Junction does not exist on the selected sheet');
  const object=ptr(args.id),before=connectorGeometry(object),attached=wires().wires.filter(w=>w.source.id===args.id||w.target.id===args.id);
  method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int'])(diagram().graph,object,args.x-before.x,args.y-before.y);
  const after=connectorGeometry(object);
  for(const w of attached){
    let points=w.points.length>=2?w.points.map(p=>({...p})):w.points.length===1?[{...w.points[0]},{...w.points[0]}]:[{x:w.source.x,y:w.source.y},{x:w.target.x,y:w.target.y}];
    for(const end of ['source','target'])if(w[end].id===args.id){
      if(end==='source')points=points.slice().reverse();
      const old=points.at(-1),previous=points.at(-2),next={x:after.x,y:after.y};
      const corner=previous.y===old.y?{x:next.x,y:old.y}:{x:old.x,y:next.y};
      points=[...points.slice(0,-1),corner,next].filter((p,i,a)=>!i||p.x!==a[i-1].x||p.y!==a[i-1].y);
      if(points.length===1)points.push({...points[0]});
      if(end==='source')points.reverse();
    }
    if(points.length===1)points.push({...points[0]});
    setWirePoints(ptr(w.id),points);
  }
  const current=wires().wires.filter(w=>w.source.id===args.id||w.target.id===args.id);
  if(current.length!==attached.length||current.some(w=>!routeEndsMatch(w)))throw new Error('Junction movement detached an electrical endpoint');
  return {id:args.id,before,after,updated_wires:current.length,wires:current};
}
function connectEndpoint(args) {
  const resolve=e=>{
    const ref=e.component_id||e.ref;
    if(ref){const c=component(ref),p=c.pins.find(p=>p.name===e.pin);if(!p)throw new Error('Pin '+JSON.stringify(e.pin)+' does not exist on '+c.ref+'; available pins: '+c.pins.map(p=>p.name).join(', '));return ptr(p.id);}
    if(!enumerate().objects.some(o=>o.id===e.junction_id&&/CODPinComp/.test(o.name)))throw new Error('Junction does not exist on the selected sheet: '+e.junction_id);return ptr(e.junction_id);
  };
  const source=resolve(args.source),target=resolve(args.target);
  if(source.equals(target))throw new Error('Cannot wire an endpoint to itself');
  const existing=wires().wires.find(w=>(w.source.id===source.toString()&&w.target.id===target.toString())||(w.target.id===source.toString()&&w.source.id===target.toString()));
  if(existing){
    if(args.points)routeWire({id:existing.id,points:existing.source.id===source.toString()?args.points:args.points.slice().reverse()});
    else if(!routeEndsMatch(existing))rerouteNativeWire({id:existing.id});
    return {...wires().wires.find(w=>w.id===existing.id),alreadyConnected:true};
  }
  const object=connectNative(source,target,args.points);
  if(args.points)routeWire({id:object.toString(),points:args.points});
  return {...wires().wires.find(w=>w.id===object.toString()),alreadyConnected:false,
    routing_engine:args.points?'specified':wiringOptions().autowire_on_connection&&nativeRouteInBounds(connectorGeometry(source),connectorGeometry(target))?'multisim-native':'orthogonal'};
}
function reconnectWire(args) {
  const old=wires().wires.find(w=>w.id===args.id);if(!old)throw new Error('Wire not found');
  const endpoint=end=>old[end].ref?{ref:old[end].component_id||old[end].ref,pin:old[end].pin}:{junction_id:old[end].id};
  const source=args.source||endpoint('source'),target=args.target||endpoint('target');
  // Validate named endpoint resolution before deleting the previous native wire.
  for(const e of [source,target]){const ref=e.component_id||e.ref;if(ref){if(!component(ref).pins.some(p=>p.name===e.pin))throw new Error('Replacement endpoint pin not found');}}
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
    if(width<=0||height<=0||stride*height+54>0xffffffff)throw new Error('Native BMP size exceeds its unsigned 32-bit file-size field');
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
  const digits={'1111110':'0','0110000':'1','1101101':'2','1111001':'3','0110011':'4','1011011':'5','1011111':'6','1110000':'7','1111111':'8','1111011':'9'};
  const hexDigits={...digits,'1110011':'9','1110111':'A','0011111':'B','1001110':'C','0111101':'D','1001111':'E','1000111':'F'};
  const getProperty=method('Od101dll.dll','?GetSubComponentPrp@CIITSymbolComp@@QAEKW4GRAPHICPROPERTY@@JPAVCTreeInstance@@@Z','uint',['pointer','int','int','pointer']);
  const tree=treeInstance();
  return components().components.flatMap(c=>{
    if(![1,2,4,8].includes(c.pins.length))return [];
    if(c.pins.length===2&&!c.pins.some(pin=>pin.name==='A'))return [];
    const object=ptr(c.id),info=componentLibraryInfo(ciObject(object)),model=info[1]||'';
    const visible=index=>getProperty(object,0,index,tree)===1;
    const result={ref:c.ref,model,source:'native runtime graphic properties'};
    if(/^SEVEN_SEG_COM_[AK](?:_[A-Z]+)?$/i.test(model)||/^DCD_HEX(?:_DIG)?(?:_[A-Z]+)?$/i.test(model)){
      const hex=/^DCD_HEX/i.test(model);
      const order=hex?[9,8,10,11,6,5,7]:[19,16,15,17,13,14,18];
      const segments=order.map(visible),pattern=segments.map(Number).join('');
      return [{...result,kind:hex?'hex_display':'seven_segment',segment_order:'abcdefg',segments,
        active:segments.some(Boolean),decoded:(hex?hexDigits:digits)[pattern]??null}];
    }
    if(/^LED_[A-Z]+$/i.test(model)&&info[0]==='LED'){
      const lit=visible(12)&&visible(13);
      return [{...result,kind:'led',active:lit,lit,state:lit?'on':'off'}];
    }
    if((/^LED_[A-Z]+_RATED$/i.test(model)&&info[3]==='LED_RATED')||(/^LED\d+_[A-Z]+$/i.test(model)&&info[3]==='LED')){
      const symbol=basePointer(object,'.?AVCIITAnimationSymbolComp@@');
      const layer=method('Od101dll.dll','?GetLayerForTreeInstance@CIITAnimationSymbolComp@@','int',['pointer','pointer'])(symbol,tree);
      const state=layer===1?'on':layer===0?'off':layer>1&&info[3]==='LED_RATED'?'blown':'unknown';
      const lit=state==='on';
      return [{...result,kind:'led',active:lit,lit,state,source:'native runtime animation layer'}];
    }
    if(/^PROBE_DIG(?:_[A-Z]+)?$/i.test(model)&&c.pins.length===1){
      const active=visible(6);
      return [{...result,kind:'digital_probe',active,level:c.pins[0].connections?Number(active):null}];
    }
    return [];
  });
}
function exportInteractiveImage(args) {
  const state=simulationInfo();
  if(!state.remote_initialized||![1,2].includes(state.state))throw new Error('Start interactive simulation before capturing its runtime image');
  const displays=interactiveDisplays();
  if(args.active_component){
    const selected=displays.find(d=>d.ref===args.active_component);
    if(!selected)throw new Error('active_component must identify a supported display, LED, or digital probe on this sheet');
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
        if(!interactiveStartup)return;
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
      for(let n=0;n<count;n++){
        const length=sendMessage(window,0x40c,n,ptr(0))&65535;
        if(!length)continue;
        const text=Memory.alloc((length+1)*2);sendMessage(window,0x40d,n,text);panes.push(text.readUtf16String());
      }
    }
    return 1;
  },'int',['pointer','pointer'],'stdcall');
  method('user32.dll','EnumChildWindows','int',['pointer','pointer','pointer'],'stdcall')(hwnd,callback,ptr(0));
  const time=panes.map(text=>text.match(/(?:^|:)\s*([0-9]+(?:[.,][0-9]+)?(?:e[+-]?[0-9]+)?)\s*(ns|us|µs|μs|ms|s)\s*$/i)).find(Boolean);
  const activeSim=info.remote_initialized&&[1,2].includes(info.state);
  const instReadouts=args.include_displays&&activeSim&&typeof liveInstrumentReadouts==='function'?liveInstrumentReadouts():null;
  return {...info,state_name:names[info.state]||'unknown',simulation_time_s:time?Number(time[1].replace(',','.'))*({ns:1e-9,us:1e-6,'µs':1e-6,'μs':1e-6,ms:1e-3,s:1}[time[2].toLowerCase()]):null,status_panes:panes,interactive_options:interactiveOptions(),...(args.include_displays?{display_readout_available:activeSim,display_states:activeSim?interactiveDisplays():[],...(instReadouts&&instReadouts.length?{instrument_readouts:instReadouts}:{})}:{})};
}
function interactiveCommand(args) {
  const names={start:'UnifiedSimulationPlay',resume:'UnifiedSimulationPlay',pause:'UnifiedSimulationPause',stop:'UnifiedSimulationStop'};
  if(!names[args.action])throw new Error('Choose start, pause, resume or stop');
  const handler=method('PlugInManagement.dll','?GetUserInterfaceHandler@CUserInterfaceHandler@@','pointer',[],'mscdecl')();
  const id=method('PlugInManagement.dll','?GetCommandID@CUserInterfaceHandler@@','uint16',['pointer','uint16','pointer'])(handler,25,Memory.allocUtf16String(names[args.action]));
  if(id===65535)throw new Error('Native interactive command is unavailable: '+names[args.action]);
  if(args.action==='start'){
    activateSheet();interactiveLastStart=null;
    if(Object.keys(interactiveConfiguration).length)interactiveStartup={session:simSession(),project:project().proj};
  } else if(args.action==='stop')interactiveStartup=null;
  const queued=method('user32.dll','PostMessageW','int',['pointer','uint','uint','int'],'stdcall')(hwnd,0x111,id,0);
  if(!queued)throw new Error('Native interactive command could not be queued');
  return {action:args.action,command_id:id,requested:true};
}
function resolveDcSource(netlistText,sourceRef) {
  const raw=String(sourceRef||'').trim();
  if(!raw)throw new Error('DC sweep requires dc_source');
  const escaped=raw.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const headerRe=new RegExp(`^\\*##\\s*Multisim Component\\s+${escaped}\\s*##\\*\\s*$`,'im');
  const headerMatch=headerRe.exec(netlistText);
  if(headerMatch){
    const rest=netlistText.slice(headerMatch.index+headerMatch[0].length);
    for(const line of rest.split(/\r?\n/)){
      const trimmed=line.trim();
      if(!trimmed)continue;
      if(trimmed.startsWith('*##'))break;
      if(trimmed.startsWith('*')||trimmed.startsWith('.'))continue;
      const m=trimmed.match(/^([vi]\S+)\s+/i);
      if(m)return m[1];
    }
  }
  for(const candidate of [raw,'v'+raw,'i'+raw]){
    const cardRe=new RegExp(`^(${candidate.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})\\s+`,'im');
    const m=cardRe.exec(netlistText);
    if(m&&/^[vi]/i.test(m[1]))return m[1];
  }
  return raw;
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
  if(args.saved_commands&&args.saved_commands.options_command.trim()){
    const configured=shell('saved-options',args.saved_commands.options_command);
    if(configured.result!==0||configured.errors.length)return {failed:true,stage:'saved-options',trace,...simulationInfo()};
  }
  const command=args.saved_commands?args.saved_commands.command:
    args.analysis==='op'?'op':
    args.analysis==='ac'?`ac ${args.ac_sweep} ${args.ac_points} ${args.ac_start} ${args.ac_stop}`:
    args.analysis==='dc'?`dc ${resolveDcSource(text.content,args.dc_source)} ${args.dc_start} ${args.dc_stop} ${args.dc_step}`:
    `tran ${args.step} ${args.stop}${args.use_initial_conditions?' uic':''}`;
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
    return {...c,body_bounds:symbolBodyBounds(c),labels:componentLabels({ref:c.id},c).labels,
      bounds:{left:Math.min(x1,x2),top:Math.min(y1,y2),right:Math.max(x1,x2),bottom:Math.max(y1,y2)}};
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
function spiceNetName(object,isWire=false) {
  const tree=treeInstance(),generator=method('SCH_CAP.dll','?GetNetlistGeneration@CMultisimExtension@@','pointer',['pointer'])(extension());
  const type=isWire?'PAVCSCH_CAPElectricalConnection':'PBVCiPort';
  const getName=method('SCH_CAP.dll',`?GetNetName@CNetlistGeneration@@QAE_NPAVCTreeInstance@@${type}@@_NAAV`,'uint8',['pointer','pointer','pointer','uint8','pointer','pointer']);
  const value=pathString(''),mode=Memory.alloc(1);mode.writeU8(0);
  try {
    return getName(generator,tree,object,0,value,mode)?value.readPointer().readUtf16String()||null:null;
  } finally {native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(value);}
}
function connectivityInfo(rawComponents=null,rawWires=null) {
  const allWires=rawWires||wires().wires,allComponents=rawComponents||components().components;
  const wireNetByConnector=new Map();
  const wireEntries=allWires.map(w=>{
    const n=method('SCH_CAP.dll','?GetNode@CIITLinkComp@@','pointer',['pointer'])(ptr(w.id));
    const connection=basePointer(ptr(w.id),'.?AVCSCH_CAPElectricalConnection@@');
    const name=spiceNetName(connection,true)??persistentWireLabel(w.id)?.name??(n.isNull()?null:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',n)||null);
    if(name!==null){wireNetByConnector.set(w.source.id,name);wireNetByConnector.set(w.target.id,name);}
    return {id:w.id,node:n.toString(),name,source:w.source,target:w.target};
  });
  const nets=Object.create(null);
  const compEntries=allComponents.map(c=>{
    const ci=ciObject(ptr(c.id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci);
    const byName=new Map(),byIndex=[];
    for(let idx=0;idx<count;idx++){
      const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,idx);
      const portName=returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',port);
      const node=method('CIRCEXP.dll','?GetNode@CiComponent@@','pointer',['pointer','int'])(ci,idx);
      const netName=spiceNetName(port)??(node.isNull()?null:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',node)||null);
      const item={node:node.toString(),net:netName};
      byName.set(portName,item);byIndex.push(item);
    }
    const pins=c.pins.map((p,idx)=>{
      const portEntry=byName.get(p.name)||(c.pins.length===count?byIndex[idx]:null);
      const netName=portEntry?.net??wireNetByConnector.get(p.id)??null;
      const signal=netName!==null?'V('+netName+')':null;
      if(netName!==null){
        if(!nets[netName])nets[netName]=[];
        nets[netName].push({ref:c.ref,component_id:c.id,pin:p.name});
      }
      return {name:p.name,id:p.id,node:portEntry?portEntry.node:ptr(0).toString(),net:netName,signal};
    });
    return {id:c.id,ref:c.ref,pins,nodes:pins.map(p=>p.node)};
  });
  return {wires:wireEntries,components:compEntries,nets};
}
function translateSheet(args) {
  const dx=args.dx,dy=args.dy;
  if(!Number.isInteger(dx)||!Number.isInteger(dy)||dx<-2147483648||dx>2147483647||dy<-2147483648||dy>2147483647)
    throw new Error('dx and dy must be signed 32-bit integers');
  const beforeWires=wires().wires,comps=components().components,d=diagram();
  const children=listChildren(d.composite);
  const junctions=children.filter(o=>rtti(o).name==='.?AVCODPinComp@@');
  const texts=children.filter(o=>rtti(o).name==='.?AVCODTextComp@@');
  const nodeTexts=children.filter(o=>rtti(o).name==='.?AVCODNodeTextComp@@').map(o=>({ptr:o,before:matrix(o)}));
  if(dx===0&&dy===0)return {dx:0,dy:0,moved_components:0,moved_junctions:0,moved_wires:0,moved_texts:0,content_bounds:contentBounds(),topology_changed:false};
  const moveNative=method('Od101dll.dll','?MoveComponentBy@CODDiagram@@','void',['pointer','pointer','int','int']);
  const context=Process.getModuleByName('Od101dll.dll').getExportByName('?DefIC@@3VCODInstContext@@A');
  const updateComp=method('Od101dll.dll','?Update@CODComponent@@UAEXAAVCODInstContext@@_N@Z','void',['pointer','pointer','uint8']);
  for(const c of comps)moveNative(d.graph,ptr(c.id),dx,dy);
  for(const j of junctions)moveNative(d.graph,j,dx,dy);
  for(const t of texts){moveNative(d.graph,t,dx,dy);updateComp(t,context,0);}
  for(const w of beforeWires){
    const base=w.points.length>=2?w.points:w.points.length===1?[w.points[0],w.points[0]]:[{x:w.source.x,y:w.source.y},{x:w.target.x,y:w.target.y}];
    setWirePoints(ptr(w.id),base.map(p=>({x:p.x+dx,y:p.y+dy})));
  }
  for(const nt of nodeTexts){
    const cur=matrix(nt.ptr),remX=dx-Math.round(cur[4]-nt.before[4]),remY=dy-Math.round(cur[5]-nt.before[5]);
    if(remX!==0||remY!==0){moveNative(d.graph,nt.ptr,remX,remY);updateComp(nt.ptr,context,0);}
  }
  if(wires().wires.some(w=>!routeEndsMatch(w)))repairWireGeometry();
  return {dx,dy,moved_components:comps.length,moved_junctions:junctions.length,moved_wires:beforeWires.length,moved_texts:texts.length,content_bounds:contentBounds(),topology_changed:false};
}
function fitSheet(args={}) {
  const margin=args.margin===undefined?36:args.margin,resize=args.resize===undefined?true:args.resize;
  if(!Number.isInteger(margin)||margin<0||margin>2147483647)throw new Error('margin must be a non-negative integer');
  if(typeof resize!=='boolean')throw new Error('resize must be boolean');
  const before_bounds=contentBounds();
  if(!before_bounds)return {shifted:{dx:0,dy:0},before_bounds:null,after_bounds:null,page:pageGeometry(),resized:false,topology_changed:false};
  const dx=before_bounds.left<margin?Math.ceil((margin-before_bounds.left)/9)*9:0;
  const dy=before_bounds.top<margin?Math.ceil((margin-before_bounds.top)/9)*9:0;
  if(dx>0||dy>0)translateSheet({dx,dy});
  const after_bounds=contentBounds();
  let page=pageGeometry(),resized=false;
  if(resize&&after_bounds){
    const neededW=Math.ceil((after_bounds.right+margin)/9)*9;
    const neededH=Math.ceil((after_bounds.bottom+margin)/9)*9;
    if(neededW>page.width||neededH>page.height){
      sheetSize({width:Math.max(page.width,neededW),height:Math.max(page.height,neededH)});
      page=pageGeometry();
      resized=true;
    }
  }
  return {shifted:{dx,dy},before_bounds,after_bounds,page,resized,topology_changed:false};
}
function circuitState(args={}) {
  const state=componentBounds(),page=pageGeometry(),rawWires=wires().wires;
  for(const c of state.components){
    const sym=ptr(c.id);
    if(typeof isInstrumentSymbol==='function'&&isInstrumentSymbol(sym)){
      c.is_instrument=true;
      c.instrument_manager=instrumentManagerForSymbol(sym);
      c.instrument_type=instrumentTypeForSymbol(sym);
    }
  }
  if(args.include_parameters)for(const c of state.components){
    const p=parameterInfo({ref:c.id},c);c.parameters=p.parameters;c.library={family:p.info[0],name:p.info[1],symbol_family:p.info[2],model:p.info[3]};
    if(c.is_instrument&&typeof readInstrumentProperties==='function'){
      try{c.instrument_properties=readInstrumentProperties(ptr(c.id)).raw_properties;}catch(_){}
    }
  }
  if(args.include_nets){
    const conn=connectivityInfo(state.components,rawWires);
    const wireNets=new Map(conn.wires.map(w=>[w.id,w.name]));
    const compPins=new Map(conn.components.map(c=>[c.id,new Map(c.pins.map(p=>[p.id,p]))]));
    for(const w of rawWires)w.net=wireNets.get(w.id)??null;
    for(const c of state.components){
      const pinMap=compPins.get(c.id);
      if(pinMap)for(const p of c.pins){const info=pinMap.get(p.id);p.net=info?.net??null;p.signal=info?.signal??null;}
    }
  }
  return {sheets:readSheets(),page,components:state.components,wires:rawWires,texts:textObjects(),content_bounds:contentBounds(),
    ...(args.include_persistence?persistenceSheetData(state):{})};
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
    return {...projectCircuitState(args),...(args.include_simulation_settings?{simulation_settings:documentSimulationText()}: {})};
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
    labels.push({id:child.toString(),kind:/CompValue/.test(type)?'value':'reference',text,transform:matrix(child),bounds,center:{x:(bounds.left+bounds.right)/2,y:(bounds.top+bounds.bottom)/2}});
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
function sequenceValue(value,bindings){
  if(Array.isArray(value))return value.map(v=>sequenceValue(v,bindings));
  if(!value||typeof value!=='object')return value;
  if(Object.keys(value).length===1&&'$ref' in value){
    const path=value.$ref;if(typeof path!=='string'||!path)throw new Error('Invalid result reference');
    let result=bindings;
    for(const key of path.split('.')){
      if(['__proto__','prototype','constructor'].includes(key)||!Object.prototype.hasOwnProperty.call(result||{},key))throw new Error('Unresolved result reference: '+path);
      result=result[key];
    }
    return result;
  }
  for(const key of ['$add','$sub'])if(Object.keys(value).length===1&&key in value){
    const terms=sequenceValue(value[key],bindings);
    if(!Array.isArray(terms)||terms.length!==2||terms.some(v=>typeof v!=='number'||!Number.isFinite(v)))throw new Error(key+' requires two finite numbers');
    return key==='$add'?terms[0]+terms[1]:terms[0]-terms[1];
  }
  return Object.fromEntries(Object.entries(value).map(([k,v])=>{
    if(['__proto__','prototype','constructor'].includes(k))throw new Error('Invalid argument key');
    return [k,sequenceValue(v,bindings)];
  }));
}
function validatePlacement(a){
  if('angle' in a&&(typeof a.angle!=='number'||!Number.isFinite(a.angle)))throw new Error('Rotation must be finite');
  if('mirror_axis' in a&&!['horizontal','vertical'].includes(a.mirror_axis))throw new Error('Invalid mirror axis');
  if('value' in a&&'expression' in a)throw new Error('Provide value or expression, not both');
  if('expression' in a&&(typeof a.expression!=='string'||!a.expression.trim()||a.expression.includes('\0')))throw new Error('Invalid expression');
  if('value' in a&&!(typeof a.value==='string'&&a.value.trim()&&!a.value.includes('\0'))&&!(typeof a.value==='number'&&Number.isFinite(a.value)))throw new Error('Invalid placement value');
  if('params' in a&&a.params!==undefined&&a.params!==null){
    if(typeof a.params!=='object'||Array.isArray(a.params))throw new Error('Invalid params');
    for(const [k,v] of Object.entries(a.params)){
      if(!k||k.includes('\0'))throw new Error('Invalid parameter name');
      if(!(typeof v==='string'&&v.trim()&&!v.includes('\0'))&&!(typeof v==='number'&&Number.isFinite(v)))throw new Error('Invalid parameter value for '+k);
    }
  }
}
function validateSequenceOperation(op,a){
  if(op==='remove'){for(const [alias,key] of [['object_id','id'],['component_ref','ref']])if(alias in a){if(key in a&&a[key]!==a[alias])throw new Error('Conflicting '+alias+' and '+key);a[key]=a[alias];delete a[alias];}}
  const required={place:['name','x','y'],placeInstrument:['dll','manager','res_id','flags','x','y'],setInstrumentSettings:['ref','writes'],move:['ref','dx','dy'],alignPin:['ref','pin','x','y'],moveLabel:['ref','x','y'],transform:['ref'],
    wire:['source','target'],connectEndpoint:['source','target'],route:['id','points'],autoWire:['id'],
    setParameter:['ref'],addText:['text','x','y'],updateText:['id'],deleteText:['id'],updateSheet:[],updatePort:['id'],moveJunction:['id','x','y'],labelWire:['id','name'],splitWire:['id','x','y'],
    rename:['ref','new_ref'],remove:[],connectTouching:[],sheetSize:['width','height'],sheetTitle:['title'],repairWireGeometry:[],fitSheet:[],translateSheet:['dx','dy']};
  if(!(op in required))throw new Error('Operation requires an individual native transaction: '+op);
  for(const k of required[op])if(!(k in a))throw new Error(op+' requires '+k);
  for(const k of ['ref','id','name','text','family','group','manufacturer','title','page','new_ref','expression','pin','role','dll','manager','create_kind','instrument'])
    if(k in a&&a[k]!==undefined&&(typeof a[k]!=='string'||a[k].includes('\0')))throw new Error('Invalid '+k);
  for(const k of ['ref','id','new_ref','name','pin','role','dll','manager'])
    if(k in a&&a[k]!==undefined&&!a[k])throw new Error('Invalid '+k);
  if(op==='labelWire'&&!a.name.trim())throw new Error('Invalid name');
  for(const k of ['x','y','dx','dy','index','width','height','margin','res_id','flags'])if(k in a&&a[k]!==undefined&&(!Number.isInteger(a[k])||a[k]<-2147483648||a[k]>2147483647))throw new Error('Invalid '+k);
  if((op==='place'||op==='placeInstrument')&&!['origin','center','pin'].includes(a.anchor||'origin'))throw new Error('Invalid placement anchor');
  if(op==='place')validatePlacement(a);
  if(op==='placeInstrument'){
    if('angle' in a&&(typeof a.angle!=='number'||!Number.isFinite(a.angle)))throw new Error('Rotation must be finite');
    if('mirror_axis' in a&&!['horizontal','vertical'].includes(a.mirror_axis))throw new Error('Invalid mirror axis');
    if('writes' in a&&a.writes!==undefined&&!Array.isArray(a.writes))throw new Error('Invalid instrument writes');
  }
  if(op==='setInstrumentSettings'&&(!Array.isArray(a.writes)||!a.writes.length))throw new Error('setInstrumentSettings requires nonempty writes');
  if(op==='transform'&&((('angle' in a)===('axis' in a))||('angle' in a&&(typeof a.angle!=='number'||!Number.isFinite(a.angle)))||('axis' in a&&!['horizontal','vertical'].includes(a.axis))))throw new Error('Invalid transform');
  if(op==='remove'&&!a.ref&&!a.id)throw new Error('remove requires ref or id');
  if(op==='updateText'&&!['text','x','y'].some(k=>k in a))throw new Error('updateText requires text, x or y');
  if(op==='updatePort'&&!['name','x','y'].some(k=>k in a))throw new Error('updatePort requires name, x or y');
  if(op==='updateSheet'&&!['title','page','width','height'].some(k=>k in a))throw new Error('updateSheet requires title, page, width or height');
  if(op==='updateSheet'&&['width','height'].some(k=>k in a&&(a[k]<=0||Math.round(a[k]/96*25.4*500000)>2147483647)))throw new Error('Sheet dimensions exceed the native signed 32-bit CUTRect work-area format');
  if(op==='setParameter'){
    const hasVal='value' in a&&a.value!==undefined,hasExpr='expression' in a&&a.expression!==undefined;
    if(hasVal===hasExpr)throw new Error('Invalid parameter value or index');
    if('index' in a&&a.index!==undefined&&(a.index<0||a.index>2147483647))throw new Error('Invalid parameter value or index');
    if(hasVal&&(typeof a.value!=='number'||!Number.isFinite(a.value)))throw new Error('Invalid parameter value or index');
    if(hasExpr&&!a.expression.trim())throw new Error('Invalid parameter value or index');
  }
  if(op==='fitSheet'&&((('margin' in a)&&a.margin!==undefined&&a.margin<0)||(('resize' in a)&&a.resize!==undefined&&typeof a.resize!=='boolean')))throw new Error('Invalid fitSheet arguments');
  if(op==='sheetSize'&&['width','height'].some(k=>a[k]<=0||a[k]>2147483647))throw new Error('Sheet dimensions must be positive signed 32-bit integers');
  if('points' in a&&(!Array.isArray(a.points)||a.points.length<2||a.points.some(p=>!p||['x','y'].some(k=>!Number.isInteger(p[k])||p[k]<-2147483648||p[k]>2147483647))))throw new Error('Invalid wire route');
  if('parameters' in a){if(!Array.isArray(a.parameters))throw new Error('Invalid parameters');a.parameters.forEach(p=>{if(!p||typeof p!=='object')throw new Error('Invalid parameters');validateSequenceOperation('setParameter',{ref:'placement',...p});});}
  for(const k of ['source','target'])if(k in a){const e=a[k];if(!e||!((typeof e.junction_id==='string'&&e.junction_id)||(((typeof e.ref==='string'&&e.ref)||(typeof e.component_id==='string'&&e.component_id))&&typeof e.pin==='string'&&e.pin)))throw new Error('Invalid '+k+' endpoint');}
  if('refs' in a&&(!Array.isArray(a.refs)||a.refs.length<1||a.refs.some(r=>typeof r!=='string'||!r)))throw new Error('Invalid component refs');
}
const cancelledEditSequences=new Set();
const terminatedEditSequences=new Set();
let activeEditSequence=null;
function receiveEditCancellation(){
  recv('cancel-edit-sequence',message=>{
    if(message&&typeof message.token==='string'&&message.token&&!terminatedEditSequences.has(message.token)){
      cancelledEditSequences.add(message.token);
      while(cancelledEditSequences.size>64)cancelledEditSequences.delete(cancelledEditSequences.values().next().value);
    }
    receiveEditCancellation();
  });
}
receiveEditCancellation();
function editSequence(args){
  if(!Array.isArray(args.operations)||args.operations.length<1||args.operations.length>8)throw new Error('Native edit slices support 1 to 8 operations');
  const bindings={...(args.bindings||{})},results=[];
  activeEditSequence=args.cancel_token||null;
  let failed=false;
  try{
  for(let index=0;index<args.operations.length;index++){
    const op=args.operations[index];
    try{
      if(args.cancel_token&&cancelledEditSequences.has(args.cancel_token))throw new Error('Workflow cancelled between native edit operations');
      if(args.cancel_token)send({edit_operation_started:{token:args.cancel_token,index,operation:op.operation}});
      const a=sequenceValue(op.arguments||{},bindings);validateSequenceOperation(op.operation,a);
      let result;
      if(op.operation==='alignPin'){
        const c=component(a.ref),pin=c.pins.find(p=>p.name===a.pin);
        if(!pin)throw new Error('Alignment pin not found: '+a.pin);
        result=move({ref:c.id,dx:a.x-pin.x,dy:a.y-pin.y});
      }else result=op.operation==='move'?move(a):op.operation==='wire'?wire(a):editorHandlers[op.operation](a);
      results.push(result);if(op.bind)bindings[op.bind]=result;
    }catch(error){failed=true;return {failed:true,failed_operation_index:index,error:String(error),results,bindings};}
  }
  return {failed:false,results,bindings};
  }finally{
    if(args.cancel_token){
      if(failed||cancelledEditSequences.has(args.cancel_token)){
        terminatedEditSequences.add(args.cancel_token);
        while(terminatedEditSequences.size>64)terminatedEditSequences.delete(terminatedEditSequences.values().next().value);
      }
      cancelledEditSequences.delete(args.cancel_token);
    }
    activeEditSequence=null;
  }
}
const editorHandlers={
  editSequence,
  signalForPin:args=>{
    const c=component(args.ref),ci=ciObject(ptr(c.id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci);
    for(let n=0;n<count;n++){
      const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,n);
      if(returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',port)!==args.pin)continue;
      const node=method('CIRCEXP.dll','?GetNode@CiComponent@@','pointer',['pointer','int'])(ci,n);
      let netName=spiceNetName(port)??(node.isNull()?null:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',node)||null);
      if(netName===null){
        const pinObj=c.pins.find(p=>p.name===args.pin);
        if(pinObj){
          const attached=wires().wires.find(w=>w.source.id===pinObj.id||w.target.id===pinObj.id);
          if(attached)netName=persistentWireLabel(attached.id)?.name??null;
        }
      }
      if(netName===null)throw new Error('Pin has no electrical node: '+c.ref+'.'+args.pin);
      return {ref:c.ref,component_id:c.id,pin:args.pin,net:netName,signal:'V('+netName+')'};
    }
    throw new Error('Electrical pin not found: '+c.ref+'.'+args.pin);
  },
  wiringOptions,connectTouching,autoWire:rerouteNativeWire,fitSheet,translateSheet,
  openedSheetComponents,componentBounds,synchronizeGraphics,circuitState,projectCircuitState,verifySavedCopy,componentLabels,moveLabel:moveComponentLabel,
  simulationCommand:args=>({result:method('SpiceifsSch.dll','?ExecuteShellCmd@CSchSpiceSession@SpiceifsSch@@','int',['pointer','pointer'])(simSession(),Memory.allocUtf16String(args.command)),...simulationInfo()}),
  cleanupNumericSession:()=>{
    const info=simulationInfo();
    if([1,2].includes(info.state))throw new Error('Stop interactive simulation before cleaning the numeric session');
    if(info.remote_initialized)method('SpiceifsSch.dll','?SessionEndCleanup@CSchSpiceSession@SpiceifsSch@@','void',['pointer'])(simSession());
    return simulationInfo();
  },
  parameters:parameterInfo,setParameter,rename:renameComponent,copy:copyComponent,remove:removeObject,transform:transformComponent,route:routeWire,repairWireGeometry,sheets:readSheets,
  electricalPorts:args=>{
    const ci=ciObject(ptr(component(args.ref).id)),count=method('CIRCEXP.dll','?GetPortCount@CiComponent@@','int',['pointer'])(ci),ports=[];
    for(let n=0;n<count;n++){const port=method('CIRCEXP.dll','?GetPort@CiComponent@@QBEPAVCiPort@@H@Z','pointer',['pointer','int'])(ci,n);ports.push({id:port.toString(),name:returnedString('CIRCEXP.dll','?GetLocalName@CiElement@@',port)});}
    return {ref:args.ref,ports};
  },
  setProjectPath:args=>setProjectPath(args.path),snapshot,restoreSnapshot,librarySearch,place:placeComponent,addText,textObjects,updateText,deleteText,updateSheet,updatePort,moveJunction,labelWire,modelInfo,setModelText,createSubcircuit,createPort,sheetTitle,sheetSize,splitWire,connectEndpoint,reconnect:reconnectWire,replace:replaceComponent,exportImage,exportInteractiveImage,interactiveOptions,interactiveStatus,interactiveCommand,netlist,menus,selectSheet,projects,selectProject,createSheet,newProject,simulationInfo,simulate,simulationExport,
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
  connectivity:()=>connectivityInfo(),
  editorInfo:()=>({handler:method('SCH_CAP.dll','?GetComponentHandler@@','pointer',[],'mscdecl')().toString(),extension:extension().toString(),objects:components().components.map(c=>({id:c.id,ref:c.ref,local_ref:c.local_ref,ci:ciObject(ptr(c.id)).toString()}))})};
// Simulator transport sends control requests independently of a busy UI-thread analysis.
rpc.exports.control=action=>{
  if(!['pause','resume','stop'].includes(action))throw new Error('Unknown simulator control');
  const transport=simSession().add(0x18).readPointer();if(transport.isNull())throw new Error('Simulator is not prepared');
  const result=action==='stop'?method('spiceifs.dll','?StopSimulation@CXSpiceSimInterface@xspiceif@@','int',['pointer'])(transport):method('spiceifs.dll','?SimPause@CXSpiceSimInterface@xspiceif@@','int',['pointer','int','uint8','uint8'])(transport,1,0,action==='pause'?1:0);
  return {action,native_result:result,requested:true};
};
