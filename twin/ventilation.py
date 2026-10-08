"""Mechanical ventilation, including the 'system fighting' overheat purge.

Flow while the plant runs: ``per_person * occupants + per_area * floor_area`` (L/s).
When the room air reaches ``purge_trigger_C`` the flow is multiplied by
``purge_flow_multiplier``. The trigger and multiplier are placeholders in params.yaml
(assumed), standing in for the behaviour described in the team's problem analysis:
the ventilation ramps up to blow out heat the radiators put in all morning.
"""

from __future__ import annotations

from .params import VentilationParams


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
