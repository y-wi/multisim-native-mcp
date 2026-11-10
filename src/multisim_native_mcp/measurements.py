"""Measurements on native samples, including adaptive time grids."""
import bisect
import cmath
import math
from .waveforms import numeric, signal_index
from .contracts import normalize_measurements


def finite(value):
    value=float(value)
    if not math.isfinite(value):raise ValueError('Measurement values must be finite')
    return value


def interpolate(xs,ys,x):
    if math.isclose(x,xs[0],rel_tol=1e-12,abs_tol=1e-15):x=xs[0]
    if math.isclose(x,xs[-1],rel_tol=1e-12,abs_tol=1e-15):x=xs[-1]
    if not xs[0]<=x<=xs[-1]:raise ValueError('Requested coordinate is outside the waveform')
    i=bisect.bisect_right(xs,x)-1
    if i==len(xs)-1 or xs[i]==x:return ys[i]
    return ys[i]+(ys[i+1]-ys[i])*(x-xs[i])/(xs[i+1]-xs[i])


def series(data,signal,start=None,stop=None):
    index=signal_index(data,signal)
    xs=[numeric(r[0]).real for r in data['rows']];ys=[numeric(r[index]) for r in data['rows']]
    if any(b<a for a,b in zip(xs,xs[1:])):raise ValueError('Waveform axis must be monotonic')
    start=xs[0] if start is None else finite(start);stop=xs[-1] if stop is None else finite(stop)
    if start>stop:raise ValueError('Measurement start exceeds stop')
    first=interpolate(xs,ys,start);last=interpolate(xs,ys,stop)
    pairs=[(start,first)]+[(x,y) for x,y in zip(xs,ys) if start<x<stop]
    if stop!=start:pairs.append((stop,last))
    return [p[0] for p in pairs],[p[1] for p in pairs]


def measure(data,requests):
    requests=normalize_measurements(requests)
    results=[];ids=set()
    for n,request in enumerate(requests):
        metric=request['metric'];signal=request['signal'];identifier=request.get('id',str(n))
        if identifier in ids:raise ValueError('Measurement IDs must be unique')
        ids.add(identifier);unit={'voltage':'V','current':'A'}.get(data['variables'][signal_index(data,signal)].get('kind'),'');extra={}
        xs,ys=series(data,signal,request.get('start'),request.get('stop'))
        if metric in ('gain_db','phase_deg'):
            if not data['complex']:raise ValueError('Gain and phase require an AC plot')
            frequency=finite(request['frequency_hz'])
            rx,ry=series(data,request['reference'])
            denominator=interpolate(rx,ry,frequency)
            if abs(denominator)==0:raise ValueError('Reference signal is zero')
            ratio=interpolate(xs,ys,frequency)/denominator
            if metric=='gain_db' and abs(ratio)==0:raise ValueError('Gain is zero')
            value=20*math.log10(abs(ratio)) if metric=='gain_db' else math.degrees(cmath.phase(ratio))
            unit='dB' if metric=='gain_db' else 'deg';extra={'frequency_hz':frequency,'reference':request['reference']}
        else:
            if data['complex']:raise ValueError('Time-domain measurements require a real plot')
            span=xs[-1]-xs[0]
            if metric=='min':value=min(ys)
            elif metric=='max':value=max(ys)
            elif metric=='peak_to_peak':value=max(ys)-min(ys)
            elif metric=='mean':value=sum((b-a)*(u+v)/2 for a,b,u,v in zip(xs,xs[1:],ys,ys[1:]))/span if span else ys[0]
            elif metric=='rms':value=math.sqrt(sum((b-a)*(u*u+u*v+v*v)/3 for a,b,u,v in zip(xs,xs[1:],ys,ys[1:]))/span) if span else abs(ys[0])
            elif metric in ('frequency','duty_cycle'):
                if span<=0:raise ValueError('Measurement needs a nonzero time window')
                if 'threshold' not in request and min(ys)==max(ys):raise ValueError('Constant signal needs an explicit threshold')
                threshold=finite(request.get('threshold',(min(ys)+max(ys))/2));rising=[];high=0.
                for a,b,u,v in zip(xs,xs[1:],ys,ys[1:]):
                    if u<threshold<=v:rising.append(a+(b-a)*(threshold-u)/(v-u))
                    if u>=threshold and v>=threshold:high+=b-a
                    elif (u>=threshold)!=(v>=threshold):
                        cross=a+(b-a)*(threshold-u)/(v-u)
                        high+=(cross-a) if u>=threshold else (b-cross)
                if metric=='frequency':
                    if len(rising)<2:raise ValueError('Frequency needs at least two rising crossings')
                    value=(len(rising)-1)/(rising[-1]-rising[0]);unit='Hz'
                else:value=high/span;unit='fraction'
            else:raise ValueError('Unsupported measurement: '+metric)
        if not math.isfinite(value):raise ValueError('Nonfinite measurement result')
        results.append({'id':identifier,'metric':metric,'signal':signal,'value':value,'unit':unit,
                        'start':xs[0],'stop':xs[-1],**extra})
    return results
