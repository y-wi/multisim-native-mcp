// Native NI Multisim virtual instrument placement, property read/write, readouts and trace export.
// Uses official exported CComponentHandler, CODPasteAct, DropComponentsOnDiagram, CSnapinHandler,
// CInstrumentBase, and CDataElementMap APIs with zero hardcoded build RVAs.

const instrumentVtableSlots = new Map();

function instrumentVtableSlot(dll, vtableExport, methodPrefix) {
  const key = dll + '|' + vtableExport + '|' + methodPrefix;
  if (instrumentVtableSlots.has(key)) return instrumentVtableSlots.get(key);
  const mod = Process.getModuleByName(dll);
  const vtable = mod.getExportByName(vtableExport);
  const matches = mod.enumerateExports().filter(e => e.name.startsWith(methodPrefix));
  if (matches.length !== 1) throw new Error('Expected one native virtual method ' + dll + ' ' + methodPrefix + '; found ' + matches.length);
  const target = matches[0].address;
  for (let i = 0; i < 256; i++) {
    if (vtable.add(i * 4).readPointer().equals(target)) {
      instrumentVtableSlots.set(key, i);
      return i;
    }
  }
  throw new Error('Virtual slot not found in ' + vtableExport + ' for ' + methodPrefix);
}

function isInstrumentSymbol(sym) {
  try {
    return !!method('Od101dll.dll', '?IsInstrument@CODComponentBridge@@SA_NPAVCODSymbolComp@@@Z', 'uint8', ['pointer'], 'mscdecl')(sym);
  } catch (_) {
    return false;
  }
}

function instrumentManagerForSymbol(sym) {
  try {
    return readCStringResult(out => method('Od101dll.dll', '?GetInstrumentMgr@CODComponentBridge@@', 'pointer', ['pointer', 'pointer'], 'mscdecl')(out, sym), []);
  } catch (_) {
    return '';
  }
}

function instrumentTypeForSymbol(sym) {
  try {
    return readCStringResult(out => method('Od101dll.dll', '?GetInstrumentType@CODComponentBridge@@SA?AV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@PAVCODSymbolComp@@@Z', 'pointer', ['pointer', 'pointer'], 'mscdecl')(out, sym), []);
  } catch (_) {
    return '';
  }
}

function getInstrumentSink(sym) {
  const sch = Process.getModuleByName('SCH_CAP.dll');
  const snapHandler = sch.getExportByName('?m_pSnapinHandler@CSnapinHandler@@1PAV1@A').readPointer();
  if (snapHandler.isNull()) throw new Error('Native instrument snap-in handler is unavailable');
  const refId = readCStringResult(out => method('SCH_CAP.dll', '?GetInstRefID@CSnapinHandler@@', 'pointer', ['pointer', 'pointer', 'pointer'])(snapHandler, out, sym), []);
  if (!refId) return { refId: '', sink: ptr(0) };
  const refIdStr = pathString(refId);
  try {
    const sink = method('SCH_CAP.dll', '?GetInstEventSink@CSnapinHandler@@', 'pointer', ['pointer', 'pointer'])(snapHandler, refIdStr);
    return { refId, sink };
  } finally {
    native('Library.dll', '??1CPathString@@QAE@XZ', 'void', ['pointer'])(refIdStr);
  }
}

const DATA_ELEMENT_TYPES = { 0: 'empty', 1: 'int', 2: 'uint', 3: 'double', 4: 'array', 5: 'string', 6: 'map', 7: 'blob', 8: 'bool', 9: 'time' };
const DATA_ELEMENT_STRIDE = 24;

function readDataElementString(elem) {
  const emptyStr = pathString('');
  try {
    return readCStringResult(out => method('EwbBase.dll', '?GetValueAsString@CDataElement@@', 'pointer', ['pointer', 'pointer', 'pointer', 'pointer'])(elem, out, emptyStr, ptr(0)), []);
  } finally {
    native('Library.dll', '??1CPathString@@QAE@XZ', 'void', ['pointer'])(emptyStr);
  }
}

function readDataElement(elem, depth = 0) {
  if (elem.isNull()) return null;
  const type = method('EwbBase.dll', '?GetType@CDataElement@@QBE?AW4EDataElementType@1@XZ', 'int', ['pointer'])(elem);
  if (type === 1) {
    const v = method('EwbBase.dll', '?GetValue@CDataElement@@QBE_J_J@Z', 'int64', ['pointer', 'int64'])(elem, int64(0));
    return { type: 'int', native_type: 1, value: v.toNumber() };
  }
  if (type === 2) {
    const v = method('EwbBase.dll', '?GetValue@CDataElement@@QBE_K_K@Z', 'uint64', ['pointer', 'uint64'])(elem, uint64(0));
    return { type: 'uint', native_type: 2, value: v.toNumber() };
  }
  if (type === 3) {
    const text = readDataElementString(elem);
    const num = Number(text);
    return { type: 'double', native_type: 3, value: Number.isFinite(num) ? num : text };
  }
  if (type === 5) {
    return { type: 'string', native_type: 5, value: readDataElementString(elem) };
  }
  if (type === 8) {
    const v = method('EwbBase.dll', '?GetValue@CDataElement@@QBE_N_N@Z', 'uint8', ['pointer', 'uint8'])(elem, 0);
    return { type: 'bool', native_type: 8, value: !!v };
  }
  if (type === 6 && depth < 4) {
    const emptyMap = Process.getModuleByName('EwbBase.dll').getExportByName('?m_EmptyDataElementMap@CDataElementMap@@2V1@B');
    const subMap = method('EwbBase.dll', '?GetValue@CDataElement@@QBEPAVCDataElementMap@@ABV2@@Z', 'pointer', ['pointer', 'pointer'])(elem, emptyMap);
    return { type: 'map', native_type: 6, value: readDataElementMap(subMap, depth + 1) };
  }
  if (type === 4 && depth < 4) {
    const emptyVec = Process.getModuleByName('EwbBase.dll').getExportByName('?m_EmptyDataElementVector@CDataElementMap@@2V?$vector@VCDataElement@@V?$allocator@VCDataElement@@@std@@@std@@B');
    const subVec = method('EwbBase.dll', '?GetValue@CDataElement@@QBEPAV?$vector@VCDataElement@@V?$allocator@VCDataElement@@@std@@@std@@ABV23@@Z', 'pointer', ['pointer', 'pointer'])(elem, emptyVec);
    const begin = subVec.readPointer(), end = subVec.add(4).readPointer();
    const len = begin.isNull() || end.compare(begin) < 0 ? 0 : Math.floor(end.sub(begin).toInt32() / DATA_ELEMENT_STRIDE);
    const arr = [];
    for (let i = 0; i < Math.min(len, 128); i++) {
      arr.push(readDataElement(begin.add(i * DATA_ELEMENT_STRIDE), depth + 1));
    }
    return { type: 'array', native_type: 4, length: len, value: arr };
  }
  return { type: DATA_ELEMENT_TYPES[type] || String(type), native_type: type, value: readDataElementString(elem) };
}

function readDataElementMap(map, depth = 0) {
  const count = method('EwbBase.dll', '?GetElementCount@CDataElementMap@@', 'uint', ['pointer'])(map);
  const obj = {};
  for (let i = 0; i < count; i++) {
    const namePool = method('EwbBase.dll', '?GetElementName@CDataElementMap@@', 'pointer', ['pointer', 'uint'])(map, i);
    const name = method('Library.dll', '?GetCharString@CPoolString@@', 'pointer', ['pointer'])(namePool).readUtf16String();
    const elem = method('EwbBase.dll', '?GetElement@CDataElementMap@@UBEPBVCDataElement@@ABVCPoolString@@@Z', 'pointer', ['pointer', 'pointer'])(map, namePool);
    obj[name] = readDataElement(elem, depth);
  }
  return obj;
}

function setDataElementScalar(elem, nativeType, val) {
  if (nativeType === 1) {
    if (typeof val !== 'number' || !Number.isFinite(val)) throw new Error('Expected finite integer value');
    method('EwbBase.dll', '?SetValue@CDataElement@@QAEX_J@Z', 'void', ['pointer', 'int64'])(elem, int64(Math.trunc(val)));
  } else if (nativeType === 2) {
    if (typeof val !== 'number' || !Number.isFinite(val) || val < 0) throw new Error('Expected non-negative integer value');
    method('EwbBase.dll', '?SetValue@CDataElement@@QAEX_K@Z', 'void', ['pointer', 'uint64'])(elem, uint64(Math.trunc(val)));
  } else if (nativeType === 3) {
    if (typeof val !== 'number' || !Number.isFinite(val)) throw new Error('Expected finite numeric value');
    method('EwbBase.dll', '?SetValue@CDataElement@@QAEXN@Z', 'void', ['pointer', 'double'])(elem, Number(val));
  } else if (nativeType === 5) {
    const pool = Memory.alloc(64);
    method('Library.dll', '??0CPoolString@@QAE@PB_W@Z', 'pointer', ['pointer', 'pointer'])(pool, Memory.allocUtf16String(String(val)));
    try {
      method('EwbBase.dll', '?SetValue@CDataElement@@QAEXABVCPoolString@@@Z', 'void', ['pointer', 'pointer'])(elem, pool);
    } finally {
      method('Library.dll', '??1CPoolString@@', 'void', ['pointer'])(pool);
    }
  } else if (nativeType === 8) {
    method('EwbBase.dll', '?SetValue@CDataElement@@QAEX_N@Z', 'void', ['pointer', 'uint8'])(elem, val ? 1 : 0);
  } else {
    throw new Error('Unsupported native CDataElement type for write: ' + nativeType);
  }
}

function setMapElementScalar(map, name, nativeType, val) {
  const pool = Memory.alloc(64);
  method('Library.dll', '??0CPoolString@@QAE@PB_W@Z', 'pointer', ['pointer', 'pointer'])(pool, Memory.allocUtf16String(name));
  try {
    if (nativeType === 1) {
      if (typeof val !== 'number' || !Number.isFinite(val)) throw new Error('Expected finite integer for ' + name);
      method('EwbBase.dll', '?SetElement@CDataElementMap@@UAEXABVCPoolString@@_J@Z', 'void', ['pointer', 'pointer', 'int64'])(map, pool, int64(Math.trunc(val)));
    } else if (nativeType === 2) {
      if (typeof val !== 'number' || !Number.isFinite(val) || val < 0) throw new Error('Expected non-negative integer for ' + name);
      method('EwbBase.dll', '?SetElement@CDataElementMap@@UAEXABVCPoolString@@_K@Z', 'void', ['pointer', 'pointer', 'uint64'])(map, pool, uint64(Math.trunc(val)));
    } else if (nativeType === 3) {
      if (typeof val !== 'number' || !Number.isFinite(val)) throw new Error('Expected finite number for ' + name);
      method('EwbBase.dll', '?SetElement@CDataElementMap@@UAEXABVCPoolString@@N@Z', 'void', ['pointer', 'pointer', 'double'])(map, pool, Number(val));
    } else if (nativeType === 5) {
      const valPool = Memory.alloc(64);
      method('Library.dll', '??0CPoolString@@QAE@PB_W@Z', 'pointer', ['pointer', 'pointer'])(valPool, Memory.allocUtf16String(String(val)));
      try {
        method('EwbBase.dll', '?SetElement@CDataElementMap@@UAEXABVCPoolString@@0@Z', 'void', ['pointer', 'pointer', 'pointer'])(map, pool, valPool);
      } finally {
        method('Library.dll', '??1CPoolString@@', 'void', ['pointer'])(valPool);
      }
    } else if (nativeType === 8) {
      method('EwbBase.dll', '?SetElement@CDataElementMap@@QAEXABVCPoolString@@_N@Z', 'void', ['pointer', 'pointer', 'uint8'])(map, pool, val ? 1 : 0);
    } else {
      throw new Error('Unsupported native property type ' + nativeType + ' for ' + name);
    }
  } finally {
    method('Library.dll', '??1CPoolString@@', 'void', ['pointer'])(pool);
  }
}

function getMapElementPtr(map, name) {
  const pool = Memory.alloc(64);
  method('Library.dll', '??0CPoolString@@QAE@PB_W@Z', 'pointer', ['pointer', 'pointer'])(pool, Memory.allocUtf16String(name));
  try {
    return method('EwbBase.dll', '?GetElement@CDataElementMap@@UBEPBVCDataElement@@ABVCPoolString@@@Z', 'pointer', ['pointer', 'pointer'])(map, pool);
  } finally {
    method('Library.dll', '??1CPoolString@@', 'void', ['pointer'])(pool);
  }
}

function writePathInMap(rootMap, path, value) {
  if (!Array.isArray(path) || path.length === 0) throw new Error('Property path must be non-empty');
  let curMap = rootMap;
  let curElem = ptr(0);
  for (let i = 0; i < path.length; i++) {
    const token = path[i];
    const isLast = i === path.length - 1;
    if (typeof token === 'string') {
      if (curMap.isNull()) throw new Error('Expected map container before key ' + token);
      const elem = getMapElementPtr(curMap, token);
      if (elem.isNull()) {
        const available = Object.keys(readDataElementMap(curMap, 0)).join(', ');
        throw new Error('Unknown native instrument property ' + JSON.stringify(token) + '; available: ' + available);
      }
      const nativeType = method('EwbBase.dll', '?GetType@CDataElement@@QBE?AW4EDataElementType@1@XZ', 'int', ['pointer'])(elem);
      if (isLast) {
        setMapElementScalar(curMap, token, nativeType, value);
        return nativeType;
      }
      curElem = elem;
      if (nativeType === 6) {
        const emptyMap = Process.getModuleByName('EwbBase.dll').getExportByName('?m_EmptyDataElementMap@CDataElementMap@@2V1@B');
        curMap = method('EwbBase.dll', '?GetValue@CDataElement@@QBEPAVCDataElementMap@@ABV2@@Z', 'pointer', ['pointer', 'pointer'])(elem, emptyMap);
      } else {
        curMap = ptr(0);
      }
    } else if (typeof token === 'number' && Number.isInteger(token)) {
      if (curElem.isNull()) throw new Error('Array index [' + token + '] requires an array property');
      const arrType = method('EwbBase.dll', '?GetType@CDataElement@@QBE?AW4EDataElementType@1@XZ', 'int', ['pointer'])(curElem);
      if (arrType !== 4) throw new Error('Property is not an array before index [' + token + ']');
      const emptyVec = Process.getModuleByName('EwbBase.dll').getExportByName('?m_EmptyDataElementVector@CDataElementMap@@2V?$vector@VCDataElement@@V?$allocator@VCDataElement@@@std@@@std@@B');
      const subVec = method('EwbBase.dll', '?GetValue@CDataElement@@QBEPAV?$vector@VCDataElement@@V?$allocator@VCDataElement@@@std@@@std@@ABV23@@Z', 'pointer', ['pointer', 'pointer'])(curElem, emptyVec);
      const begin = subVec.readPointer(), end = subVec.add(4).readPointer();
      const len = begin.isNull() || end.compare(begin) < 0 ? 0 : Math.floor(end.sub(begin).toInt32() / DATA_ELEMENT_STRIDE);
      if (token < 0 || token >= len) throw new Error('Array index [' + token + '] out of bounds (length ' + len + ')');
      const itemElem = begin.add(token * DATA_ELEMENT_STRIDE);
      const itemType = method('EwbBase.dll', '?GetType@CDataElement@@QBE?AW4EDataElementType@1@XZ', 'int', ['pointer'])(itemElem);
      if (isLast) {
        setDataElementScalar(itemElem, itemType, value);
        return itemType;
      }
      curElem = itemElem;
      if (itemType === 6) {
        const emptyMap = Process.getModuleByName('EwbBase.dll').getExportByName('?m_EmptyDataElementMap@CDataElementMap@@2V1@B');
        curMap = method('EwbBase.dll', '?GetValue@CDataElement@@QBEPAVCDataElementMap@@ABV2@@Z', 'pointer', ['pointer', 'pointer'])(itemElem, emptyMap);
      } else {
        curMap = ptr(0);
      }
    } else {
      throw new Error('Invalid path token: ' + JSON.stringify(token));
    }
  }
  throw new Error('Unreachable path end');
}

function readPathFromRaw(rawProps, path) {
  let cur = rawProps;
  for (let i = 0; i < path.length; i++) {
    const token = path[i];
    if (i === 0) {
      if (!cur || !(token in cur)) return undefined;
      cur = cur[token];
      continue;
    }
    if (cur && typeof cur === 'object' && 'native_type' in cur && 'value' in cur) cur = cur.value;
    if (typeof token === 'number') {
      if (!Array.isArray(cur) || token < 0 || token >= cur.length) return undefined;
      cur = cur[token];
    } else {
      if (!cur || typeof cur !== 'object' || !(token in cur)) return undefined;
      cur = cur[token];
    }
  }
  return cur;
}

function readInstrumentProperties(sym) {
  const { refId, sink } = getInstrumentSink(sym);
  if (sink.isNull()) throw new Error('Virtual instrument native backend is unavailable (refId=' + refId + ')');
  const slot = instrumentVtableSlot('SHARUTIL.dll', '??_7CInstrumentBase@@6B@', '?UpdatePropertiesInMap@CInstrumentBase@@');
  const fn = new NativeFunction(sink.readPointer().add(slot * 4).readPointer(), 'void', ['pointer', 'pointer', 'uint8'], 'thiscall');
  const map = Memory.alloc(512);
  method('EwbBase.dll', '??0CDataElementMap@@QAE@XZ', 'pointer', ['pointer'])(map);
  try {
    fn(sink, map, 1);
    return { refId, sinkClass: rtti(sink).name, raw_properties: readDataElementMap(map) };
  } finally {
    method('EwbBase.dll', '??1CDataElementMap@@UAE@XZ', 'void', ['pointer'])(map);
  }
}

function refreshCurrentProbeLabel(sink) {
  method('imeter.dll', '?SetSymbolCompValueString@CIMeterInstrument@@UAEXXZ', 'void', ['pointer'])(sink);
}

function restoreCurrentProbeLabels() {
  // Multisim stores the ratio, but clears the derived value text when loading a sheet.
  for (const sym of listChildren(diagram().composite)) {
    if (rtti(sym).name !== '.?AVCIITIMeterSymbolComp@@') continue;
    const label = listChildren(sym).find(child => rtti(child).name === '.?AVCIITSymTextCompValue@@');
    if (!label || instanceString('Od101dll.dll', '?GetText@CODTextComp@@', label, [treeInstance()], ['pointer'])) continue;
    const { sink } = getInstrumentSink(sym);
    if (!sink.isNull()) refreshCurrentProbeLabel(sink);
  }
}

function syncInstrumentAfterWrite(sink, writes) {
  const sinkClass = rtti(sink).name;
  // CMultimeterInstrument::SetMeasurementMode updates the SPICE subcircuit shunt/open-circuit impedance.
  if (sinkClass === '.?AVCMultimeterInstrument@@') {
    const modeWrite = writes.find(w => w.path.length === 1 && w.path[0] === 'NI_EWB_MEASUREMENT_MODE');
    if (modeWrite) {
      method('mulmeter.dll', '?SetMeasurementMode@CMultimeterInstrument@@', 'uint8', ['pointer', 'int'])(sink, Math.trunc(modeWrite.value));
    }
  }
  // Invoke the concrete instrument's UpdateDatabase() if exported by its owning DLL.
  const mod = Process.findModuleByAddress(sink.readPointer());
  if (mod) {
    const classBase = sinkClass.replace(/^\.\?AV/, '').replace(/@@$/, '');
    const updDb = mod.enumerateExports().find(e => e.name === '?UpdateDatabase@' + classBase + '@@QAEXXZ');
    if (updDb) {
      new NativeFunction(updDb.address, 'void', ['pointer'], 'thiscall')(sink);
    }
  }
  if (sinkClass === '.?AVCIMeterInstrument@@') refreshCurrentProbeLabel(sink);
  method('SHARUTIL.dll', '?UpdateDatabase_netlist@CInstrumentBase@@', 'void', ['pointer'])(sink);
  method('SHARUTIL.dll', '?UpdateDatabase_ModelTemplate@CInstrumentBase@@', 'void', ['pointer'])(sink);
  const refreshSlot = instrumentVtableSlot('SHARUTIL.dll', '??_7CInstrumentBase@@6B@', '?refresh_instrument_dialog@CInstrumentBase@@');
  new NativeFunction(sink.readPointer().add(refreshSlot * 4).readPointer(), 'void', ['pointer', 'int', 'uint8'], 'thiscall')(sink, 1, 1);
}

function valuesMatchReadback(nativeType, expected, actual) {
  if (nativeType === 1 || nativeType === 2) return actual === Math.trunc(expected);
  if (nativeType === 3) {
    const exp = Number(expected), act = Number(actual);
    if (!Number.isFinite(exp) || !Number.isFinite(act)) return false;
    const scale = Math.max(1, Math.abs(exp), Math.abs(act));
    return Math.abs(exp - act) <= 1e-5 * scale;
  }
  if (nativeType === 8) return Boolean(actual) === Boolean(expected);
  return String(actual) === String(expected);
}

function writeInstrumentProperties(sym, writes) {
  if (!Array.isArray(writes) || !writes.length) throw new Error('No instrument setting writes supplied');
  const { refId, sink } = getInstrumentSink(sym);
  if (sink.isNull()) throw new Error('Virtual instrument native backend is unavailable (refId=' + refId + ')');
  const slot = instrumentVtableSlot('SHARUTIL.dll', '??_7CInstrumentBase@@6B@', '?UpdatePropertiesInMap@CInstrumentBase@@');
  const updateFn = new NativeFunction(sink.readPointer().add(slot * 4).readPointer(), 'void', ['pointer', 'pointer', 'uint8'], 'thiscall');
  const map = Memory.alloc(512);
  method('EwbBase.dll', '??0CDataElementMap@@QAE@XZ', 'pointer', ['pointer'])(map);
  const applied = [];
  try {
    updateFn(sink, map, 1);
    for (const write of writes) {
      const nativeType = writePathInMap(map, write.path, write.value);
      applied.push({ path: write.path, source_key: write.source_key || write.path.join('.'), native_type: nativeType, value: write.value });
    }
    updateFn(sink, map, 0);
    syncInstrumentAfterWrite(sink, writes);
  } finally {
    method('EwbBase.dll', '??1CDataElementMap@@UAE@XZ', 'void', ['pointer'])(map);
  }
  const after = readInstrumentProperties(sym);
  for (const item of applied) {
    const actualNode = readPathFromRaw(after.raw_properties, item.path);
    if (!actualNode || !valuesMatchReadback(item.native_type, item.value, actualNode.value)) {
      throw new Error('Native instrument property readback failed for ' + item.source_key + ' (expected ' + JSON.stringify(item.value) + ', got ' + JSON.stringify(actualNode ? actualNode.value : null) + ')');
    }
  }
  return { ...after, applied };
}

function resolveInstrumentModule(dllName) {
  const existing = Process.enumerateModules().find(m => m.name.toLowerCase() === dllName.toLowerCase());
  if (existing) return existing;
  // Load dynamically from the Multisim installation directory if not yet mapped.
  const mainMod = Process.enumerateModules()[0];
  const dir = mainMod.path.replace(/[^\\\/]+$/, '');
  const loaded = Module.load(dir + dllName);
  if (!loaded) throw new Error('Instrument DLL could not be loaded: ' + dllName);
  return loaded;
}

function placeInstrument(args) {
  activateSheet();
  const anchor = args.anchor || 'origin';
  if (!['origin', 'center', 'pin'].includes(anchor)) throw new Error('Invalid placement anchor');
  if (anchor === 'pin' && (!args.pin || typeof args.pin !== 'string')) throw new Error('Placement with anchor=pin requires pin');
  if (args.angle !== undefined && (typeof args.angle !== 'number' || !Number.isFinite(args.angle))) throw new Error('Rotation must be finite');
  if (args.mirror_axis !== undefined && !['horizontal', 'vertical'].includes(args.mirror_axis)) throw new Error('Invalid mirror axis');
  if (args.ref && components().components.some(c => c.ref === args.ref)) {
    throw new Error('Reference already exists on this sheet: ' + args.ref);
  }
  const d = diagram(), tree = treeInstance();
  if (tree.isNull()) throw new Error('Selected sheet has no native tree instance');

  const mod = resolveInstrumentModule(args.dll);
  const fnName = args.create_kind === 'imeter'
    ? '?CreateInstrument_IMeter@CComponentHandler@@SAPAVCIITIMeterSymbolComp@@PAUHINSTANCE__@@ABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@II1@Z'
    : '?CreateInstrument@CComponentHandler@@SAPAVCIITSymbolComp@@PAUHINSTANCE__@@ABV?$CStringT@_WV?$StrTraitMFC_DLL@_WV?$ChTraitsCRT@_W@ATL@@@@@ATL@@II1@Z';
  const createInst = method('SCH_CAP.dll', fnName, 'pointer', ['pointer', 'pointer', 'uint', 'uint', 'pointer'], 'mscdecl');
  const managerStr = pathString(args.manager), emptyStr = pathString('');
  let sym = ptr(0);
  try {
    sym = createInst(mod.base, managerStr, args.res_id, args.flags, emptyStr);
  } finally {
    native('Library.dll', '??1CPathString@@QAE@XZ', 'void', ['pointer'])(managerStr);
    native('Library.dll', '??1CPathString@@QAE@XZ', 'void', ['pointer'])(emptyStr);
  }
  if (sym.isNull()) throw new Error('Native CreateInstrument returned null for ' + args.dll);

  try {
    method('SCH_CAP.dll', '?SetInitialVariantData@CComponentHandler@@', 'void', ['pointer', 'int'], 'mscdecl')(sym, 0);
  } catch (_) {}

  // Drop via Multisim's official CODPasteAct + DropComponentsOnDiagram pipeline so electrical
  // ports, CSnapinHandler registration, RefDes allocation, and Undo bookkeeping initialize natively.
  const getProc = ptrFunction('kernel32.dll', 'GetProcAddress', ['pointer', 'pointer'], 'stdcall');
  const allocate = new NativeFunction(getProc(Process.getModuleByName('mfc140u.dll').base, ptr(1511)), 'pointer', ['uint'], 'mscdecl');
  const list = allocate(28);
  if (list.isNull()) throw new Error('Native component list allocation failed');
  method('Od101dll.dll', '??0CODCompList@@QAE@PAVCODComponent@@@Z', 'pointer', ['pointer', 'pointer'])(list, sym);
  const action = allocateObject('CODPasteAct', '??0CODPasteAct@@QAE@PAVCTreeInstance@@PAVCODDiagram@@PAVCODCompList@@@Z',
    [tree, d.graph, list], ['pointer', 'pointer', 'pointer']);
  const dropResult = temporaryWiring({ connect_touching: false }, () =>
    method('SCH_CAP.dll', '?DropComponentsOnDiagram@@', 'int',
      ['pointer', 'pointer', 'pointer', ...Array(7).fill('uint8'), 'pointer', 'uint8'], 'mscdecl')
      (d.graph, tree, action, 1, 1, 1, 0, 0, 0, 0, ptr(0), 0)
  );
  if (dropResult < 0) throw new Error('Native instrument drop failed: ' + dropResult);

  let c = component(sym.toString());
  if (args.ref && c.ref !== args.ref) {
    renameComponent({ ref: c.id, new_ref: args.ref });
    c = component(sym.toString());
  }
  if (args.angle !== undefined) transformComponent({ ref: c.id, angle: args.angle });
  if (args.mirror_axis !== undefined) transformComponent({ ref: c.id, axis: args.mirror_axis });
  c = component(sym.toString());

  const origin = matrix(sym);
  let point = { x: origin[4], y: origin[5] };
  if (anchor === 'pin') {
    point = c.pins.find(p => p.name === args.pin);
    if (!point) throw new Error('Placement anchor pin not found: ' + args.pin + '; available pins: ' + c.pins.map(p => p.name).join(', '));
  } else if (anchor === 'center') {
    const b = symbolBodyBounds(c);
    point = { x: (b.left + b.right) / 2, y: (b.top + b.bottom) / 2 };
  }
  method('Od101dll.dll', '?MoveComponentBy@CODDiagram@@', 'void', ['pointer', 'pointer', 'int', 'int'])(d.graph, sym, Math.round(args.x - point.x), Math.round(args.y - point.y));

  let propInfo;
  if (Array.isArray(args.writes) && args.writes.length) {
    propInfo = writeInstrumentProperties(sym, args.writes);
  } else {
    propInfo = readInstrumentProperties(sym);
  }

  let touching = null;
  if (wiringOptions().connect_touching) {
    touching = connectTouching({ refs: [c.id] });
  }

  c = component(sym.toString());
  const body = symbolBodyBounds(c);
  const actual = anchor === 'pin'
    ? c.pins.find(p => p.name === args.pin)
    : anchor === 'center'
      ? { x: (body.left + body.right) / 2, y: (body.top + body.bottom) / 2 }
      : { x: c.transform[4], y: c.transform[5] };
  const placement = {
    coordinate_system: 'sheet_units',
    pin_offsets: c.pins.map(p => ({ name: p.name, dx: p.x - actual.x, dy: p.y - actual.y })),
    anchor,
    ...(anchor === 'pin' ? { pin: args.pin } : {}),
    requested: { x: args.x, y: args.y },
    actual: { x: actual.x, y: actual.y },
    origin: { x: c.transform[4], y: c.transform[5] },
    body_bounds: body,
  };
  const page = pageGeometry();
  const offPage = body.left < 0 || body.top < 0 || body.right > page.width || body.bottom > page.height;
  const warnings = offPage
    ? [{ code: 'outside_page', reference: c.ref, message: 'Instrument is outside the page. Use fit_sheet or a region to include it in the exported image.' }]
    : [];
  const manager = instrumentManagerForSymbol(sym);
  const instType = instrumentTypeForSymbol(sym);
  return {
    component: { ...c, is_instrument: true, instrument_manager: manager, instrument_type: instType },
    instrument_manager: manager,
    instrument_type: instType,
    sink_class: propInfo.sinkClass,
    raw_properties: propInfo.raw_properties,
    ...(propInfo.applied ? { applied: propInfo.applied } : {}),
    page,
    placement,
    labels: componentLabels({ ref: c.id }).labels,
    warnings,
    ...(touching ? { touching } : {}),
    topology_changed: true,
  };
}

function getInstrumentSettings(args) {
  const c = component(args.ref);
  const sym = ptr(c.id);
  if (!isInstrumentSymbol(sym)) {
    throw new Error(c.ref + ' is a standard schematic component, not a virtual instrument; use native_get_parameters instead.');
  }
  const info = readInstrumentProperties(sym);
  return {
    ref: c.ref,
    component_id: c.id,
    instrument_manager: instrumentManagerForSymbol(sym),
    instrument_type: instrumentTypeForSymbol(sym),
    sink_class: info.sinkClass,
    pins: c.pins,
    raw_properties: info.raw_properties,
  };
}

function setInstrumentSettings(args) {
  const c = component(args.ref);
  const sym = ptr(c.id);
  if (!isInstrumentSymbol(sym)) {
    throw new Error(c.ref + ' is a standard schematic component, not a virtual instrument; use native_set_parameter instead.');
  }
  const info = writeInstrumentProperties(sym, args.writes);
  return {
    ref: c.ref,
    component_id: c.id,
    instrument_manager: instrumentManagerForSymbol(sym),
    instrument_type: instrumentTypeForSymbol(sym),
    sink_class: info.sinkClass,
    applied: info.applied,
    raw_properties: info.raw_properties,
    topology_changed: false,
  };
}

function listPlacedInstruments() {
  const items = [];
  for (const c of components().components) {
    const sym = ptr(c.id);
    if (!isInstrumentSymbol(sym)) continue;
    let rawProps = null, sinkClass = null;
    try {
      const info = readInstrumentProperties(sym);
      rawProps = info.raw_properties;
      sinkClass = info.sinkClass;
    } catch (_) {}
    items.push({
      id: c.id,
      ref: c.ref,
      instrument_manager: instrumentManagerForSymbol(sym),
      instrument_type: instrumentTypeForSymbol(sym),
      sink_class: sinkClass,
      transform: c.transform,
      pins: c.pins,
      raw_properties: rawProps,
    });
  }
  return { instruments: items };
}

function liveInstrumentReadouts() {
  const readouts = [];
  for (const c of components().components) {
    const sym = ptr(c.id);
    if (!isInstrumentSymbol(sym)) continue;
    try {
      const info = readInstrumentProperties(sym);
      const props = info.raw_properties;
      const mgr = instrumentManagerForSymbol(sym);
      const item = { ref: c.ref, component_id: c.id, instrument_manager: mgr, instrument_type: instrumentTypeForSymbol(sym) };
      if (info.sinkClass === '.?AVCMultimeterInstrument@@') {
        readouts.push({
          ...item,
          display_value: String(props.NI_EWB_CURRENTDISPLAYDATA_VALUE?.value ?? '').trim(),
          measurement_mode: props.NI_EWB_MEASUREMENT_MODE?.value ?? null,
          signal_mode: props.NI_EWB_SIGNAL_MODE?.value ?? null,
        });
      } else if (info.sinkClass === '.?AVCWattMeterInstrument@@') {
        readouts.push({
          ...item,
          power: String(props.NI_EWB_CURRENTDISPLAYDATAVALUE?.value ?? '').trim(),
          power_factor: String(props.NI_EWB_CURRENTDISPLAYDATAFACTOR?.value ?? '').trim(),
        });
      } else if (info.sinkClass === '.?AVCDistortionInstrument@@') {
        readouts.push({
          ...item,
          distortion_value: props.NI_EWB_CURRENTDISPLAYDATA_DISTORTIONVALUE?.value ?? null,
          resolution: String(props.NI_EWB_CURRENTDISPLAYDATA_RESOLUTION?.value ?? '').trim(),
        });
      } else if (info.sinkClass === '.?AVCMultimeter_ATInstrument@@') {
        readouts.push({
          ...item,
          dc_voltage: props.NI_EWB_DC_VOLTAGE?.value ?? null,
          ac_voltage: props.NI_EWB_AC_VOLTAGE?.value ?? null,
          frequency: props.NI_EWB_FREQ_VALUE?.value ?? null,
        });
      }
    } catch (_) {}
  }
  return readouts;
}

function exportInstrumentData(args) {
  const c = component(args.ref);
  const sym = ptr(c.id);
  if (!isInstrumentSymbol(sym)) {
    throw new Error(c.ref + ' is not a virtual instrument');
  }
  const { sink } = getInstrumentSink(sym);
  if (sink.isNull()) throw new Error('Virtual instrument native backend is unavailable');
  const sinkClass = rtti(sink).name;
  const exporters = {
    '.?AVCScopeInstrument@@': ['scope.dll', '?write_data_file@CScopeInstrument@@'],
    '.?AVCScope_4chInstrument@@': ['scope_4ch.dll', '?write_data_file@CScope_4chInstrument@@'],
    '.?AVCBodeInstrument@@': ['bode.dll', '?write_data_file@CBodeInstrument@@'],
  };
  const spec = exporters[sinkClass];
  if (!spec) {
    throw new Error('Native trace export is supported for 2-channel Oscilloscope, 4-channel Oscilloscope, and Bode Plotter (got ' + sinkClass + ')');
  }
  const pStr = pathString(args.path);
  // write_data_file takes CString by value (consumes the internal string pointer).
  method(spec[0], spec[1], 'void', ['pointer', 'pointer'])(sink, pStr.readPointer());
  return {
    ref: c.ref,
    component_id: c.id,
    sink_class: sinkClass,
    path: args.path,
  };
}

editorHandlers.placeInstrument = placeInstrument;
editorHandlers.getInstrumentSettings = getInstrumentSettings;
editorHandlers.setInstrumentSettings = setInstrumentSettings;
editorHandlers.listPlacedInstruments = listPlacedInstruments;
editorHandlers.exportInstrumentData = exportInstrumentData;
