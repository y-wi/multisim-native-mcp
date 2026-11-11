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
  if(count<0||count>10000)throw new Error('Unsupported native simulation property count');
  for(let i=0;i<count;i++) {
    const item=Memory.alloc(128);method('SHARUTIL.dll','??0CPropertyItem@@QAE@XZ','pointer',['pointer'])(item);
    try {
      if(!method('SHARUTIL.dll','?GetNth@CPropertyList@@','int',['pointer','int','pointer'])(list,i,item))throw new Error('Cannot read native simulation property');
      callback(item,simulationPropertyLabel(item));
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
