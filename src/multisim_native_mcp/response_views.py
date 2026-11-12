"""Compact public responses; full native records stay available on explicit reads."""


def compact_result(value):
    if isinstance(value,list):return [compact_result(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:compact_result(v) for k,v in value.items()}
    parameters=value.get('parameters')
    if isinstance(parameters,list) and parameters and all(isinstance(p,dict) and {'index','value','expression'}<=p.keys() and 'ref' not in p and 'component_ref' not in p for p in parameters):
        useful=[p for p in parameters if p.get('role')=='value' or (p.get('name') and p.get('role')!='model_option')]
        result['parameters']=[compact_result(p) for p in useful]
        result['parameter_count']=len(parameters)
        result['parameters_complete']=len(useful)==len(parameters)
    return result
