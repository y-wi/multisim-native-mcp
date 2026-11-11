"""Native parameter experiments with checkpoint restoration."""
import itertools
from .measurements import finite,measure
from .verification import verify
from .waveforms import parse_raw
from pathlib import Path
from .contracts import normalize_measurements,normalize_criteria


def validate_spec(parameters,analysis,measurements,criteria,objective):
    if not isinstance(parameters,list) or not parameters:raise ValueError('Provide nonempty sweep parameters')
    seen=set();total=1
    for p in parameters:
        key=(p['ref'],p['index'])
        if key in seen:raise ValueError('Duplicate sweep parameter')
        seen.add(key)
        if not isinstance(p['index'],int) or not 0<=p['index']<=2147483647:raise ValueError('Invalid parameter index')
        if not isinstance(p['values'],list) or not p['values']:raise ValueError('Provide nonempty sweep values')
        for value in p['values']:finite(value)
        total*=len(p['values'])
    allowed={'analysis','step','stop','use_initial_conditions','ac_sweep','ac_points','ac_start','ac_stop'}
    if not isinstance(analysis,dict) or set(analysis)-allowed:raise ValueError('Invalid analysis options')
    measurements=normalize_measurements(measurements)
    ids=[m.get('id',str(i)) for i,m in enumerate(measurements)]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate measurement IDs')
    normalize_criteria(criteria,set(ids),allow_empty=True)
    if objective:
        if objective['measurement'] not in ids or objective['goal'] not in ('min','max','target'):raise ValueError('Invalid objective')
        if objective['goal']=='target':finite(objective['target'])
    return total


def run_sweep(host,parameters,analysis,measurements,criteria=None,objective=None,cancel=None,progress=None):
    criteria=criteria or [];total=validate_spec(parameters,analysis,measurements,criteria,objective)
    trials=[];result={'status':'running','total':total,'trials':trials,'best':None,'restored':False}
    with host.lock:
        originals=[]
        for parameter in parameters:
            info=host.call('parameters',{'ref':parameter['ref']})
            if not any(p['index']==parameter['index'] for p in info['parameters']):raise ValueError('Parameter index not found')
            originals.append({'ref':parameter['ref'],**next(p for p in info['parameters'] if p['index']==parameter['index'])})
        checkpoint=host.checkpoint();result['checkpoint']=checkpoint['path']
        try:
            for n,values in enumerate(itertools.product(*(p['values'] for p in parameters))):
                if cancel and cancel.is_set():result['status']='cancelled';break
                trial={'index':n,'parameters':[{'ref':p['ref'],'index':p['index'],'value':v} for p,v in zip(parameters,values)]}
                trials.append(trial)
                try:
                    for parameter in trial['parameters']:
                        host.validate('setParameter',parameter);host.call('setParameter',parameter)
                    native=host.run_analysis(**analysis)
                    trial['analysis']=native
                    trial['measurements']=measure(parse_raw(Path(native['raw_path'])),measurements)
                    trial['acceptance']=verify(trial['measurements'],criteria) if criteria else {'passed':True,'criteria':[]}
                    trial['status']='complete';trial['feasible']=trial['acceptance']['passed']
                    if objective:
                        value=next(m['value'] for m in trial['measurements'] if m['id']==objective['measurement'])
                        trial['score']=-value if objective['goal']=='max' else abs(value-objective['target']) if objective['goal']=='target' else value
                except Exception as error:
                    trial.update(status='cancelled' if cancel and cancel.is_set() else 'failed',error=str(error),feasible=False)
                if progress:progress(result)
            if cancel and cancel.is_set():result['status']='cancelled'
            if result['status']=='running':result['status']='complete' if all(t['status']=='complete' for t in trials) else 'failed'
            feasible=[t for t in trials if t.get('feasible')]
            if feasible:result['best']=(min(feasible,key=lambda t:t['score']) if objective else feasible[0])['index']
        finally:
            try:
                for p in originals:
                    if p.get('value') is not None:host.call('setParameter',{'ref':p['ref'],'index':p['index'],'value':p['value']})
                    if p.get('expression') is not None:host.call('setParameter',{'ref':p['ref'],'index':p['index'],'expression':p['expression']})
                result['restored']=True
            except Exception:
                host.restore(checkpoint);result['restored']=True
            if progress:progress(result)
    return result
