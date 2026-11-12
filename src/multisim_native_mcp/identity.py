"""Explicit object-handle changes after a controlled native document refresh."""


def identity_changes(before,after):
    from .workflows import remap_bindings
    def identifiers(state):
        ids=set()
        for c in state.get('components',[]):
            ids.add(c['id']);ids.update(p['id'] for p in c.get('pins',[]));ids.update(l['id'] for l in c.get('labels',[]))
        for w in state.get('wires',[]):
            ids.add(w['id']);ids.update(w[end]['id'] for end in ('source','target'))
        ids.update(t['id'] for t in state.get('texts',[]))
        return ids
    left=before if isinstance(before,list) else [before]
    right=after if isinstance(after,list) else [after]
    targets={s.get('sheet_index',n):s for n,s in enumerate(right)}
    mapped={};unresolved=set()
    for n,state in enumerate(left):
        ids=identifiers(state);target=targets.get(state.get('sheet_index',n),{})
        values=remap_bindings({key:key for key in ids},{**state,'handle_epoch':'before'},{**target,'handle_epoch':'after'})
        for key,value in values.items():
            if isinstance(value,str):
                if key!=value:mapped[key]=value
            else:unresolved.add(key)
    return {'id_map':mapped,'unresolved_ids':sorted(unresolved)}
