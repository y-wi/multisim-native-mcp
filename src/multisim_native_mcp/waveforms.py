"""Multisim ASCII RAW data and numeric exports."""
from __future__ import annotations

import csv
import math
from pathlib import Path


def parse_raw(path: Path) -> dict:
    plots=[];budget=2000000
    with Path(path).open(encoding='utf-8') as stream:
      while True:
        headers={};variables=[];rows=[];nonempty=False
        for line in stream:
            nonempty=nonempty or bool(line.strip())
            if line.strip()=='Variables:':break
            if ':' in line:
                key,value=line.split(':',1);headers[key.strip()]=value.strip()
        if not headers:
            if nonempty:raise ValueError('Unexpected trailing RAW content')
            break
        count=int(headers.get('No. Variables',0));points=int(headers.get('No. Points',0))
        budget-=count*points
        if not (0<count<=10000 and 0<points<=1000000) or budget<0:
            raise RuntimeError('Simulator did not produce a bounded nonempty result plot: '+str(headers))
        for line in stream:
            if line.strip()=='Values:':break
            if not line.strip():continue
            fields=line.split(None,3)
            if len(fields)<3 or int(fields[0])!=len(variables):raise ValueError('Malformed native vector metadata')
            variables.append({'index':int(fields[0]),'native_name':fields[1],'kind':fields[2],
                              'name':fields[3].strip() if len(fields)>3 else fields[1],
                              'unit':{'voltage':'V','current':'A','time':'s','frequency':'Hz'}.get(fields[2])})
        if len(variables)!=count:raise ValueError('Native variable count mismatch')
        complex_plot='complex' in headers.get('Flags','').split()
        digital=headers.get('DigitalFlags')=='Yes'
        if digital:
            for variable in variables:
                if variable['kind']!='time':variable['unit']=None
        for n in range(points):
            if digital:
                line=next((line.strip() for line in stream if line.strip()),None)
                if line is None:raise ValueError('Native sample count mismatch')
                values=[float(v.strip()) for v in line.split(',')]
                if count!=2 or len(values)!=3 or not all(math.isfinite(v) for v in values):
                    raise ValueError('Malformed digital transition record')
                rows.append(values);continue
            row=[]
            for col in range(count):
                line=next((line.strip() for line in stream if line.strip()),None)
                if line is None:raise ValueError('Native sample count mismatch')
                if col==0:
                    fields=line.split(None,1)
                    if len(fields)!=2 or int(fields[0])!=n:raise ValueError('Native sample index mismatch')
                    line=fields[1]
                value=[float(v.strip()) for v in line.split(',')] if complex_plot else float(line)
                if complex_plot and len(value)!=2:raise ValueError('Malformed complex sample')
                if not all(math.isfinite(v) for v in (value if isinstance(value,list) else [value])):
                    raise ValueError('Simulator returned a nonfinite sample')
                row.append(value)
            rows.append(row)
        plots.append({'title':headers.get('Title'),'plot':headers.get('Plotname'),'points':points,
                      'variables':variables,'complex':complex_plot,'digital':digital,'rows':rows,'unit_system':'SI'})
    if not plots or plots[0]['digital']:raise ValueError('No analog result plot')
    return {**plots[0],'additional_plots':plots[1:]}


def numeric(value):
    return complex(*value) if isinstance(value,list) else float(value)


def summarize(data):
    result=[]
    for i,variable in enumerate(data['variables']):
        values=[abs(numeric(row[i])) if data['complex'] else row[i] for row in data['rows']]
        result.append({**variable,'first':data['rows'][0][i],'last':data['rows'][-1][i],
                       'min':min(values),'max':max(values),
                       'summary_domain':'magnitude' if data['complex'] else 'real'})
    return result


def export_csv(data,path):
    with Path(path).open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream)
        writer.writerow([part+(' ['+v['unit']+']' if v.get('unit') else '') for v in data['variables'] for part in
                         ([v['name']+'.real',v['name']+'.imag'] if data['complex'] else [v['name']])])
        for row in data['rows']:
            writer.writerow([part for value in row for part in (value if isinstance(value,list) else [value])])


def signal_index(data,name):
    matches=[v['index'] for v in data['variables'] if name.casefold() in
             (v['name'].casefold(),v['native_name'].casefold())]
    if len(matches)!=1:raise ValueError('Expected one waveform signal: '+name)
    return matches[0]
