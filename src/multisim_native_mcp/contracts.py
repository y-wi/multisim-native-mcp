"""Typed waveform requests shared by tools and persisted experiments."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class MeasurementRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str | None = Field(default=None, min_length=1)
    metric: Literal['min', 'max', 'mean', 'rms', 'peak_to_peak', 'frequency', 'duty_cycle', 'gain_db', 'phase_deg']
    signal: str = Field(min_length=1)
    start: float | None = None
    stop: float | None = None
    threshold: float | None = None
    reference: str | None = None
    frequency_hz: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def ac_fields(self):
        if self.metric in ('gain_db', 'phase_deg') and (not self.reference or self.frequency_hz is None):
            raise ValueError('AC measurements require reference and frequency_hz')
        return self


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(min_length=1, description='ID of the measurement to check; legacy measurement is also accepted.')
    min: float | None = None
    max: float | None = None
    target: float | None = None
    absolute_tolerance: float | None = Field(default=None, ge=0)
    relative_tolerance: float | None = Field(default=None, ge=0)

    @model_validator(mode='before')
    @classmethod
    def legacy_key(cls, value):
        if isinstance(value, dict) and 'measurement' in value:
            value = dict(value)
            legacy = value.pop('measurement')
            if 'id' in value and value['id'] != legacy:
                raise ValueError('id and measurement must refer to the same measurement')
            value['id'] = legacy
        return value

    @model_validator(mode='after')
    def bounds(self):
        if self.min is None and self.max is None and self.target is None:
            raise ValueError('Criterion needs min, max or target')
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError('Criterion min must not exceed max')
        return self


def normalize_requests(values, model, field, allow_empty=False):
    if not isinstance(values, list) or (not values and not allow_empty):
        raise ValueError(f'{field}: provide {"0" if allow_empty else "1"} or more entries')
    result = []
    for index, item in enumerate(values):
        try:
            parsed = item if isinstance(item, model) else model.model_validate(item)
        except ValidationError as error:
            messages = []
            for issue in error.errors(include_url=False):
                location = '.'.join(str(p) for p in issue['loc'])
                messages.append(f'{field}[{index}]' + ('.' + location if location else '') + ': ' + issue['msg'])
            raise ValueError('; '.join(messages)) from error
        entry = parsed.model_dump(exclude_none=True)
        if model is MeasurementRequest:
            entry.setdefault('id', str(index))
        else:
            entry['measurement'] = entry['id']
        result.append(entry)
    if model is MeasurementRequest and len({m['id'] for m in result}) != len(result):
        raise ValueError('measurements: IDs must be unique')
    return result


def normalize_measurements(values):
    return normalize_requests(values, MeasurementRequest, 'measurements')


def normalize_criteria(values, ids=None, allow_empty=False):
    result = normalize_requests(values, AcceptanceCriterion, 'criteria', allow_empty)
    if ids is not None:
        for index, criterion in enumerate(result):
            if criterion['id'] not in ids:
                raise ValueError(f'criteria[{index}].id: unknown measurement {criterion["id"]!r}; expected one of {sorted(ids)}')
    return result
