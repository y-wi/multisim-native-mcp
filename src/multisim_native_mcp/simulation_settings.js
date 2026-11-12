// Document-owned interactive settings. All parsing, property replacement and
// serialization use Multisim's native property classes; .ms14 bytes are untouched.
function simulationPropertyList(text) {
  const list=Memory.alloc(64),s=pathString(text+'\n');
  try{method('SHARUTIL.dll','??0CPropertyList@@QAE@ABV?$CStringT@','pointer',['pointer','pointer'])(list,s);}
  finally{native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(s);}
  return list;
}
function destroySimulationPropertyList(list){method('SHARUTIL.dll','??1CPropertyList@@','void',['pointer'])(list);}
function simulationPropertyValue(item){return method('SHARUTIL.dll','?GetValue@CPropertyItem@@','pointer',['pointer'])(item).readPointer().readUtf16String();}
function simulationPropertyLabel(item){return method('SHARUTIL.dll','?GetLabel@CPropertyItem@@','pointer',['pointer'])(item).readPointer().readUtf16String();}
function visitSimulationProperties(list,callback) {
  const count=method('SHARUTIL.dll','?GetCount@CPropertyList@@','int',['pointer'])(list);
  if(count<0)throw new Error('Unsupported native simulation property count');
  for(let i=0;i<count;i++) {
    const item=Memory.alloc(128);method('SHARUTIL.dll','??0CPropertyItem@@QAE@XZ','pointer',['pointer'])(item);
    try {
      if(!method('SHARUTIL.dll','?GetNth@CPropertyList@@','int',['pointer','int','pointer'])(list,i,item))throw new Error('Cannot read native simulation property');
      callback(item,simulationPropertyLabel(item),i);
    } finally{method('SHARUTIL.dll','??1CPropertyItem@@','void',['pointer'])(item);}
  }
}
function readSimulationFields(text,path) {
  const list=simulationPropertyList(text);let result=null,matches=0;
  try {
    if(!path.length){result={};visitSimulationProperties(list,(item,name)=>{if(Object.prototype.hasOwnProperty.call(result,name))throw new Error('Duplicate native simulation property: '+name);result[name]=simulationPropertyValue(item);});}
    else visitSimulationProperties(list,(item,name)=>{if(name===path[0]){matches++;result=readSimulationFields(simulationPropertyValue(item),path.slice(1));}});
    if(path.length&&matches!==1)throw new Error('Expected one native simulation property: '+path.join('.'));
    return result;
  }finally{destroySimulationPropertyList(list);}
}
function patchSimulationProperties(text,path,changes) {
  const list=simulationPropertyList(text),result=Memory.alloc(64);let matches=0;
  method('SHARUTIL.dll','??0CPropertyList@@QAE@XZ','pointer',['pointer'])(result);
  try {
    visitSimulationProperties(list,(item,name)=>{
      if(path.length&&name===path[0]) {
        matches++;
        const changed=patchSimulationProperties(simulationPropertyValue(item),path.slice(1),changes),nested=simulationPropertyList(changed),replacement=Memory.alloc(128),label=pathString(name);
        try {
          method('SHARUTIL.dll','??0CPropertyItem@@QAE@ABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@ABVCPropertyList@@@Z','pointer',['pointer','pointer','pointer'])(replacement,label,nested);
          try{method('SHARUTIL.dll','?AddItem@CPropertyList@@QAEXABV','void',['pointer','pointer'])(result,replacement);}
          finally{method('SHARUTIL.dll','??1CPropertyItem@@','void',['pointer'])(replacement);}
        }finally{native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(label);destroySimulationPropertyList(nested);}
      } else if(!path.length&&Object.prototype.hasOwnProperty.call(changes,name)) {
        matches++;const replacement=simulationPropertyList(name+':'+changes[name]);
        try{method('SHARUTIL.dll','?AppendItems@CPropertyList@@','void',['pointer','pointer'])(result,replacement);}
        finally{destroySimulationPropertyList(replacement);}
      } else method('SHARUTIL.dll','?AddItem@CPropertyList@@QAEXABV','void',['pointer','pointer'])(result,item);
    });
    if(matches!==(path.length?1:Object.keys(changes).length))throw new Error('Expected uniquely matched native simulation property: '+path.join('.'));
    return instanceString('SHARUTIL.dll','?GetList@CPropertyList@@',result);
  }finally{destroySimulationPropertyList(list);destroySimulationPropertyList(result);}
}
function documentSimulationText(value) {
  const frontend=method('SHARUTIL.dll','?GetGuiFEObject@CGuiFEObj@@','pointer',[],'mscdecl')(),variant=Memory.alloc(128);
  if(value===undefined)method('SHARUTIL.dll','??0IITVariant@@QAE@XZ','pointer',['pointer'])(variant);
  else method('SHARUTIL.dll','??0IITVariant@@QAE@PB_W@Z','pointer',['pointer','pointer'])(variant,Memory.allocUtf16String(value));
  try {
    // 10099 is the native document's simulation-information property, used by
    // InstrumentAgency to load SIMULATION_INFO before ordinary GUI starts.
    const status=value===undefined?
      method('SHARUTIL.dll','?GetProperty@CGuiFEObj@@','int',['pointer','int','pointer','pointer','pointer'])(frontend,10099,variant,ptr(0),treeInstance()):
      method('SHARUTIL.dll','?SetProperty@CGuiFEObj@@','int',['pointer','int','pointer','pointer','pointer','uint8'])(frontend,10099,variant,ptr(0),treeInstance(),1);
    if(status!==0)throw new Error('Native document simulation property failed: '+status);
    if(value!==undefined)return;
    const string=method('SHARUTIL.dll','?GetCString@IITVariant@@QAEP','pointer',['pointer'])(variant);
    if(string.isNull())throw new Error('Unsupported native document simulation property type');
    return string.readPointer().readUtf16String();
  }finally{method('SHARUTIL.dll','??1IITVariant@@','void',['pointer'])(variant);}
}
const interactivePropertyPath=['SIMULATION_INFO','DEFAULT_INST_SETTINGS','TRAN'];
function documentInteractiveOptions(args={}) {
  const before=documentSimulationText(),changes=args.configuration||{};
  let text=before;
  // An untouched new schematic may not yet have serialized simulation data.
  if(!text.trim())text='SIMULATION_INFO:list{DEFAULT_INST_SETTINGS:list{TRAN:list{ANALYSIS:list{TSTEP:string{calculate}\nTSTOP:double{1e30}\nTSTART:double{0}\nTMAX:string{calculate}\nIC:string{auto_ic}\n}\nTHROTTLE_SPEED:long{1}\n}\n}\n}\n';
  if(Object.keys(changes).length||args.reset) {
    const fields={};
    if(args.reset){fields.TSTEP='string{calculate}';fields.TMAX='string{calculate}';}
    else {
      if(changes.time_step!==undefined)fields.TSTEP='double{'+changes.time_step+'}';
      if(changes.max_time_step!==undefined)fields.TMAX='double{'+changes.max_time_step+'}';
    }
    if(Object.keys(fields).length)text=patchSimulationProperties(text,[...interactivePropertyPath,'ANALYSIS'],fields);
    if(changes.real_time!==undefined||args.reset)text=patchSimulationProperties(text,interactivePropertyPath,{THROTTLE_SPEED:'long{'+(args.reset||changes.real_time?1:0)+'}'});
    documentSimulationText(text);
    // Re-read the document property, rather than trusting the native setter.
    text=documentSimulationText();
  }
  const transient=readSimulationFields(text,[...interactivePropertyPath,'ANALYSIS']),common=readSimulationFields(text,interactivePropertyPath);
  function step(key){const value=transient[key];if(value==='calculate')return null;const number=Number(value);if(!value||!Number.isFinite(number)||number<=0)throw new Error('Unsupported native interactive '+key);return number;}
  if(!['0','1'].includes(common.THROTTLE_SPEED))throw new Error('Unsupported native real-time pacing setting');
  return {scope:'circuit',persisted_in_circuit:true,applies_to:'native interactive simulation, including ordinary GUI starts after saving',
    configuration:{time_step:step('TSTEP'),max_time_step:step('TMAX'),real_time:common.THROTTLE_SPEED==='1'},
    automatic:{time_step:transient.TSTEP==='calculate',max_time_step:transient.TMAX==='calculate'},
    changed:text!==before&&(Object.keys(changes).length>0||!!args.reset)};
}
editorHandlers.documentInteractiveOptions=documentInteractiveOptions;
editorHandlers.simulationSettingsText=()=>documentSimulationText();

function simulationPropertyType(item){return method('SHARUTIL.dll','?GetType@CPropertyItem@@','pointer',['pointer'])(item).readPointer().readUtf16String();}
function simulationEntries(text) {
  const list=simulationPropertyList(text),entries=[];
  try {visitSimulationProperties(list,(item,label,index)=>entries.push({label,index,type:simulationPropertyType(item),raw:simulationPropertyValue(item)}));return entries;}
  finally{destroySimulationPropertyList(list);}
}
function simulationValue(entry) {
  if(entry.type==='double'||entry.type==='long')return Number(entry.raw);
  if(entry.type==='flag')return null;
  return entry.raw;
}
function simulationField(text,path) {
  if(!path.length)throw new Error('A native field path is required');
  const entries=simulationEntries(text),token=path[0],matches=entries.filter(e=>typeof token==='number'?e.index===token:e.label===token);
  if(matches.length!==1)throw new Error('Native field must match exactly once: '+JSON.stringify(path));
  const entry=matches[0];
  if(path.length===1)return entry;
  if(entry.type!=='list')throw new Error('Native field parent is not a list');
  return simulationField(entry.raw,path.slice(1));
}
function simulationCatalog(text,path=[],depth=0) {
  const entries=simulationEntries(text),counts={};
  for(const e of entries)counts[e.label]=(counts[e.label]||0)+1;
  return entries.flatMap(e=>{
    const p=[...path,counts[e.label]>1?e.index:e.label];
    if(e.type==='list')return simulationCatalog(e.raw,p,depth+1);
    return [{path:p,label:e.label,native_type:e.type,value:simulationValue(e),writable:['string','long','double'].includes(e.type)}];
  });
}
function nativeSimulationScalar(label,type,value) {
  const item=Memory.alloc(128),name=pathString(label);let string=null;
  try {
    const prefix='??0CPropertyItem@@QAE@ABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@';
    if(type==='string'){
      string=pathString(value);method('SHARUTIL.dll',prefix+'0@Z','pointer',['pointer','pointer','pointer'])(item,name,string);
    }else if(type==='double')method('SHARUTIL.dll',prefix+'N@Z','pointer',['pointer','pointer','double'])(item,name,value);
    else if(type==='long')method('SHARUTIL.dll',prefix+'J@Z','pointer',['pointer','pointer','int'])(item,name,value);
    else throw new Error('Unsupported writable native type: '+type);
    return item;
  }finally{native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);if(string)native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(string);}
}
function patchNativeSimulationField(text,path,type,value) {
  const list=simulationPropertyList(text),result=Memory.alloc(64),target=simulationField(text,[path[0]]);
  method('SHARUTIL.dll','??0CPropertyList@@QAE@XZ','pointer',['pointer'])(result);
  try {
    visitSimulationProperties(list,(item,label,index)=>{
      if(index!==target.index){method('SHARUTIL.dll','?AddItem@CPropertyList@@QAEXABV','void',['pointer','pointer'])(result,item);return;}
      let replacement;
      if(path.length>1){
        if(target.type!=='list')throw new Error('Native field parent is not a list');
        const nested=simulationPropertyList(patchNativeSimulationField(target.raw,path.slice(1),type,value)),name=pathString(label);
        replacement=Memory.alloc(128);
        try{method('SHARUTIL.dll','??0CPropertyItem@@QAE@ABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@ABVCPropertyList@@@Z','pointer',['pointer','pointer','pointer'])(replacement,name,nested);}
        finally{native('Library.dll','??1CPathString@@QAE@XZ','void',['pointer'])(name);destroySimulationPropertyList(nested);}
      }else replacement=nativeSimulationScalar(label,type,value);
      try{method('SHARUTIL.dll','?AddItem@CPropertyList@@QAEXABV','void',['pointer','pointer'])(result,replacement);}
      finally{method('SHARUTIL.dll','??1CPropertyItem@@','void',['pointer'])(replacement);}
    });
    return instanceString('SHARUTIL.dll','?GetList@CPropertyList@@',result);
  }finally{destroySimulationPropertyList(list);destroySimulationPropertyList(result);}
}
function simulationSelection(text,scope,analysis) {
  if(!['interactive','analysis'].includes(scope))throw new Error('Choose interactive or analysis scope');
  const group=['SIMULATION_INFO',scope==='interactive'?'DEFAULT_INST_SETTINGS':'ANALYSES'];
  const available=simulationEntries(simulationField(text,group).raw).filter(e=>e.type==='list'&&e.label!=='ANALYSIS_LIST').map(e=>e.label);
  if(!available.includes(analysis))throw new Error('Unknown native analysis '+analysis+'; available: '+available.join(', '));
  const path=[...group,analysis];return {path,available,raw:simulationField(text,path).raw};
}
function validateNativeSimulationValue(field,value) {
  let type=field.type;
  if(['TSTEP','TMAX'].includes(field.label)){
    if(value===null||value==='calculate')return {type:'string',value:'calculate'};
    type='double';
  }
  if(type==='double'){
    if(typeof value!=='number'||!Number.isFinite(value))throw new Error(field.label+' requires a finite number');
  }else if(type==='long'){
    if(typeof value==='boolean')value=Number(value);
    if(!Number.isInteger(value)||value < -2147483648||value>2147483647)throw new Error(field.label+' requires a signed 32-bit integer');
  }else if(type==='string'){
    if(typeof value!=='string'||value.includes('\0'))throw new Error(field.label+' requires a native string');
  }else throw new Error('Change scalar fields only; solver flags use solver_options');
  const key=field.label.toLowerCase();
  if(['tstep','tmax','tstop','reltol','abstol','vntol','chgtol','trtol','gmin','pivtol','pivrel','rshunt','defl','defw','npoints_per_variation'].includes(key)&&!(value>0))throw new Error(field.label+' must be positive');
  if(['tstart','minbreak','ramptime','defad','defas','itl1','itl2','itl4','itl6','gminsteps','maxevtiter','maxopalter'].includes(key)&&value<0)throw new Error(field.label+' cannot be negative');
  if(['temp','tnom'].includes(key)&&value<=-273.15)throw new Error(field.label+' must exceed absolute zero in Celsius');
  if(key==='method'&&!['trapezoidal','gear'].includes(value))throw new Error('method must be trapezoidal or gear');
  if(key==='variation'&&!['lin','dec','oct'].includes(value))throw new Error('VARIATION must be lin, dec or oct');
  if(key==='ic'&&!['auto_ic','uic','zero_ic'].includes(value))throw new Error('IC must be auto_ic, uic or zero_ic');
  if(key==='maxord'&&(!Number.isInteger(value)||value<1||value>6))throw new Error('maxord must be 1 to 6');
  if(['IsEnabled','USE_ASYS_OPT','MSM_ASYS_OPT','THROTTLE_SPEED'].includes(field.label)&&![0,1].includes(value))throw new Error(field.label+' must be 0 or 1');
  return {type,value};
}
function validateSimulationSection(raw) {
  const values=Object.fromEntries(simulationEntries(raw).map(e=>[e.label,e.raw])),analysis=values.ANALYSIS?Object.fromEntries(simulationEntries(values.ANALYSIS).map(e=>[e.label,e.raw])):{};
  if(analysis.TSTOP!==undefined&&Number(analysis.TSTART)>=Number(analysis.TSTOP))throw new Error('TSTART must be less than TSTOP');
  if(analysis.FSTART!==undefined&&!(Number(analysis.FSTART)>0&&Number(analysis.FSTART)<Number(analysis.FSTOP)))throw new Error('Require 0 < FSTART < FSTOP');
  if(Number(values.DIGITAL_THRESHOLD_L)>Number(values.DIGITAL_THRESHOLD_H))throw new Error('Low digital threshold cannot exceed high threshold');
}
function documentSimulationSettings(args={}) {
  const before=documentSimulationText(),scope=args.scope||'interactive',analysis=args.analysis_type||'TRAN';
  if(args.expected_text!==undefined&&before!==args.expected_text)throw new Error('Simulation settings changed before the native transaction');
  let text=before;const selection=simulationSelection(text,scope,analysis),patches=[...(args.changes||[])];
  const options=simulationEntries(simulationField(selection.raw,['ASYS_OPT']).raw).map(e=>{
    const children=simulationEntries(e.raw),value=children.find(c=>c.label!=='IsEnabled');
    if(!value)throw new Error('Malformed native solver option');
    return {name:value.label,path:['ASYS_OPT',e.label],native_type:value.type,value:simulationValue(value),enabled:children.find(c=>c.label==='IsEnabled').raw==='1'};
  });
  for(const [name,value] of Object.entries(args.solver_options||{})){
    const option=options.find(o=>o.name===name);if(!option)throw new Error('Unknown native solver option: '+name);
    patches.push({path:[...option.path,'IsEnabled'],value:value===null||value===false?0:1});
    if(value!==null&&value!==false&&option.native_type!=='flag')patches.push({path:[...option.path,name],value});
    else if(value!==null&&option.native_type==='flag'&&typeof value!=='boolean')throw new Error(name+' is a boolean solver flag');
  }
  // MSM_ASYS_OPT=1 selects Multisim defaults and otherwise masks stored custom
  // values. Native customized solver settings require USE=1 and MSM=0.
  if(Object.keys(args.solver_options||{}).length||patches.some(p=>p.path[0]==='ASYS_OPT')){
    for(const [key,value] of Object.entries({USE_ASYS_OPT:1,MSM_ASYS_OPT:0})){
      const explicit=patches.find(p=>p.path.length===1&&p.path[0]===key);
      if(explicit&&Number(explicit.value)!==value)throw new Error('Custom solver options require '+key+'='+value);
      if(!explicit)patches.push({path:[key],value});
    }
  }
  const expected=[];const seen=new Set();
  for(const patch of patches){
    const path=[...selection.path,...patch.path],field=simulationField(text,path),key=JSON.stringify(path);
    if(seen.has(key))throw new Error('Duplicate simulation setting change: '+key);seen.add(key);
    const replacement=validateNativeSimulationValue(field,patch.value);
    text=patchNativeSimulationField(text,path,replacement.type,replacement.value);expected.push({path,...replacement});
  }
  validateSimulationSection(simulationField(text,selection.path).raw);
  if(patches.length){documentSimulationText(text);text=documentSimulationText();}
  for(const change of expected){const actual=simulationField(text,change.path);if(actual.type!==change.type||simulationValue(actual)!==change.value)throw new Error('Native simulation setting readback failed: '+JSON.stringify(change.path));}
  const after=simulationSelection(text,scope,analysis),fields=simulationCatalog(after.raw).filter(f=>f.path[0]!=='ASYS_OPT');
  const solver=simulationEntries(simulationField(after.raw,['ASYS_OPT']).raw).map(e=>{
    const children=simulationEntries(e.raw),value=children.find(c=>c.label!=='IsEnabled');
    return {name:value.label,native_type:value.type,value:simulationValue(value),enabled:children.find(c=>c.label==='IsEnabled').raw==='1'};
  });
  return {scope:'circuit',simulation_scope:scope,analysis_type:analysis,available_analyses:selection.available,fields,solver_options:solver,changed:text!==before&&patches.length>0,applied_changes:expected.map(c=>({path:c.path.slice(selection.path.length),native_type:c.type,value:c.value})),_simulation_text:text};
}
function documentAnalysisCommands(args={}) {
  const scope=args.scope||'analysis',analysis=args.analysis_type||'TRAN',getters={OP:'Op',AC:'Ac',TRAN:'Tran'};
  if(!getters[analysis])throw new Error('Numeric execution supports OP, AC and TRAN; other configurations are available to native Multisim');
  const text=args.text===undefined?documentSimulationText():args.text,selection=simulationSelection(text,scope,analysis);
  const list=simulationPropertyList(analysis+':list{'+selection.raw+'}\n'),item=Memory.alloc(128),object=Memory.alloc(65536);
  method('SHARUTIL.dll','??0CPropertyItem@@QAE@XZ','pointer',['pointer'])(item);
  method('asys.dll','??0Analyses@@QAE@XZ','pointer',['pointer'])(object);
  try{
    method('SHARUTIL.dll','?GetNth@CPropertyList@@','int',['pointer','int','pointer'])(list,0,item);
    const selected=method('asys.dll','?Get'+getters[analysis]+'@Analyses@@','pointer',['pointer'])(object);
    const status=method('asys.dll','?fromPropertyItem@Analysis@Analyses@@','int',['pointer','pointer','int'])(selected,item,0);
    if(status!==1)throw new Error('Native analysis settings parser failed: '+status);
    const options=instanceString('asys.dll','?toNutmegCommand@Analysis@Analyses@@',selected,[32],['int']);
    const generated=instanceString('asys.dll','?toNutmegCommand@Analysis@Analyses@@',selected,[1],['int']);
    const command=generated.split(';').map(c=>c.trim()).find(c=>new RegExp('^'+analysis.toLowerCase()+'(?:\\s|$)').test(c));
    if(!command)throw new Error('Native analysis did not generate the expected command');
    return {analysis_type:analysis,command,options_command:options,backend:'native analysis property parser and command compiler'};
  }finally{method('asys.dll','??1Analyses@@','void',['pointer'])(object);method('SHARUTIL.dll','??1CPropertyItem@@','void',['pointer'])(item);destroySimulationPropertyList(list);}
}
editorHandlers.documentSimulationSettings=documentSimulationSettings;
editorHandlers.documentAnalysisCommands=documentAnalysisCommands;

const sheetDisplayKeys={show_grid:['Grid ON','Simplified Grid ON'],show_border:['Border ON'],show_bounds:['Bounds ON']};
function sheetDisplaySettings(args={}) {
  const graph=diagram().graph,prefs=new NativeFunction(graph.readPointer().add(0x5c).readPointer(),'pointer',['pointer'],'thiscall')(graph);
  if(prefs.isNull())throw new Error('Native sheet preferences are unavailable');
  const read=()=>{
    const result={};
    for(const keys of Object.values(sheetDisplayKeys))for(const key of keys){
      const name=pathString(key),out=Memory.alloc(8);
      // These preference APIs take CString by value and consume its reference.
      if(!method('PREFS.dll','?GetPrefsAsDouble@CPreferences@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),out))throw new Error('Missing native sheet preference: '+key);result[key]=out.readDouble();
    }return result;
  };
  const before=read();
  for(const [option,enabled] of Object.entries(args)){
    if(!Object.prototype.hasOwnProperty.call(sheetDisplayKeys,option)||typeof enabled!=='boolean')throw new Error('Unknown or invalid sheet display option: '+option);
    for(const key of sheetDisplayKeys[option]){
      const name=pathString(key),value=pathString(enabled?'1':'0');
      if(!method('PREFS.dll','?SetPrefsAsString@CIITCircuitPrefs@@','uint8',['pointer','pointer','pointer'])(prefs,name.readPointer(),value.readPointer()))throw new Error('Native sheet preference write failed: '+key);
    }
  }
  const after=read();
  for(const [option,enabled] of Object.entries(args))for(const key of sheetDisplayKeys[option])if(after[key]!==Number(enabled))throw new Error('Native sheet preference readback failed: '+key);
  return {scope:'circuit',sheet_index:readSheets().find(s=>s.selected).index,native_preferences:after,
    configuration:Object.fromEntries(Object.entries(sheetDisplayKeys).map(([k,keys])=>[k,!!after[keys[0]]])),changed:JSON.stringify(before)!==JSON.stringify(after)};
}
function persistenceSheetData(state) {
  const cache=new Map();
  for(const c of state.components){
    const model=method('CIRCEXP.dll','?GetModel@CiElement@@','pointer',['pointer'])(ciObject(ptr(c.id)));let text=null;
    if(!model.isNull()){
      if(cache.has(model.toString()))text=cache.get(model.toString());
      else{
        const attr=method('CIRCEXP.dll','?GetAttribute@CiElement@@','pointer',['pointer','uint'])(model,1);
        if(!attr.isNull()&&rtti(attr).name==='.?AVCiaCString@@')text=method('CIRCEXP.dll','?GetString@CiaCString@@','pointer',['pointer'])(attr).readPointer().readUtf16String();
        cache.set(model.toString(),text);
      }
    }c.model_text=text;
  }
  const annotations=[];
  for(const object of listChildren(diagram().composite))if(/^\.\?AVCODTextComp@@/.test(rtti(object).name)){
    const text=instanceString('Od101dll.dll','?GetText@CODTextComp@@',object,[treeInstance()],['pointer']);
    // Node text is generated from persistent wire naming/display properties.
    // Only independent user annotations have portable text geometry here.
    if(text.length)annotations.push({text,transform:matrix(object)});
  }
  const endpoint=p=>Object.fromEntries(['ref','pin','x','y'].filter(k=>k in p).map(k=>[k,p[k]]));
  const wire_labels=wires().wires.flatMap(w=>{const label=persistentWireLabel(w.id);return label?[{source:endpoint(w.source),target:endpoint(w.target),...label}]:[];});
  return {annotations,wire_labels,sheet_display:sheetDisplaySettings().native_preferences};
}
editorHandlers.sheetDisplaySettings=sheetDisplaySettings;
editorHandlers.persistWiringOptions=persistWiringOptions;
editorHandlers.openDocument=openDocument;
