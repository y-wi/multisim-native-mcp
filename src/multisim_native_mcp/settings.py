"""Contracts and execution of native document simulation settings."""
import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr


Scalar = StrictBool | StrictInt | StrictFloat | StrictStr | None
PathToken = StrictStr | Annotated[StrictInt, Field(ge=0)]


class SimulationSettingChange(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    path: list[PathToken] = Field(min_length=1)
    value: Scalar


def normalize_setting_changes(changes):
    if changes is None:return []
    if not isinstance(changes,list):raise ValueError('Provide native setting changes as a list')
    normalized=[SimulationSettingChange.model_validate(c).model_dump() for c in changes]
    for change in normalized:
        value=change['value']
        if isinstance(value,float) and not math.isfinite(value):raise ValueError('Setting numbers must be finite')
        if any(isinstance(t,str) and (not t or '\0' in t) for t in change['path']):raise ValueError('Invalid native field path')
    return normalized


def analysis_changes(analysis,step,stop,use_initial_conditions,ac_sweep,ac_points,ac_start,ac_stop):
    if analysis=='op':return []
    fields={'TSTEP':step,'TSTOP':stop,'IC':'uic' if use_initial_conditions else 'auto_ic'} if analysis=='tran' else {
        'VARIATION':ac_sweep,'NPOINTS_PER_VARIATION':ac_points,'FSTART':ac_start,'FSTOP':ac_stop}
    return [{'path':['ANALYSIS',key],'value':value} for key,value in fields.items()]


def validate_analysis_options(analysis,step,stop,use_initial_conditions,ac_sweep='dec',ac_points=20,
                              ac_start=1.,ac_stop=100000.,persist=False,save_to_source=False,use_saved_settings=False):
    if analysis not in ('op','tran','ac'):raise ValueError('analysis must be op, tran or ac')
    numeric=(step,stop,ac_start,ac_stop)
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in numeric):
        raise ValueError('Analysis time and frequency values must be finite numbers')
    if not 0<step<=stop:
        raise ValueError('Require 0 < step <= stop')
    if not isinstance(use_initial_conditions,bool):raise ValueError('use_initial_conditions must be boolean')
    if use_initial_conditions and analysis!='tran':raise ValueError('Initial conditions apply to transient analysis')
    if ac_sweep not in ('lin','dec','oct') or isinstance(ac_points,bool) or not isinstance(ac_points,int) or ac_points<1:
        raise ValueError('Choose lin, dec or oct and a positive integer point count')
    if not 0<ac_start<ac_stop:raise ValueError('Require 0 < AC start < stop')
    if any(not isinstance(v,bool) for v in (persist,save_to_source,use_saved_settings)):raise ValueError('Persistence and saved-settings flags must be boolean')
    if save_to_source and not persist:raise ValueError('save_to_source requires persist=true')
    if persist and use_saved_settings:raise ValueError('Choose explicit run settings with persist or use_saved_settings, not both')


def saved_execution(settings):
    """Validate saved native settings before allowing them to run through the raw-data API."""
    fields={tuple(f['path']):f['value'] for f in settings['fields']}
    analysis=settings['analysis_type']
    if analysis=='TRAN':
        start=fields.get(('ANALYSIS','TSTART'),0);stop=fields[('ANALYSIS','TSTOP')]
        step=fields[('ANALYSIS','TSTEP')]
        if step=='calculate':step=stop/50
        if not all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in (start,stop,step)):
            raise ValueError('Saved transient settings require finite start, stop and step values')
        if not 0<=start<stop or not 0<step<=stop:
            raise ValueError('Saved transient execution requires 0 <= start < stop and 0 < step <= stop')
    elif analysis=='AC':
        start=fields[('ANALYSIS','FSTART')];stop=fields[('ANALYSIS','FSTOP')]
        points=fields[('ANALYSIS','NPOINTS_PER_VARIATION')];sweep=fields[('ANALYSIS','VARIATION')]
        if sweep not in ('lin','dec','oct') or not 0<start<stop or points!=int(points) or points<1:
            raise ValueError('Saved AC execution requires valid sweep, integer points and 0 < start < stop')
    elif analysis!='OP':raise ValueError('Numeric execution supports op, tran and ac')
