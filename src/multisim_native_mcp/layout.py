"""Native geometry checks and orthogonal obstacle routing."""
import heapq
import itertools


def intersects(a,b,r):
    if a['x']==b['x']:
        return r['left']<a['x']<r['right'] and max(min(a['y'],b['y']),r['top'])<min(max(a['y'],b['y']),r['bottom'])
    if a['y']==b['y']:
        return r['top']<a['y']<r['bottom'] and max(min(a['x'],b['x']),r['left'])<min(max(a['x'],b['x']),r['right'])
    # Slab intersection for diagonal routes.
    lo,hi=0.,1.
    for axis,l,h in [('x','left','right'),('y','top','bottom')]:
        delta=b[axis]-a[axis]
        if not delta:
            if not r[l]<a[axis]<r[h]:return False
        else:
            p,q=sorted(((r[l]-a[axis])/delta,(r[h]-a[axis])/delta));lo=max(lo,p);hi=min(hi,q)
    return lo<hi


def check_layout(components,wires):
    pins={p['id']:p for c in components for p in c['pins']};issues=[]
    for a,b in itertools.combinations(components,2):
        x,y=a['bounds'],b['bounds']
        if max(x['left'],y['left'])<min(x['right'],y['right']) and max(x['top'],y['top'])<min(x['bottom'],y['bottom']):
            issues.append({'kind':'component_overlap','severity':'warning','components':[a['ref'],b['ref']]})
    for wire in wires:
        points=wire['points']
        if len(points)<2:
            issues.append({'kind':'missing_route','severity':'error','wire':wire['id']});continue
        for end,index in [('source',0),('target',-1)]:
            endpoint=pins.get(wire[end]['id'],wire[end])
            if all(k in endpoint for k in ('x','y')) and any(endpoint[k]!=points[index][k] for k in ('x','y')):
                issues.append({'kind':'detached_endpoint','severity':'error','wire':wire['id'],'end':end})
        if wire.get('has_pen') is False:issues.append({'kind':'invisible_wire','severity':'error','wire':wire['id']})
        for n,(a,b) in enumerate(zip(points,points[1:])):
            if a['x']!=b['x'] and a['y']!=b['y']:
                issues.append({'kind':'diagonal_segment','severity':'warning','wire':wire['id'],'segment':n})
            for c in components:
                if c['ref'] in (wire['source'].get('ref'),wire['target'].get('ref')):continue
                if intersects(a,b,c['bounds']):issues.append({'kind':'wire_crosses_component','severity':'warning','wire':wire['id'],'segment':n,'component':c['ref']})
    errors=sum(i['severity']=='error' for i in issues)
    return {'passed':not issues,'errors':errors,'warnings':len(issues)-errors,'issues':issues,
            'component_count':len(components),'wire_count':len(wires)}


def orthogonal_path(start,end,obstacles,turn_cost=9):
    xs=sorted({start['x'],end['x'],*(r[k] for r in obstacles for k in ('left','right'))})
    ys=sorted({start['y'],end['y'],*(r[k] for r in obstacles for k in ('top','bottom'))})
    if len(xs)*len(ys)>100000:raise ValueError('Routing grid exceeds 100000 nodes')
    def point(x,y):return {'x':xs[x],'y':ys[y]}
    def inside(p):return any(r['left']<p['x']<r['right'] and r['top']<p['y']<r['bottom'] for r in obstacles)
    if inside(start) or inside(end):raise ValueError('Route endpoint lies inside an obstacle')
    source=(xs.index(start['x']),ys.index(start['y']),-1);target=(xs.index(end['x']),ys.index(end['y']))
    distance={source:0};parent={};queue=[(0,0,source)];visited=0
    while queue:
        _,cost,current=heapq.heappop(queue)
        if cost!=distance[current]:continue
        visited+=1
        if visited>300000:raise ValueError('Routing search exceeds 300000 states')
        x,y,direction=current
        if (x,y)==target:
            route=[]
            while True:
                route.append(point(current[0],current[1]))
                if current==source:break
                current=parent[current]
            return simplify(list(reversed(route)))
        a=point(x,y)
        for nx,ny,nd in [(x-1,y,0),(x+1,y,0),(x,y-1,1),(x,y+1,1)]:
            if not (0<=nx<len(xs) and 0<=ny<len(ys)):continue
            b=point(nx,ny)
            if inside(b) or any(intersects(a,b,r) for r in obstacles):continue
            new=(nx,ny,nd);value=cost+abs(a['x']-b['x'])+abs(a['y']-b['y'])+(turn_cost if direction not in (-1,nd) else 0)
            if value<distance.get(new,float('inf')):
                distance[new]=value;parent[new]=current
                heuristic=abs(b['x']-end['x'])+abs(b['y']-end['y'])
                heapq.heappush(queue,(value+heuristic,value,new))
    raise ValueError('No obstacle-free orthogonal path')


def simplify(points):
    result=[]
    for p in points:
        if result and p==result[-1]:continue
        if len(result)>1 and ((result[-2]['x']==result[-1]['x']==p['x']) or (result[-2]['y']==result[-1]['y']==p['y'])):result.pop()
        result.append(p)
    return result


def plan_wire(components,wire,clearance=9):
    if not isinstance(clearance,int) or not 0<=clearance<=100:raise ValueError('Clearance must be 0 to 100 native units')
    obstacles=[{k:v+(-clearance if k in ('left','top') else clearance) for k,v in c['bounds'].items()} for c in components]
    lookup={c['ref']:i for i,c in enumerate(components)}
    leads=[]
    for end,index in [('source',0),('target',-1)]:
        p=dict(wire['points'][index]);owner=lookup.get(wire[end].get('ref'))
        if owner is None:leads.append((p,p));continue
        r=obstacles[owner]
        candidates=[{'x':r['left'],'y':p['y']},{'x':r['right'],'y':p['y']},
                    {'x':p['x'],'y':r['top']},{'x':p['x'],'y':r['bottom']}]
        escape=min(candidates,key=lambda q:abs(q['x']-p['x'])+abs(q['y']-p['y']))
        if any(intersects(p,escape,o) for i,o in enumerate(obstacles) if i!=owner):raise ValueError('Pin escape is blocked by another component')
        leads.append((p,escape))
    middle=orthogonal_path(leads[0][1],leads[1][1],obstacles)
    points=simplify([leads[0][0],*middle,leads[1][0]])
    return {'wire_id':wire['id'],'points':points,'clearance':clearance,
            'length':sum(abs(a['x']-b['x'])+abs(a['y']-b['y']) for a,b in zip(points,points[1:]))}
