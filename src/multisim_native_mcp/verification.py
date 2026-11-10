"""Numeric acceptance criteria and multiplexed seven-segment decoding."""
import collections
from .measurements import finite
from .waveforms import signal_index


SEGMENTS={'1111110':'0','0110000':'1','1101101':'2','1111001':'3','0110011':'4',
          '1011011':'5','1011111':'6','1110000':'7','1111111':'8','1111011':'9',
          '1110111':'A','0011111':'b','1001110':'C','0111101':'d','1001111':'E','1000111':'F'}


def verify(measurements,criteria):
    if not criteria or len(criteria)>100:raise ValueError('Provide 1 to 100 acceptance criteria')
    values={m['id']:m['value'] for m in measurements};results=[]
    for criterion in criteria:
        key=criterion['measurement']
        if key not in values:raise ValueError('Unknown measurement: '+key)
        value=finite(values[key]);checks=[]
        for bound in ('min','max'):
            if bound in criterion:
                b=finite(criterion[bound]);checks.append(value>=b if bound=='min' else value<=b)
        if 'target' in criterion:
            target=finite(criterion['target']);absolute=finite(criterion.get('absolute_tolerance',0));relative=finite(criterion.get('relative_tolerance',0))
            if absolute<0 or relative<0:raise ValueError('Tolerances must be nonnegative')
            checks.append(abs(value-target)<=max(absolute,abs(target)*relative))
        if not checks:raise ValueError('Criterion needs min, max or target')
        results.append({**criterion,'value':value,'passed':all(checks)})
    return {'passed':all(c['passed'] for c in results),'criteria':results}


def decode_display(data,digits,expected=None,start=None,stop=None,threshold=2.5,active_high=True,
                   select_threshold=2.5,select_active_high=True,settling=0.00002,min_dwell=0.00001):
    if data['complex']:raise ValueError('Display decoding needs transient samples')
    if not 1<=len(digits)<=16:raise ValueError('Provide 1 to 16 digits in display order')
    if expected is not None and len(expected)!=len(digits):raise ValueError('Expected display length differs from digit count')
    threshold=finite(threshold);select_threshold=finite(select_threshold)
    settling=finite(settling);min_dwell=finite(min_dwell)
    if settling<0 or min_dwell<=0:raise ValueError('Require settling >= 0 and min_dwell > 0')
    begin=data['rows'][0][0] if start is None else finite(start);end=data['rows'][-1][0] if stop is None else finite(stop)
    if not data['rows'][0][0]<=begin<end<=data['rows'][-1][0]:raise ValueError('Invalid display time window')
    indices=[]
    for digit in digits:
        if len(digit['segments'])!=7:raise ValueError('Segments must be ordered a,b,c,d,e,f,g')
        indices.append(([signal_index(data,s) for s in digit['segments']],signal_index(data,digit['select'])))
    duration=[collections.Counter() for _ in digits];visits=[0]*len(digits)
    previous=None;changed=begin;conflict=0.;blank=0.
    for row,next_row in zip(data['rows'],data['rows'][1:]):
        a=max(begin,row[0]);b=min(end,next_row[0])
        if a>=b:continue
        selected=tuple(i for i,(_,sel) in enumerate(indices) if (row[sel]>=select_threshold)==select_active_high)
        if selected!=previous:previous=selected;changed=a
        a=max(a,changed+settling)
        if a>=b:continue
        if len(selected)>1:conflict+=b-a;continue
        if not selected:blank+=b-a;continue
        digit=selected[0];segments=indices[digit][0]
        bits=''.join('1' if (row[i]>=threshold)==active_high else '0' for i in segments)
        duration[digit][SEGMENTS.get(bits,'unknown:'+bits)]+=b-a
        visits[digit]+=1
    result=[]
    for i,hist in enumerate(duration):
        observed={k:v for k,v in hist.items() if v>=min_dwell}
        best=max(observed,key=observed.get) if observed else None
        passed=bool(observed) and len(observed)==1 and not best.startswith('unknown:')
        if expected is not None:passed=passed and best==expected[i]
        result.append({'label':digits[i].get('label',str(i)),'decoded':best,'observed_seconds':dict(hist),
                       'stable_seconds':sum(observed.values()),'samples':visits[i],'passed':passed})
    return {'decoded':''.join(d['decoded'] if d['decoded'] and len(d['decoded'])==1 else '?' for d in result),
            'expected':expected,'passed':all(d['passed'] for d in result) and conflict<min_dwell,
            'digits':result,'conflict_seconds':conflict,'blank_seconds':blank,'start':begin,'stop':end}
