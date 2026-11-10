"""DeepSeek Harness profile configuration."""
from __future__ import annotations

from collections.abc import Mapping
from io import StringIO
import os
from pathlib import Path
import re

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap,CommentedSeq
from ruamel.yaml.error import YAMLError

PLUGIN='@deepseek-ai/dsh-mcp-client'
ENTRY_ID='mcp-multisim-native'


def yaml_parser():
    parser=YAML(typ='rt',pure=True)
    parser.preserve_quotes=True
    parser.width=4096
    return parser


def profile_path(profile='desktop'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',profile):raise ValueError('Invalid DSH profile name')
    home=Path(os.environ.get('DSH_HOME',str(Path.home()/'.dsh'))).expanduser()
    return home/'profiles'/profile/'cordis.patch.yml'


def dsh_entry(entry):
    config={'serverName':'multisim_native','transport':'stdio','command':entry['command'],
            'args':entry['args'],'toolCallTimeoutMs':120000}
    if entry.get('env'):config['env']=entry['env']
    return {'id':ENTRY_ID,'name':PLUGIN,'config':config}


def dsh_document(text,entry):
    parser=yaml_parser()
    try:document=parser.load(text)
    except YAMLError as error:raise ValueError('Invalid DSH patch YAML') from error
    prefix=''
    if document is None:document=CommentedSeq();prefix=text.rstrip()+'\n' if text.strip() else ''
    if not isinstance(document,list):raise ValueError('DSH patch must be a YAML list')
    matches=[]
    def collect(items,inserted):
        for item in items:
            if not isinstance(item,Mapping):raise ValueError('DSH patch entries must be mappings')
            config=item.get('config')
            owned=item.get('id')==ENTRY_ID or (item.get('name')==PLUGIN and isinstance(config,Mapping) and config.get('serverName')=='multisim_native')
            if owned:
                if item.get('name',PLUGIN)!=PLUGIN:raise ValueError('DSH entry ID is used by another plugin')
                if config is not None and not isinstance(config,Mapping):raise ValueError('DSH MCP config must be a mapping')
                matches.append((items,item,inserted))
            if not inserted and 'insert' in item:
                if not isinstance(item['insert'],list):raise ValueError('DSH insert must contain a list')
                collect(item['insert'],True)
    collect(document,False)
    chosen=next((item for _,item,inserted in matches if inserted),matches[0][1] if matches else CommentedMap())
    config=chosen.get('config') or CommentedMap()
    for _,item,_ in matches:
        for key,value in (item.get('config') or {}).items():config[key]=value
    desired=dsh_entry(entry)
    if config.get('env') is not None and not isinstance(config['env'],Mapping):raise ValueError('DSH MCP env must be a mapping')
    environment=CommentedMap(config.get('env') or {})
    environment.update(desired['config'].pop('env',{}))
    config.update(desired['config'])
    if environment:config['env']=environment
    chosen.setdefault('id',ENTRY_ID);chosen['name']=PLUGIN;chosen['config']=config
    chosen.pop('disabled',None)
    inserted=False
    for parent,item,in_insert in reversed(matches):
        if item is chosen and in_insert and not inserted:inserted=True;continue
        index=next(i for i,value in enumerate(parent) if value is item)
        del parent[index]
    if not inserted:document.append(CommentedMap({'insert':CommentedSeq([chosen])}))
    output=StringIO();parser.dump(document,output)
    return prefix+output.getvalue()
