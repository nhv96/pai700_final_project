"""Mechanical ventilation, including the 'system fighting' overheat purge, and the
air-handling unit (AHU) that conditions the supply air.

Flow while the plant runs: ``per_person * occupants + per_area * floor_area`` (L/s).
When the room air reaches ``purge_trigger_C`` the flow is multiplied by
``purge_flow_multiplier``. The trigger and multiplier are placeholders in params.yaml
(assumed), standing in for the behaviour described in the team's problem analysis:
the ventilation ramps up to blow out heat the radiators put in all morning.
"""

from __future__ import annotations

from dataclasses import dataclass

from .params import VentilationParams

RHO_CP_AIR = 1.2 * 1005.0  # J/(m3 K)


def ventilation_flow_L_s(
    params: VentilationParams,
    floor_area_m2: float,
    occupants: int,
    running: bool,
    t_air_C: float,
) -> float:
    if not running:
        return 0.0
    flow = params.per_person_L_s * occupants + params.per_area_L_s_m2 * floor_area_m2
    if t_air_C >= params.purge_trigger_C:
        flow *= params.purge_flow_multiplier
    return flow


@dataclass(frozen=True)
class AhuResult:
    t_supply_C: float  # air as it ENTERS the room (after heat recovery and coil)
    q_coil_W: float  # heat the heating coil adds to the air (ventilation energy)


def ahu_step(
    params: VentilationParams,
    flow_L_s: float,
    t_outdoor_C: float,
    t_extract_C: float,
    t_target_C: float,
) -> AhuResult:
    """Supply air: heat recovery first, then a heating coil up to ``t_target_C``.

    Heat recovery warms the outdoor air towards the extract (room) air:
    ``t_hr = t_out + eff * (t_extract - t_out)``. The coil only heats, never cools, so
    warm air is passed on as it is. With no flow there is no coil energy.
    """
    t_hr = t_outdoor_C + params.heat_recovery_eff * (t_extract_C - t_outdoor_C)
    if flow_L_s <= 0.0:
        return AhuResult(t_supply_C=t_hr, q_coil_W=0.0)
    q_coil = RHO_CP_AIR * flow_L_s / 1000.0 * max(t_target_C - t_hr, 0.0)
    return AhuResult(t_supply_C=max(t_hr, t_target_C), q_coil_W=q_coil)
