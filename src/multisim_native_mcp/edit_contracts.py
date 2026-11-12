"""Shared spelling for standalone tools, edit batches and workflow arguments."""

OPERATIONS={
    'place_component':'place','copy_component':'copy','delete_object':'remove',
    'move_component':'move','move_component_label':'moveLabel','transform_component':'transform',
    'route_wire':'route','auto_route_wire':'autoWire','connect_touching':'connectTouching',
    'connect_pins':'wire','connect_endpoints':'connectEndpoint','reconnect_wire':'reconnect',
    'split_wire':'splitWire','rename_component':'rename','set_parameter':'setParameter',
    'set_model_text':'setModelText','add_text':'addText','update_text':'updateText',
    'delete_text':'deleteText','label_wire':'labelWire','replace_component':'replace',
    'create_sheet':'createSheet','create_subcircuit':'createSubcircuit',
    'create_hierarchical_port':'createPort','update_hierarchical_port':'updatePort',
    'update_sheet':'updateSheet','move_junction':'moveJunction','repair_wire_geometry':'repairWireGeometry',
}
COMPONENT_OPERATIONS={'copy','remove','move','alignPin','moveLabel','transform','setParameter',
                      'setModelText','rename','replace'}
WIRE_OPERATIONS={'route','autoWire','reconnect','splitWire','labelWire'}
OBJECT_OPERATIONS=WIRE_OPERATIONS|{'remove','updateText','deleteText','updatePort','moveJunction'}


def rename_field(arguments,alias,key):
    if alias in arguments:
        if key in arguments and arguments[key]!=arguments[alias]:
            raise ValueError(f'Conflicting {alias} and {key}; provide one value for this selector')
        arguments[key]=arguments.pop(alias)


def normalize_edit(operation):
    if not isinstance(operation,dict):raise ValueError('Each edit requires operation and arguments')
    result=dict(operation);name=result.get('operation','')
    if not isinstance(name,str):raise ValueError('Edit operation must be a string')
    name=name.removeprefix('native_') if isinstance(name,str) else name
    name=OPERATIONS.get(name,name);result['operation']=name
    arguments=result.get('arguments',{})
    if not isinstance(arguments,dict):raise ValueError(f'{name}: arguments must be an object')
    args=dict(arguments)
    if name in COMPONENT_OPERATIONS:rename_field(args,'component_ref','ref')
    if name in OBJECT_OPERATIONS:rename_field(args,'object_id','id')
    if name in WIRE_OPERATIONS:rename_field(args,'wire_id','id')
    if name=='moveJunction':rename_field(args,'junction_id','id')
    if name in ('place','createSubcircuit'):rename_field(args,'reference','ref')
    if name=='transform':rename_field(args,'mirror_axis','axis')
    if name=='connectTouching':rename_field(args,'component_refs','refs')
    if name=='autoWire' and args.get('engine','native')!='native':
        raise ValueError('Batch autoWire uses the native router; use native_auto_route_wire(engine="obstacle") for obstacle planning')
    if name in ('wire','connectEndpoint','reconnect'):
        for end in ('source','target'):
            if isinstance(args.get(end),dict):
                args[end]=dict(args[end]);rename_field(args[end],'component_ref','ref')
            if end+'_ref' in args or end+'_pin' in args:
                if end+'_ref' not in args or end+'_pin' not in args:
                    raise ValueError(f'{name}: {end}_ref and {end}_pin must be provided together')
                endpoint={'ref':args.pop(end+'_ref'),'pin':args.pop(end+'_pin')}
                if end in args and args[end]!=endpoint:raise ValueError(f'{name}: conflicting {end} endpoint selectors')
                args[end]=endpoint
    if name=='remove' and bool(args.get('id'))==bool(args.get('ref')):
        raise ValueError('remove requires one object_id/id or component_ref/ref')
    result['arguments']=args
    return result
