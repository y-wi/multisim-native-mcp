"""Declarative stages for native circuit workflows."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import AcceptanceCriterion, MetricName
from .settings import SimulationSettingChange, Scalar


def _validate_region(region: dict[str, int] | None, fit_content: bool):
    if region is not None and fit_content:
        raise ValueError('Choose region or fit_content')
    if region is not None:
        if set(region) != {'left', 'top', 'right', 'bottom'} or any(
            isinstance(v, bool) or not isinstance(v, int) or not -2147483648 <= v <= 2147483647
            for v in region.values()
        ):
            raise ValueError('Region must contain integer left/top/right/bottom sheet coordinates')
        if region['right'] <= region['left'] or region['bottom'] <= region['top']:
            raise ValueError('Export region must have positive size')


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ComponentRequest(Contract):
    name: str = Field(min_length=1)
    family: str = ''
    group: str = ''
    manufacturer: str = ''


class Stage(Contract):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]*$')


class SessionStage(Stage):
    kind: Literal['session']
    mode: Literal['create', 'open', 'attach']
    title: str = 'Circuit'
    source_path: str | None = None
    pid: int | None = None
    project_index: int = Field(default=0, ge=0)
    output_path: str | None = None
    isolated_copy: bool = False

    @field_validator('pid', 'project_index', mode='before')
    @classmethod
    def reject_bool_ints(cls, value):
        if isinstance(value, bool):
            raise ValueError('Integer fields must not be boolean')
        return value

    @model_validator(mode='after')
    def required_target(self):
        if self.mode == 'create' and not self.output_path:raise ValueError('create requires output_path')
        if self.mode == 'open' and not self.source_path:
            raise ValueError('open requires source_path')
        if self.mode == 'attach' and self.pid is None:
            raise ValueError('attach requires pid')
        if self.isolated_copy and self.mode!='open':raise ValueError('isolated_copy applies only to opening an existing circuit')
        return self


class PrepareStage(Stage):
    kind: Literal['prepare']
    components: list[ComponentRequest] = Field(min_length=1)


class ComponentSelector(Contract):
    ref: str | None = None
    component_ref: str | None = None
    local_ref: str | None = None
    id: str | None = None
    pin: str | None = None
    x: int | None = None
    y: int | None = None

    @field_validator('x', 'y', mode='before')
    @classmethod
    def reject_bool_coords(cls, value):
        if isinstance(value, bool):
            raise ValueError('Selector coordinates must be integers')
        return value

    @model_validator(mode='after')
    def selected(self):
        if self.component_ref is not None:
            if self.ref is not None and self.ref != self.component_ref:
                raise ValueError('Conflicting component_ref and ref; provide one value for this selector')
            self.ref = self.component_ref
            self.component_ref = None
        if not (self.ref or self.local_ref or self.id):raise ValueError('Select by ref, local_ref or current id')
        if (self.x is None)!=(self.y is None):raise ValueError('Selector coordinates require x and y')
        return self


class SelectStage(Stage):
    kind: Literal['select']
    components: dict[str,ComponentSelector] = Field(min_length=1)


class SelectSheetStage(Stage):
    kind: Literal['select_sheet']
    index: int | dict | None = Field(default=None)
    title: str | dict | None = None
    sheet_id: str | dict | None = None

    @field_validator('index', mode='before')
    @classmethod
    def reject_bool_index(cls, value):
        if isinstance(value, bool):
            raise ValueError('Sheet index must be an integer')
        return value

    @model_validator(mode='after')
    def valid_selector(self):
        provided = [k for k in ('index', 'title', 'sheet_id') if getattr(self, k) is not None]
        if not provided:
            raise ValueError('SelectSheetStage requires index, title, or sheet_id')
        if len(provided) > 1:
            raise ValueError('Provide only one of index, title, or sheet_id')
        if isinstance(self.index, int) and self.index < 0:
            raise ValueError('Sheet index must be >= 0')
        if isinstance(self.index, dict) and not (len(self.index) == 1 and set(self.index) <= {'$ref', '$add', '$sub'}):
            raise ValueError('Invalid sheet index reference')
        for field_name in ('title', 'sheet_id'):
            val = getattr(self, field_name)
            if isinstance(val, str) and (not val.strip() or '\0' in val):
                raise ValueError(f'{field_name} must be non-empty')
            if isinstance(val, dict) and set(val) != {'$ref'}:
                raise ValueError(f'Invalid {field_name} reference')
        return self


class EditOperation(Contract):
    @model_validator(mode='before')
    @classmethod
    def consistent_arguments(cls,value):
        from .edit_contracts import normalize_edit
        result = normalize_edit(value)
        if isinstance(result, dict) and result.get('operation') in ('fit_sheet', 'translate_sheet'):
            result['operation'] = {'fit_sheet': 'fitSheet', 'translate_sheet': 'translateSheet'}[result['operation']]
        return result

    operation: Literal['place', 'placeInstrument', 'setInstrumentSettings', 'copy', 'remove', 'move', 'alignPin', 'moveLabel', 'transform', 'route',
                       'autoWire', 'connectTouching', 'wire', 'connectEndpoint', 'reconnect',
                       'splitWire', 'rename', 'setParameter', 'setModelText', 'addText', 'updateText', 'deleteText', 'updateSheet', 'moveJunction', 'updatePort',
                       'labelWire', 'replace', 'createSheet', 'createSubcircuit', 'createPort',
                       'sheetTitle', 'sheetSize', 'fitSheet', 'translateSheet', 'repairWireGeometry']
    arguments: dict = Field(default_factory=dict)
    bind: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_]*$')


class EditStage(Stage):
    kind: Literal['edit']
    operations: list[EditOperation] = Field(min_length=1)


class WiringStage(Stage):
    kind: Literal['wiring']
    autowire_on_connection: bool | None = None
    autowire_on_move: bool | None = None
    connect_touching: bool | None = None
    move_connection_limit: int | None = Field(default=None, ge=1)
    persist: bool = False


class SimulationSettingsStage(Stage):
    kind: Literal['simulation_settings']
    scope: Literal['interactive','analysis'] = 'interactive'
    analysis_type: str = 'TRAN'
    changes: list[SimulationSettingChange] = Field(default_factory=list)
    solver_options: dict[str,Scalar] = Field(default_factory=dict)
    expected_revision: str | None = None


class SheetDisplayStage(Stage):
    kind: Literal['sheet_display']
    show_grid: bool | None = None
    show_border: bool | None = None
    show_bounds: bool | None = None


class NetlistStage(Stage):
    kind: Literal['netlist']


class LayoutStage(Stage):
    kind: Literal['layout']
    repair_geometry: bool = False
    require_no_warnings: bool = False


class AnalysisOptions(Contract):
    analysis: Literal['op', 'tran', 'ac', 'dc'] = 'op'
    step: float = Field(default=1e-5, gt=0)
    stop: float = Field(default=.01, gt=0)
    use_initial_conditions: bool = False
    ac_sweep: Literal['lin', 'dec', 'oct'] = 'dec'
    ac_points: int = Field(default=20, ge=1)
    ac_start: float = Field(default=1, gt=0)
    ac_stop: float = Field(default=100000, gt=0)
    dc_source: str | dict | None = None
    dc_start: float | None = None
    dc_stop: float | None = None
    dc_step: float | None = None
    persist: bool = False
    use_saved_settings: bool = False

    @field_validator('step', 'stop', 'ac_points', 'ac_start', 'ac_stop', 'dc_start', 'dc_stop', 'dc_step', mode='before')
    @classmethod
    def reject_bool_numbers(cls, value):
        if isinstance(value, bool):
            raise ValueError('Numeric analysis fields must not be boolean')
        return value

    @model_validator(mode='after')
    def ranges(self):
        if self.persist and self.use_saved_settings:raise ValueError('Choose persist or use_saved_settings')
        if self.step > self.stop:raise ValueError('Require step <= stop')
        if self.ac_start >= self.ac_stop:
            raise ValueError('Require ac_start < ac_stop')
        if self.use_initial_conditions and self.analysis != 'tran':
            raise ValueError('Initial conditions apply to transient analysis')
        if self.analysis == 'dc':
            if self.dc_source is None or (isinstance(self.dc_source, str) and (not self.dc_source.strip() or '\0' in self.dc_source)):
                raise ValueError('DC analysis requires a non-empty dc_source')
            if isinstance(self.dc_source, dict) and set(self.dc_source) != {'$ref'}:
                raise ValueError('Invalid dc_source reference')
            if self.dc_start is None or self.dc_stop is None or self.dc_step is None:
                raise ValueError('DC analysis requires dc_start, dc_stop, and dc_step')
            if self.dc_step == 0 or (self.dc_stop - self.dc_start) * self.dc_step <= 0:
                raise ValueError('DC sweep requires non-zero dc_step moving from dc_start toward dc_stop')
        return self


class WorkflowMeasurement(Contract):
    id: str = Field(min_length=1)
    metric: MetricName
    signal: str | dict
    reference: str | dict | None = None
    frequency_hz: float | None = Field(default=None, gt=0)
    start: float | None = None
    stop: float | None = None
    threshold: float | None = None
    at: float | None = None
    tolerance: float | None = Field(default=None, gt=0, lt=1)
    final_value: float | None = None
    plot_index: int = Field(default=0, ge=0)

    @field_validator('plot_index', mode='before')
    @classmethod
    def reject_bool_plot_index(cls, value):
        if isinstance(value, bool):
            raise ValueError('plot_index must be an integer')
        return value

    @field_validator('start', 'stop', 'threshold', 'frequency_hz', 'at', 'tolerance', 'final_value', mode='before')
    @classmethod
    def reject_bool_numbers(cls, value):
        if isinstance(value, bool):
            raise ValueError('Numeric measurement fields must not be boolean')
        return value

    @model_validator(mode='after')
    def ac_fields(self):
        if isinstance(self.signal, str) and not self.signal.strip():
            raise ValueError('signal must be nonempty')
        if isinstance(self.reference, str) and not self.reference.strip():
            raise ValueError('reference must be nonempty')
        if self.start is not None and self.stop is not None and self.start > self.stop:
            raise ValueError('Measurement start exceeds stop')
        if self.metric in ('gain_db', 'phase_deg') and (self.reference is None or self.frequency_hz is None):
            raise ValueError('AC measurements require reference and frequency_hz')
        if self.metric == 'magnitude' and self.frequency_hz is None:
            raise ValueError('magnitude measurement requires frequency_hz')
        if self.metric in ('bandwidth_3db', 'phase_margin') and self.reference is None:
            raise ValueError(f'{self.metric} measurement requires reference')
        if self.metric == 'bandwidth_3db' and self.threshold is not None and self.threshold <= 0:
            raise ValueError('bandwidth_3db threshold drop in dB must be positive')
        if self.metric == 'value_at' and self.at is None:
            raise ValueError('value_at measurement requires at')
        return self


class AnalysisStage(Stage):
    kind: Literal['analysis']
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    measurements: list[WorkflowMeasurement] = Field(default_factory=list)
    criteria: list[AcceptanceCriterion] = Field(default_factory=list)


class VerifyStage(Stage):
    kind: Literal['verify']
    raw_path: str | dict
    measurements: list[WorkflowMeasurement] = Field(min_length=1)
    criteria: list[AcceptanceCriterion] = Field(min_length=1)


class DecodeDigit(Contract):
    label: str | None = None
    segments: list[str | dict] = Field(min_length=7,max_length=7)
    select: str | dict


class DecodeOptions(Contract):
    start: float | None = None
    stop: float | None = None
    threshold: float = 2.5
    active_high: bool = True
    select_threshold: float = 2.5
    select_active_high: bool = True
    settling: float = Field(default=.00002, ge=0)
    min_dwell: float = Field(default=.00001, gt=0)


class DecodeStage(Stage):
    kind: Literal['decode']
    raw_path: str | dict
    digits: list[DecodeDigit] = Field(min_length=1)
    expected: str | None = None
    options: DecodeOptions = Field(default_factory=DecodeOptions)

    @model_validator(mode='after')
    def digit_count(self):
        if self.expected is not None and len(self.expected)!=len(self.digits):raise ValueError('Expected display length differs from digit count')
        return self


class SaveStage(Stage):
    kind: Literal['save']
    output_path: str | None = None
    save_to_source: bool = False
    overwrite: bool = False
    allow_off_page: bool = False
    verify: bool = True

    @model_validator(mode='after')
    def target(self):
        if self.output_path and self.save_to_source:raise ValueError('Choose output_path or save_to_source=true')
        return self


class ExportStage(Stage):
    kind: Literal['export']
    output_path: str
    overwrite: bool = False
    dpi: int = Field(default=144, gt=0)
    scale: float = Field(default=1.0, gt=0)
    region: dict[str, int] | None = None
    fit_content: bool = False
    padding: int = Field(default=18, ge=0)
    show_frame: bool = False
    show_grid: bool = False

    @field_validator('dpi', 'scale', 'padding', mode='before')
    @classmethod
    def reject_bool_render(cls, value):
        if isinstance(value, bool):
            raise ValueError('Numeric export fields must not be boolean')
        return value

    @model_validator(mode='after')
    def export_bounds(self):
        _validate_region(self.region, self.fit_content)
        return self


class Capture(Contract):
    output_path: str
    active_component: str | dict | None = None
    expected_digit: str | None = Field(default=None, pattern=r'^[0-9A-Fa-f]$')
    wait_timeout: float | None = Field(default=None, ge=0)
    dpi: int = Field(default=144, gt=0)
    scale: float = Field(default=1.0, gt=0)
    region: dict[str, int] | None = None
    fit_content: bool = False
    padding: int = Field(default=18, ge=0)
    show_frame: bool = False
    show_grid: bool = False

    @field_validator('dpi', 'scale', 'padding', 'wait_timeout', mode='before')
    @classmethod
    def reject_bool_capture(cls, value):
        if isinstance(value, bool):
            raise ValueError('Numeric capture fields must not be boolean')
        return value

    @field_validator('expected_digit')
    @classmethod
    def canonical_digit(cls, value):
        return value.upper() if value is not None else None

    @model_validator(mode='after')
    def capture_bounds(self):
        _validate_region(self.region, self.fit_content)
        return self


class InteractiveStage(Stage):
    kind: Literal['interactive']
    time_step: float | None = Field(default=None, gt=0)
    max_time_step: float | None = Field(default=None, gt=0)
    real_time: bool | None = None
    persist: bool = True
    captures: list[Capture] = Field(default_factory=list)
    overwrite: bool = False
    stop_after: bool = True


class CloseStage(Stage):
    kind: Literal['close']
    save_changes: bool = True


WorkflowStage = Annotated[SessionStage | PrepareStage | SelectStage | SelectSheetStage | EditStage | WiringStage | SimulationSettingsStage | SheetDisplayStage | NetlistStage |
                          LayoutStage | AnalysisStage | VerifyStage | DecodeStage | SaveStage |
                          ExportStage | InteractiveStage | CloseStage, Field(discriminator='kind')]


class WorkflowPlan(Contract):
    steps: list[WorkflowStage] = Field(min_length=1)
    expected_revision: str | None = None
    # Retrying a stage is always an explicit caller decision.
    max_runtime: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def ordering(self):
        ids = [s.id for s in self.steps]
        binds = [op.bind for s in self.steps if isinstance(s, EditStage) for op in s.operations if op.bind]
        if len(set(ids + binds)) != len(ids + binds):
            raise ValueError('Stage IDs and operation bind names must be unique')
        sessions = [i for i, s in enumerate(self.steps) if isinstance(s, SessionStage)]
        if sessions and sessions != [0]:
            raise ValueError('A session stage must be the first and only session stage')
        if any(isinstance(s, CloseStage) for s in self.steps[:-1]):
            raise ValueError('close must be the last stage')
        for stage in self.steps:
            if isinstance(stage, (AnalysisStage, VerifyStage)):
                known = {m.id for m in stage.measurements}
                if len(known) != len(stage.measurements) or any(c.id not in known for c in stage.criteria):
                    raise ValueError('Measurement IDs must be unique and criteria must reference them')
        available=set()
        def references(value):
            if isinstance(value,list):
                for v in value:references(v)
            elif isinstance(value,dict):
                if set(value)=={'$ref'}:
                    path=value['$ref']
                    if not isinstance(path,str) or not path or any(p in ('__proto__','prototype','constructor') for p in path.split('.')) or path.split('.')[0] not in available:
                        raise ValueError('Result reference must identify an earlier stage or operation binding: '+str(path))
                else:
                    for v in value.values():references(v)
        for stage in self.steps:
            if isinstance(stage,EditStage):
                for op in stage.operations:
                    references(op.arguments)
                    if op.bind:available.add(op.bind)
            else:references(stage.model_dump())
            available.add(stage.id)
        return self
