"""The digital twin: wires schedule, weather, sensors, controller, radiator,
ventilation and the heat model into one fixed-step loop.

One step (``dt = step_seconds``, 60 s by default):

    sensors read state -> controller decides -> radiator -> ventilation
    -> StepInputs -> HeatModel.step -> new ZoneState
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .controller import Controller, LegacyController
from .interface import HeatModel, StepInputs, ZoneState
from .params import TwinParams, load_params
from .radiator import Radiator
from .schedule import OccupancySchedule
from .sensors import IdealSensors
from .stub_model import StubHeatModel
from .ventilation import ventilation_flow_L_s
from .weather import SyntheticWeather, Weather


@dataclass(frozen=True)
class Record:
    """One logged step. Values are those the heat model received / returned."""

    time: datetime
    t_air_C: float  # model output at the END of this step
    t_outdoor_C: float
    solar_W_m2: float
    occupants: int
    valve_position: float
    t_supply_C: float
    q_radiator_W: float
    q_internal_W: float
    ventilation_flow_L_s: float


class DigitalTwin:
    def __init__(
        self,
        params: TwinParams,
        model: HeatModel,
        weather: Weather,
        controller: Controller,
        start: datetime,
        initial_t_air_C: float,
    ) -> None:
        self.params = params
        self.model = model
        self.weather = weather
        self.controller = controller
        self.time = start
        self.state = ZoneState(t_air_C=initial_t_air_C)
        self.dt_s = float(params.step_seconds)
        self.schedule = OccupancySchedule(params.occupancy)
        self.sensors = IdealSensors()
        self.radiator = Radiator.from_params(params.heating, params.actuator, params.comfort)

    def internal_gains_W(self, occupants: int) -> float:
        g = self.params.gains
        if occupants <= 0:
            return 0.0
        adults = self.params.occupancy.teachers
        pupils = max(0, occupants - adults)
        lighting = g.lighting_W_m2 * self.params.zone.floor_area_m2
        return pupils * g.pupil_W + adults * g.adult_W + lighting + g.equipment_W

    def step(self) -> Record:
        p = self.params
        sample = self.weather.at(self.time)
        occupants = self.schedule.occupants(self.time)

        meas = self.sensors.read(self.state, sample, occupants)
        action = self.controller.act(self.time, meas)

        q_rad = self.radiator.step(
            action.valve_cmd, action.t_supply_C, self.state.t_air_C, self.dt_s
        )
        flow = ventilation_flow_L_s(
            p.ventilation,
            p.zone.floor_area_m2,
            occupants,
            action.ventilation_on,
            self.state.t_air_C,
        )
        q_int = self.internal_gains_W(occupants)

        inputs = StepInputs(
            t_outdoor_C=sample.t_outdoor_C,
            solar_irradiance_W_m2=sample.solar_irradiance_W_m2,
            occupants=occupants,
            q_internal_W=q_int,
            q_radiator_W=q_rad,
            ventilation_flow_L_s=flow,
            supply_air_temp_C=sample.t_outdoor_C,
            heat_recovery_eff=p.ventilation.heat_recovery_eff,
        )
        self.state = self.model.step(self.state, inputs, self.dt_s)

        rec = Record(
            time=self.time,
            t_air_C=self.state.t_air_C,
            t_outdoor_C=sample.t_outdoor_C,
            solar_W_m2=sample.solar_irradiance_W_m2,
            occupants=occupants,
            valve_position=self.radiator.valve_position,
            t_supply_C=action.t_supply_C,
            q_radiator_W=q_rad,
            q_internal_W=q_int,
            ventilation_flow_L_s=flow,
        )
        self.time += timedelta(seconds=self.dt_s)
        return rec

    def run(self, duration: timedelta) -> list[Record]:
        n = int(duration.total_seconds() // self.dt_s)
        return [self.step() for _ in range(n)]


def build_default_twin(
    start: datetime | None = None,
    model: HeatModel | None = None,
    weather: Weather | None = None,
    controller: Controller | None = None,
    initial_t_air_C: float = 21.0,
) -> DigitalTwin:
    """Default wiring: params.yaml, stub heat model, synthetic weather, legacy controller."""
    params = load_params()
    return DigitalTwin(
        params=params,
        model=model or StubHeatModel(),
        weather=weather or SyntheticWeather(),
        controller=controller or LegacyController(params.heating, params.comfort),
        start=start or datetime(2026, 10, 12, 0, 0),  # a Monday
        initial_t_air_C=initial_t_air_C,
    )
