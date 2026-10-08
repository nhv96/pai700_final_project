"""Typed view of config/params.yaml.

The YAML mixes ``typical:`` and ``value:`` keys and carries confidence metadata.
This loader reads the number the twin should use (``typical`` first, then ``value``)
and ignores the metadata. Confidence levels stay in the YAML, which remains the
source of truth for where each number came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[1] / "config" / "params.yaml"

# params.yaml leaves the TRV full-stroke time as null ("keep configurable").
DEFAULT_VALVE_FULL_STROKE_S = 60.0


def _val(node: Any) -> Any:
    """Return the usable number from a params node (``typical`` first, then ``value``)."""
    if isinstance(node, dict):
        for key in ("typical", "value"):
            if node.get(key) is not None:
                return node[key]
    raise KeyError(f"no usable 'typical' or 'value' in {node!r}")


def _opt(node: Any, default: Any) -> Any:
    try:
        return _val(node)
    except KeyError:
        return default


@dataclass(frozen=True)
class ZoneParams:
    floor_area_m2: float
    ceiling_height_m: float
    window_area_m2: float
    window_orientation: str

    @property
    def volume_m3(self) -> float:
        return self.floor_area_m2 * self.ceiling_height_m


@dataclass(frozen=True)
class ScheduleBlock:
    start: time
    end: time
    occupancy_fraction: float


@dataclass(frozen=True)
class OccupancyParams:
    pupils: int
    teachers: int
    blocks: tuple[ScheduleBlock, ...]
    weekend_occupancy: float


@dataclass(frozen=True)
class GainParams:
    pupil_W: float
    adult_W: float
    lighting_W_m2: float
    equipment_W: float


@dataclass(frozen=True)
class VentilationParams:
    per_person_L_s: float
    per_area_L_s_m2: float
    heat_recovery_eff: float
    purge_trigger_C: float
    purge_flow_multiplier: float


@dataclass(frozen=True)
class ComfortParams:
    setpoint_C: float
    lower_limit_C: float
    discomfort_above_C: float
    setback_unoccupied_C: float


@dataclass(frozen=True)
class HeatingParams:
    design_supply_C: float  # at design outdoor temperature
    design_return_C: float
    design_outdoor_C: float
    mild_supply_C: float  # supply temperature cap when outdoor >= 5 C
    radiator_rated_W: float
    radiator_response_s: float


@dataclass(frozen=True)
class ActuatorParams:
    valve_full_stroke_s: float


@dataclass(frozen=True)
class TwinParams:
    step_seconds: int
    zone: ZoneParams
    occupancy: OccupancyParams
    gains: GainParams
    ventilation: VentilationParams
    comfort: ComfortParams
    heating: HeatingParams
    actuator: ActuatorParams


def _parse_blocks(raw: list[dict[str, Any]]) -> tuple[ScheduleBlock, ...]:
    return tuple(
        ScheduleBlock(
            start=time.fromisoformat(str(b["start"])),
            end=time.fromisoformat(str(b["end"])),
            occupancy_fraction=float(b["occupancy_fraction"]),
        )
        for b in raw
    )


def params_from_dict(raw: dict[str, Any]) -> TwinParams:
    zone = raw["zone"]
    occ = raw["occupancy"]
    gains = raw["internal_gains"]
    vent = raw["ventilation"]
    comfort = raw["comfort"]
    heat = raw["heating_system"]
    act = raw["actuators"]["smart_trv"]

    return TwinParams(
        step_seconds=int(raw["meta"]["step_seconds"]),
        zone=ZoneParams(
            floor_area_m2=float(_val(zone["floor_area_m2"])),
            ceiling_height_m=float(_val(zone["ceiling_height_m"])),
            window_area_m2=float(_val(zone["window_area_m2"])),
            window_orientation=str(_val(zone["window_orientation"])),
        ),
        occupancy=OccupancyParams(
            pupils=int(_val(occ["pupils_per_class"])),
            teachers=int(_val(occ["teachers_per_class"])),
            blocks=_parse_blocks(occ["weekday_schedule"]["blocks"]),
            weekend_occupancy=float(_val(occ["weekend_and_holiday_occupancy"])),
        ),
        gains=GainParams(
            pupil_W=float(_val(gains["sensible_heat_per_pupil_W"])),
            adult_W=float(_val(gains["sensible_heat_per_adult_W"])),
            lighting_W_m2=float(_val(gains["lighting_W_per_m2"])),
            equipment_W=float(_val(gains["classroom_equipment_W"])),
        ),
        ventilation=VentilationParams(
            per_person_L_s=float(_val(vent["airflow_per_person_L_s"])),
            per_area_L_s_m2=float(_val(vent["airflow_per_area_L_s_m2"])),
            heat_recovery_eff=float(_val(vent["heat_recovery_efficiency"])),
            purge_trigger_C=float(_val(vent["overheat_response"]["trigger_temp_C"])),
            purge_flow_multiplier=float(
                _val(vent["overheat_response"]["flow_multiplier_when_triggered"])
            ),
        ),
        comfort=ComfortParams(
            setpoint_C=float(_val(comfort["setpoint_C"])),
            lower_limit_C=float(_val(comfort["lower_limit_C"])),
            discomfort_above_C=float(_val(comfort["discomfort_above_C"])),
            setback_unoccupied_C=float(_val(comfort["setback_unoccupied_C"])),
        ),
        heating=HeatingParams(
            design_supply_C=float(_val(heat["supply_temp_at_design_outdoor_C"])),
            design_return_C=float(_val(heat["return_temp_at_design_outdoor_C"])),
            design_outdoor_C=float(_val(heat["design_outdoor_temp_C"])),
            mild_supply_C=float(heat["supply_temp_when_outdoor_5C_or_warmer_C"]["max"]),
            radiator_rated_W=float(_val(heat["radiator_rated_output_W"])),
            radiator_response_s=float(_val(heat["radiator_response_time_min"])) * 60.0,
        ),
        actuator=ActuatorParams(
            valve_full_stroke_s=float(
                _opt(act["time_to_move_full_stroke_s"], DEFAULT_VALVE_FULL_STROKE_S)
            ),
        ),
    )


def load_params(path: str | Path = DEFAULT_PARAMS_PATH) -> TwinParams:
    with open(path, encoding="utf-8") as f:
        return params_from_dict(yaml.safe_load(f))
