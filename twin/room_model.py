"""Two-node room model: our own heat model, behind the twin's ``HeatModel`` interface.

Idea taken from the teammate's ``heat-model/`` (two heat stores, ISO 13790 style), but
rewritten against the twin's own ``StepInputs``, with no extra files or contract.

Two heat stores:

* air node (fast): room air plus furniture, reacts in minutes;
* mass node (slow): walls, floor and ceiling, reacts over days. This is the thermal
  inertia: it keeps releasing heat after the radiator is closed, which is what lets
  the room overshoot.

    C_air  dT_air/dt  = H_out (T_out - T_air) + H_vent (T_supply - T_air)
                        + H_am (T_mass - T_air) + Q_to_air
    C_mass dT_mass/dt = H_wall (T_out - T_mass) + H_am (T_air - T_mass) + Q_to_mass

Solved with backward Euler (stable for any step), 2x2 system by Cramer's rule.

Inputs that matter: ``supply_air_temp_C`` is the air AS IT ENTERS THE ROOM, i.e. after
heat recovery and the heating coil (computed by the twin, see ``ventilation.ahu_step``).
``heat_recovery_eff`` is therefore NOT used here, otherwise recovery would count twice.
``occupants`` is not used either: people's heat is already in ``q_internal_W``.

All numbers in ``RoomModelParams`` below are ASSUMED unless stated. The wall U-value,
infiltration and the heat-split fractions are calibration knobs, not measurements.
"""

from __future__ import annotations

from dataclasses import dataclass

from .interface import StepInputs, ZoneState
from .params import TwinParams

RHO_AIR = 1.2  # kg/m3
CP_AIR = 1005.0  # J/(kg K)


@dataclass(frozen=True)
class TwoNodeState(ZoneState):
    """ZoneState plus the wall temperature. The twin passes it back unchanged."""

    t_mass_C: float = 20.0


@dataclass(frozen=True)
class RoomModelParams:
    # Geometry: these four come from params.yaml (see ``from_twin_params``)
    floor_area_m2: float = 60.0
    height_m: float = 3.0
    window_area_m2: float = 10.0
    g_value: float = 0.6

    # Air node
    furniture_factor: float = 5.0  # air node capacity = room air x this (desks, chairs react like air)
    # Mass node: ISO 13790 "heavy" class (old masonry school)
    mass_capacity_J_m2K: float = 260_000.0  # per m2 floor
    mass_area_factor: float = 3.0  # effective mass surface = 3 x floor area
    h_mass_surface_W_m2K: float = 9.1  # surface to air coefficient
    # Envelope (assumed; interior classroom with one external wall)
    u_window_W_m2K: float = 2.8  # old double glazing
    opaque_wall_area_m2: float = 14.0  # 8 m x 3 m minus windows
    u_wall_W_m2K: float = 0.8  # CALIBRATION KNOB
    infiltration_ach: float = 0.15  # 1/h, CALIBRATION KNOB
    glass_fraction: float = 0.8  # share of the window opening that is glass
    shading_factor: float = 1.0  # 1 = no shading (about 3/4 of schools, SKR 2011)
    # Where each heat source lands (assumed)
    frac_solar_to_air: float = 0.1  # sunlight mostly warms floor and walls first
    frac_internal_to_air: float = 0.5  # people, lights, PCs: about half convective
    frac_radiator_to_air: float = 0.7  # panel radiators: about 70 % convection

    @classmethod
    def from_twin_params(cls, params: TwinParams, **overrides: float) -> "RoomModelParams":
        z = params.zone
        return cls(
            floor_area_m2=z.floor_area_m2,
            height_m=z.ceiling_height_m,
            window_area_m2=z.window_area_m2,
            g_value=z.window_g_value,
            **overrides,
        )


class TwoNodeRoomModel:
    def __init__(self, params: RoomModelParams | None = None, initial_t_mass_C: float | None = None) -> None:
        self.p = params or RoomModelParams()
        self.initial_t_mass_C = initial_t_mass_C
        p = self.p
        volume = p.floor_area_m2 * p.height_m
        rho_cp = RHO_AIR * CP_AIR
        self.rho_cp = rho_cp
        self.c_air = rho_cp * volume * p.furniture_factor  # J/K
        self.c_mass = p.mass_capacity_J_m2K * p.floor_area_m2  # J/K
        self.h_air_mass = p.h_mass_surface_W_m2K * p.mass_area_factor * p.floor_area_m2  # W/K
        self.h_air_out = p.u_window_W_m2K * p.window_area_m2 + rho_cp * volume * p.infiltration_ach / 3600.0
        self.h_wall = p.u_wall_W_m2K * p.opaque_wall_area_m2
        self.solar_aperture_m2 = p.window_area_m2 * p.glass_fraction * p.g_value * p.shading_factor

    @classmethod
    def from_params(cls, params: TwinParams, **overrides: float) -> "TwoNodeRoomModel":
        return cls(RoomModelParams.from_twin_params(params, **overrides))

    def step(self, state: ZoneState, inputs: StepInputs, dt_s: float) -> TwoNodeState:
        p = self.p
        ta = state.t_air_C
        if isinstance(state, TwoNodeState):
            tm = state.t_mass_C
        else:  # first step: the twin only knows the air temperature
            tm = ta if self.initial_t_mass_C is None else self.initial_t_mass_C
        to = inputs.t_outdoor_C

        h_vent = self.rho_cp * inputs.ventilation_flow_L_s / 1000.0  # W/K

        q_solar = self.solar_aperture_m2 * max(inputs.solar_irradiance_W_m2, 0.0)
        q_int = inputs.q_internal_W
        q_rad = max(inputs.q_radiator_W, 0.0)
        q_to_air = (
            p.frac_solar_to_air * q_solar
            + p.frac_internal_to_air * q_int
            + p.frac_radiator_to_air * q_rad
        )
        q_to_mass = (
            (1 - p.frac_solar_to_air) * q_solar
            + (1 - p.frac_internal_to_air) * q_int
            + (1 - p.frac_radiator_to_air) * q_rad
        )

        a11 = self.c_air / dt_s + self.h_air_out + h_vent + self.h_air_mass
        a12 = -self.h_air_mass
        b1 = (
            self.c_air / dt_s * ta
            + self.h_air_out * to
            + h_vent * inputs.supply_air_temp_C
            + q_to_air
        )
        a21 = -self.h_air_mass
        a22 = self.c_mass / dt_s + self.h_wall + self.h_air_mass
        b2 = self.c_mass / dt_s * tm + self.h_wall * to + q_to_mass

        det = a11 * a22 - a12 * a21
        ta_new = (b1 * a22 - a12 * b2) / det
        tm_new = (a11 * b2 - b1 * a21) / det
        return TwoNodeState(t_air_C=ta_new, t_mass_C=tm_new)

