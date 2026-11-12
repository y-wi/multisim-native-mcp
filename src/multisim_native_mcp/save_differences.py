"""Actionable differences between native saved document signatures."""
import json
from collections import Counter


def object_identity(value,kind,secondary=False):
    if not isinstance(value,dict):return None
    if kind=='components':
        if not secondary:return value.get('ref')
        return (value['transform'],value['pins']) if 'transform' in value and 'pins' in value else None
    if kind=='annotations':return value.get('transform') if secondary else value.get('text')
    if kind in ('wires','wire_labels'):
        if secondary:return value.get('name')
        return [{k:value.get(end,{}).get(k) for k in (('ref','pin') if value.get(end,{}).get('ref') else ('x','y'))} for end in ('source','target')]


def object_path(path,value):
    if isinstance(value,dict):
        key='ref' if 'ref' in value else 'text' if 'text' in value else None
        if key:return path+'['+key+'='+json.dumps(value[key],ensure_ascii=False)+']'
        if 'source' in value and 'target' in value:
            endpoint=lambda e:str(e.get('ref','junction'))+'.'+str(e.get('pin',''))
            return path+'['+json.dumps(endpoint(value['source'])+' -> '+endpoint(value['target']),ensure_ascii=False)+']'
    return path


def saved_differences(expected, actual, path='sheets'):
    if expected == actual:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences=[]
        for key in sorted(expected.keys()|actual.keys()):
            field=path+'.'+key
            if key not in actual:differences.append({'path':field,'kind':'missing','expected':expected[key]})
            elif key not in expected:differences.append({'path':field,'kind':'unexpected','actual':actual[key]})
            else:differences.extend(saved_differences(expected[key],actual[key],field))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        if path.endswith(('.annotations', '.components', '.wires', '.wire_labels')):
            encode=lambda value:json.dumps(value, sort_keys=True, ensure_ascii=False)
            remaining=Counter(encode(value) for value in actual);missing=[];unexpected=[];differences=[]
            for value in expected:
                key=encode(value)
                if remaining[key]:remaining[key]-=1
                else:missing.append(value)
            for value in actual:
                key=encode(value)
                if remaining[key]:
                    unexpected.append(value);remaining[key]-=1
            kind=path.rsplit('.',1)[-1]
            for secondary in (False,True):
                left={};right={}
                for items,groups in ((missing,left),(unexpected,right)):
                    for index,value in enumerate(items):
                        identity=object_identity(value,kind,secondary)
                        if identity is not None:groups.setdefault(encode(identity),[]).append(index)
                paired_left=set();paired_right=set()
                for identity,indices in left.items():
                    hits=right.get(identity,[])
                    if len(indices)==len(hits)==1:
                        a,b=indices[0],hits[0];paired_left.add(a);paired_right.add(b)
                        differences.extend(saved_differences(missing[a],unexpected[b],object_path(path,missing[a])))
                missing=[v for n,v in enumerate(missing) if n not in paired_left]
                unexpected=[v for n,v in enumerate(unexpected) if n not in paired_right]
            return differences+[{'path':path,'kind':'missing','expected':v} for v in missing]+[{'path':path,'kind':'unexpected','actual':v} for v in unexpected]
        differences=[]
        for index in range(max(len(expected),len(actual))):
            field=path+'['+str(index)+']'
            if index>=len(actual):differences.append({'path':field,'kind':'missing','expected':expected[index]})
            elif index>=len(expected):differences.append({'path':field,'kind':'unexpected','actual':actual[index]})
            else:differences.extend(saved_differences(expected[index],actual[index],field))
        return differences
    return [{'path':path,'kind':'changed','expected':expected,'actual':actual}]


def difference_summary(differences):
    def preview(value):
        if isinstance(value,dict):
            if 'ref' in value:return 'component '+repr(value['ref'])
            if 'source' in value and 'target' in value:
                endpoint=lambda e:str(e.get('ref','junction'))+'.'+str(e.get('pin',''))
                return 'wire '+endpoint(value['source'])+' -> '+endpoint(value['target'])
        return json.dumps(value,ensure_ascii=False)
    def describe(difference):
        value=difference.get('expected',difference.get('actual'))
        if difference['kind']=='changed':
            return difference['path']+': '+preview(difference.get('expected'))+' -> '+preview(difference.get('actual'))
        if isinstance(value,dict) and 'text' in value:
            position=value.get('transform',[])[4:6]
            return difference['path']+': '+difference['kind']+' '+repr(value['text'])+(' at '+str(tuple(position)) if position else '')
        return difference['path']+': '+difference['kind']+' '+preview(value)
    return '; '.join(describe(d) for d in differences)
