"""Standalone bilingual experiment reports generated from saved native results."""
import base64
import csv
import html
import json
import math
import shutil
from pathlib import Path
from .waveforms import parse_raw,numeric,signal_index


def waveform_svg(data,signals):
    if not signals:raise ValueError('Choose waveform signals')
    width=960;height=220*len(signals)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
         '<rect width="100%" height="100%" fill="white"/>']
    axis_kind=data['variables'][0].get('kind')
    axis=[numeric(r[0]).real for r in data['rows']] if axis_kind in ('frequency','time') else list(range(len(data['rows'])))
    log=data['complex'] and min(axis)>0
    xs=[math.log10(x) if log else x for x in axis];span=xs[-1]-xs[0] or 1
    for n,signal in enumerate(signals):
        index=signal_index(data,signal);ys=[abs(numeric(r[index])) if data['complex'] else r[index] for r in data['rows']]
        low=min(ys);high=max(ys);scale=high-low or 1;top=n*220+36
        points=[]
        # Retain each bucket's extrema so brief transitions remain visible.
        stride=max(1,len(xs)//400)
        selected={0,len(xs)-1}
        for i in range(0,len(xs),stride):
            bucket=range(i,min(i+stride,len(xs)))
            selected.update((min(bucket,key=ys.__getitem__),max(bucket,key=ys.__getitem__)))
        for i in sorted(selected):points.append(f'{80+830*(xs[i]-xs[0])/span:.2f},{top+140-140*(ys[i]-low)/scale:.2f}')
        label=html.escape(signal+(' | magnitude' if data['complex'] else ''))
        svg.extend([f'<text x="80" y="{top-12}" font-family="sans-serif" font-size="16">{label}</text>',
            f'<path d="M80 {top}v140h830" fill="none" stroke="#aaa"/>',
            f'<polyline points="{" ".join(points)}" fill="none" stroke="#1764c0" stroke-width="1.5"/>',
            f'<text x="8" y="{top+12}" font-size="12">{high:.5g}</text>',
            f'<text x="8" y="{top+140}" font-size="12">{low:.5g}</text>',
            f'<text x="80" y="{top+164}" font-size="12">{axis[0]:.6g}</text>',
            f'<text x="760" y="{top+164}" font-size="12">{axis[-1]:.6g} {"Hz (log)" if log else "s" if axis_kind=="time" else "sample"}</text>'])
    return ''.join(svg)+ '</svg>'


def export_report(record,directory,language='zh',title=None,signals=None,overwrite=False):
    if language not in ('zh','en'):raise ValueError('Choose zh or en')
    out=Path(directory)
    if not out.is_absolute() or not out.is_dir():raise ValueError('Choose an existing absolute output directory')
    trials=record.get('result',{}).get('trials',[]);complete=[t for t in trials if t.get('status')=='complete']
    if not complete:raise ValueError('Experiment has no completed numeric trial')
    best=record['result'].get('best');trial=next((t for t in complete if t['index']==best),complete[0])
    data=parse_raw(Path(trial['analysis']['raw_path']))
    offset=1 if data['variables'][0].get('kind') in ('frequency','time') else 0
    signals=signals or [v['name'] for v in data['variables'][offset:offset+3]]
    svg=waveform_svg(data,signals)
    image=Path(record['schematic_path']);png=image.read_bytes()
    names=['report.html','report.md','measurements.csv','circuit.png','waveforms.svg']
    if not overwrite and any((out/n).exists() for n in names):raise FileExistsError('Report output already exists')
    zh=language=='zh';title=title or ('电路实验报告' if zh else 'Circuit experiment report')
    labels=['实验','状态','候选','参数','指标','数值','单位','候选可行'] if zh else ['Experiment','Status','Trial','Parameters','Metric','Value','Unit','Feasible']
    rows=[]
    for t in trials:
        parameters=', '.join(f"{p['ref']}[{p['index']}]={p['value']:g}" for p in t['parameters'])
        for m in t.get('measurements',[]):
            rows.append([str(t['index']),parameters,m['id'],f"{m['value']:.10g}",m['unit'],str(t.get('feasible',False))])
        if t.get('error'):rows.append([str(t['index']),parameters,'error',t['error'],'','False'])
    headings=labels[2:]
    table='<table><thead><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in headings)+'</tr></thead><tbody>'
    table+=''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
    acceptance=trial.get('acceptance',{})
    criteria=acceptance.get('criteria',[])
    if criteria:
        criteria_rows=[]
        for c in criteria:
            condition=[]
            if 'min' in c:condition.append('≥ '+str(c['min']))
            if 'max' in c:condition.append('≤ '+str(c['max']))
            if 'target' in c:condition.append(str(c['target'])+' ± '+str(max(c.get('absolute_tolerance',0),abs(c['target'])*c.get('relative_tolerance',0))))
            criteria_rows.append([c['measurement'],', '.join(condition),str(c['value']),('通过' if c['passed'] else '失败') if zh else ('Pass' if c['passed'] else 'Fail')])
        criteria_head=['指标','要求','实测值','结果'] if zh else ['Metric','Requirement','Measured','Result']
        details='<table><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in criteria_head)+'</tr>'
        details+=''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in criteria_rows)+'</table>'
        acceptance_md='| '+' | '.join(criteria_head)+' |\n| --- | --- | --- | --- |\n'
        acceptance_md+=''.join('| '+' | '.join(row)+' |\n' for row in criteria_rows)
    else:
        text='未设置验收条件。' if zh else 'No acceptance criteria configured.'
        details='<p>'+text+'</p>';acceptance_md=text+'\n'
    caption='验收结果' if zh else 'Acceptance results'
    document=f'''<!doctype html><html lang="{'zh-CN' if zh else 'en'}"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#17212f}}img,svg{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd4df;padding:8px;text-align:left}}th{{background:#edf2f8}}pre{{white-space:pre-wrap}}</style>
<h1>{html.escape(title)}</h1><p>{labels[0]}: {record['id']} · {labels[1]}: {html.escape(record['status'])}</p>
<h2>{'电路' if zh else 'Circuit'}</h2><img alt="Circuit" src="data:image/png;base64,{base64.b64encode(png).decode()}">
<h2>{'波形' if zh else 'Waveforms'}</h2>{svg}<h2>{'测量结果' if zh else 'Measurements'}</h2>{table}
<h2>{caption}</h2>{details}</html>'''
    def md(value):return str(value).replace('|','\\|').replace('\n',' ')
    markdown=f'# {title}\n\n{labels[0]}: `{record["id"]}`\n\n{labels[1]}: {record["status"]}\n\n![Circuit](circuit.png)\n\n![Waveforms](waveforms.svg)\n\n'
    markdown+='| '+' | '.join(headings)+' |\n| '+' | '.join(['---']*len(headings))+' |\n'
    markdown+=''.join('| '+' | '.join(md(c) for c in row)+' |\n' for row in rows)
    markdown+=f'\n## {caption}\n\n{acceptance_md}'
    (out/'report.html').write_text(document,encoding='utf-8');(out/'report.md').write_text(markdown,encoding='utf-8')
    (out/'circuit.png').write_bytes(png);(out/'waveforms.svg').write_text(svg,encoding='utf-8')
    with (out/'measurements.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream);writer.writerow(headings);writer.writerows(rows)
    return {'experiment_id':record['id'],'trial_index':trial['index'],'files':{n:str((out/n).resolve()) for n in names}}
