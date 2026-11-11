"""Result references shared by workflow stages and native edit slices."""
import math


def reference_roots(value):
    if isinstance(value,list):return set().union(*(reference_roots(v) for v in value)) if value else set()
    if not isinstance(value,dict):return set()
    if set(value)=={'$ref'}:return {value['$ref'].split('.')[0]}
    return set().union(*(reference_roots(v) for v in value.values())) if value else set()


def resolve(value, bindings, depth=0):
    if isinstance(value,list):return [resolve(v,bindings,depth+1) for v in value]
    if not isinstance(value,dict):return value
    if set(value)=={'$ref'}:
        path=value['$ref']
        if not isinstance(path,str) or not path:raise ValueError('Invalid result reference')
        result=bindings
        for key in path.split('.'):
            if key in ('__proto__','prototype','constructor'):raise ValueError('Invalid result reference')
            try:result=result[int(key)] if isinstance(result,list) else result[key]
            except (KeyError,IndexError,TypeError,ValueError) as error:
                raise ValueError('Unresolved result reference: '+path) from error
        return result
    for key in ('$add','$sub'):
        if set(value)=={key}:
            terms=resolve(value[key],bindings,depth+1)
            if not isinstance(terms,list) or len(terms)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in terms):
                raise ValueError(key+' requires two finite numbers')
            return terms[0]+terms[1] if key=='$add' else terms[0]-terms[1]
    if any(k in ('__proto__','prototype','constructor') for k in value):raise ValueError('Invalid argument key')
    return {k:resolve(v,bindings,depth+1) for k,v in value.items()}
