"""THROWAWAY 1R1C room model. Not the teammate's heat model.

Only here so the twin shows temperature dynamics before the real HeatModel arrives.
R and C are invented placeholders (they are not in params.yaml). Delete this file and
pass the real model to ``build_default_twin(model=...)`` once it exists.

    C * dT_in/dt = Q_radiator + Q_internal + Q_solar - (T_in - T_out)/R - Q_vent
    Q_solar = irradiance * window_area * g_value
    Q_vent  = (1 - heat_recovery_eff) * rho * cp * flow * (T_in - T_supply_air)
"""

from __future__ import annotations

from dataclasses import replace

from .interface import StepInputs, ZoneState
from .params import TwinParams

RHO_AIR = 1.2  # kg/m3
CP_AIR = 1005.0  # J/(kg K)

# Placeholders, deliberately not from params.yaml:
R_ENVELOPE_K_PER_W = 0.025  # ~40 W/K envelope conductance (assumed)
C_ZONE_J_PER_K = 2.2e6  # air plus furniture and fabric, effective (assumed)
WINDOW_G_VALUE = 0.6  # params.yaml 'window_g_value', typical (assumed)


class OneR1CPlaceholder:
    def __init__(
        self,
        window_area_m2: float,
        r_K_per_W: float = R_ENVELOPE_K_PER_W,
        c_J_per_K: float = C_ZONE_J_PER_K,
        g_value: float = WINDOW_G_VALUE,
    ) -> None:
        self.window_area_m2 = window_area_m2
        self.r = r_K_per_W
        self.c = c_J_per_K
        self.g = g_value

    @classmethod
    def from_params(cls, params: TwinParams) -> "OneR1CPlaceholder":
        return cls(window_area_m2=params.zone.window_area_m2)

    def step(self, state: ZoneState, inputs: StepInputs, dt_s: float) -> ZoneState:
        t_in = state.t_air_C
        q_solar = inputs.solar_irradiance_W_m2 * self.window_area_m2 * self.g
        q_trans = (t_in - inputs.t_outdoor_C) / self.r
        flow_m3s = inputs.ventilation_flow_L_s / 1000.0
        q_vent = (
            (1.0 - inputs.heat_recovery_eff)
            * RHO_AIR
            * CP_AIR
            * flow_m3s
            * (t_in - inputs.supply_air_temp_C)
        )
        dq = inputs.q_radiator_W + inputs.q_internal_W + q_solar - q_trans - q_vent
        return replace(state, t_air_C=t_in + dq / self.c * dt_s)
