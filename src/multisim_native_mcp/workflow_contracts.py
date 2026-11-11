"""Declarative stages for native circuit workflows."""
from typing import Annotated, Literal
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import AcceptanceCriterion
from .settings import SimulationSettingChange,Scalar


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
    project_index: int = 0
    output_path: str | None = None
    isolated_copy: bool = False

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
    local_ref: str | None = None
    id: str | None = None
    pin: str | None = None
    x: int | None = None
    y: int | None = None

    @model_validator(mode='after')
    def selected(self):
        if not (self.ref or self.local_ref or self.id):raise ValueError('Select by ref, local_ref or current id')
        if (self.x is None)!=(self.y is None):raise ValueError('Selector coordinates require x and y')
        return self


class SelectStage(Stage):
    kind: Literal['select']
    components: dict[str,ComponentSelector] = Field(min_length=1)


class EditOperation(Contract):
    operation: Literal['place', 'copy', 'remove', 'move', 'alignPin', 'moveLabel', 'transform', 'route',
                       'autoWire', 'connectTouching', 'wire', 'connectEndpoint', 'reconnect',
                       'splitWire', 'rename', 'setParameter', 'setModelText', 'addText',
                       'labelWire', 'replace', 'createSheet', 'createSubcircuit', 'createPort',
                       'sheetTitle', 'sheetSize', 'repairWireGeometry']
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
    analysis: Literal['op', 'tran', 'ac'] = 'op'
    step: float = Field(default=1e-5, gt=0)
    stop: float = Field(default=.01, gt=0)
    use_initial_conditions: bool = False
    ac_sweep: Literal['lin', 'dec', 'oct'] = 'dec'
    ac_points: int = Field(default=20, ge=1)
    ac_start: float = Field(default=1, gt=0)
    ac_stop: float = Field(default=100000, gt=0)
    persist: bool = False
    use_saved_settings: bool = False

    @model_validator(mode='after')
    def ranges(self):
        if self.persist and self.use_saved_settings:raise ValueError('Choose persist or use_saved_settings')
        if self.step > self.stop:raise ValueError('Require step <= stop')
        if self.ac_start >= self.ac_stop:
            raise ValueError('Require ac_start < ac_stop')
        if self.use_initial_conditions and self.analysis != 'tran':
            raise ValueError('Initial conditions apply to transient analysis')
        return self


class WorkflowMeasurement(Contract):
    id: str = Field(min_length=1)
    metric: Literal['min', 'max', 'mean', 'rms', 'peak_to_peak', 'frequency', 'duty_cycle', 'gain_db', 'phase_deg']
    signal: str | dict
    reference: str | dict | None = None
    frequency_hz: float | None = Field(default=None, gt=0)
    start: float | None = None
    stop: float | None = None
    threshold: float | None = None

    @model_validator(mode='after')
    def ac_fields(self):
        if self.metric in ('gain_db','phase_deg') and (self.reference is None or self.frequency_hz is None):
            raise ValueError('AC measurements require reference and frequency_hz')
        if self.start is not None and self.stop is not None and self.start>self.stop:
            raise ValueError('Measurement start exceeds stop')
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
        if not self.output_path and not self.verify:raise ValueError('Current/source saves always require verification')
        return self


class ExportStage(Stage):
    kind: Literal['export']
    output_path: str
    overwrite: bool = False
    dpi: int = Field(default=144, gt=0)
    fit_content: bool = False
    show_frame: bool = False
    show_grid: bool = False


class Capture(Contract):
    output_path: str
    active_component: str | dict | None = None
    expected_digit: str | None = Field(default=None, pattern=r'^[0-9]$')
    wait_timeout: float | None = Field(default=None, ge=0)


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


WorkflowStage = Annotated[SessionStage | PrepareStage | SelectStage | EditStage | WiringStage | SimulationSettingsStage | SheetDisplayStage | NetlistStage |
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
