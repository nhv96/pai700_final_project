"""Tests for the two-node room model, the AHU step and the overshoot scenario."""

import pytest

from twin.interface import StepInputs, ZoneState
from twin.params import load_params
from twin.room_model import RHO_AIR, CP_AIR, RoomModelParams, TwoNodeRoomModel, TwoNodeState
from twin.ventilation import RHO_CP_AIR, ahu_step
from scenarios.overshoot import run, summarise


def quiet(**kw) -> StepInputs:
    base = dict(
        t_outdoor_C=0.0, solar_irradiance_W_m2=0.0, occupants=0, q_internal_W=0.0,
        q_radiator_W=0.0, ventilation_flow_L_s=0.0, supply_air_temp_C=0.0, heat_recovery_eff=0.0,
    )
    base.update(kw)
    return StepInputs(**base)


def settle(model, inp, t0, steps):
    state = TwoNodeState(t_air_C=t0, t_mass_C=t0)
    for _ in range(steps):
        state = model.step(state, inp, 60.0)
    return state


def test_no_heat_settles_at_outdoor_temperature():
    model = TwoNodeRoomModel.from_params(load_params())
    s = settle(model, quiet(t_outdoor_C=5.0, supply_air_temp_C=5.0), 20.0, 120 * 1440)
    assert s.t_air_C == pytest.approx(5.0, abs=1e-3)
    assert s.t_mass_C == pytest.approx(5.0, abs=1e-3)


def test_constant_radiator_heat_matches_hand_solved_steady_state():
    model = TwoNodeRoomModel.from_params(load_params())
    q, f = 1000.0, model.p.frac_radiator_to_air
    h_ao, h_am, h_w = model.h_air_out, model.h_air_mass, model.h_wall
    # steady state: air  f q + h_am (Tm - Ta) - h_ao Ta = 0 ; mass (1-f) q + h_am (Ta - Tm) - h_w Tm = 0
    a11, a12, b1 = h_ao + h_am, -h_am, f * q
    a21, a22, b2 = -h_am, h_am + h_w, (1 - f) * q
    expected = (b1 * a22 - a12 * b2) / (a11 * a22 - a12 * a21)
    s = settle(model, quiet(q_radiator_W=q), 0.0, 120 * 1440)
    assert s.t_air_C == pytest.approx(expected, abs=1e-2)


def test_energy_is_conserved_in_one_step():
    # Stored heat change = heat in - heat lost to outside and supply air (backward Euler, so
    # losses use the NEW temperatures).
    model = TwoNodeRoomModel.from_params(load_params())
    inp = quiet(t_outdoor_C=-5.0, supply_air_temp_C=18.0, ventilation_flow_L_s=100.0,
                q_radiator_W=2000.0, q_internal_W=1500.0, solar_irradiance_W_m2=300.0)
    s0 = TwoNodeState(t_air_C=20.0, t_mass_C=19.0)
    s1 = model.step(s0, inp, 60.0)
    stored = model.c_air * (s1.t_air_C - s0.t_air_C) + model.c_mass * (s1.t_mass_C - s0.t_mass_C)
    h_vent = RHO_AIR * CP_AIR * 0.1
    gains = inp.q_radiator_W + inp.q_internal_W + model.solar_aperture_m2 * 300.0
    losses = (model.h_air_out * (s1.t_air_C + 5.0) + h_vent * (s1.t_air_C - 18.0)
              + model.h_wall * (s1.t_mass_C + 5.0))
    assert stored / 60.0 == pytest.approx(gains - losses, rel=1e-9)


def test_first_step_accepts_plain_zone_state():
    s = TwoNodeRoomModel.from_params(load_params()).step(ZoneState(t_air_C=20.0), quiet(), 60.0)
    assert isinstance(s, TwoNodeState)
    assert s.t_mass_C == pytest.approx(20.0, abs=0.1)


def test_wall_stores_heat_after_radiator_stops():
    # Thermal inertia: after heating stops, the wall keeps the air above where it would be.
    model = TwoNodeRoomModel.from_params(load_params())
    hot = settle(model, quiet(q_radiator_W=3000.0), 15.0, 3 * 1440)
    cold_wall = TwoNodeState(t_air_C=hot.t_air_C, t_mass_C=0.0)
    a = settle(model, quiet(), hot.t_air_C, 120).t_air_C
    b = model.step(cold_wall, quiet(), 60.0).t_air_C
    assert a > b


def test_ahu_without_heat_recovery_heats_outdoor_air_to_target():
    v = load_params().ventilation
    r = ahu_step(v, flow_L_s=200.0, t_outdoor_C=1.0, t_extract_C=22.0, t_target_C=21.0)
    assert r.t_supply_C == 21.0
    assert r.q_coil_W == pytest.approx(RHO_CP_AIR * 0.2 * 20.0)


def test_ahu_heat_recovery_cuts_coil_energy():
    v = load_params().ventilation
    from dataclasses import replace
    hr = replace(v, heat_recovery_eff=0.8)
    plain = ahu_step(v, 200.0, 1.0, 22.0, 21.0)
    recov = ahu_step(hr, 200.0, 1.0, 22.0, 21.0)
    assert recov.q_coil_W < 0.3 * plain.q_coil_W


def test_ahu_does_not_cool_and_idles_without_flow():
    v = load_params().ventilation
    warm = ahu_step(v, 200.0, 25.0, 22.0, 21.0)
    assert warm.q_coil_W == 0.0 and warm.t_supply_C == 25.0
    assert ahu_step(v, 0.0, 0.0, 22.0, 21.0).q_coil_W == 0.0


def test_scenario_shows_the_client_problem():
    params = load_params()
    days = summarise(run(params), params)
    assert len(days) == 3
    last = days[-1]
    assert last.peak_t_air_C > params.comfort.setpoint_C + 2  # overshoot
    assert last.minutes_above_purge > 0  # the purge starts
    assert last.coil_kWh > 0  # while ventilation air is still heated
    assert last.energy_while_above_setpoint_kWh > 0


# --- forecast controller -------------------------------------------------------------
from datetime import timedelta

from twin.controller import LegacyController
from twin.predictive_controller import ForecastController
from twin.sensors import Measurements


def test_forecast_controller_needs_bind():
    p = load_params()
    fc = ForecastController(p.heating, p.comfort, p.occupancy)
    from datetime import datetime
    with pytest.raises(RuntimeError, match="bind"):
        fc.act(datetime(2026, 10, 12, 6, 0), Measurements(17.0, 2.0, 0))


def test_preview_does_not_change_the_live_twin():
    from twin.simulation import build_default_twin
    p = load_params()
    twin = build_default_twin(model=TwoNodeRoomModel.from_params(p), initial_t_air_C=19.0)
    twin.run(timedelta(hours=3))
    before = (twin.time, twin.state, twin.radiator.q_W, twin.radiator.valve_position, twin.controller)
    ahead = twin.preview(LegacyController(p.heating, p.comfort), timedelta(hours=2))
    assert len(ahead) == 120
    assert (twin.time, twin.state, twin.radiator.q_W, twin.radiator.valve_position, twin.controller) == before


def test_forecast_controller_keeps_ventilation_like_legacy_and_improves_comfort():
    p = load_params()
    legacy = run(p, days=2)
    forecast = run(p, days=2, controller=ForecastController(p.heating, p.comfort, p.occupancy))
    # ventilation timer unchanged, so ventilation flow is identical step by step
    assert [r.ventilation_flow_L_s for r in legacy[:1440]] == [r.ventilation_flow_L_s for r in forecast[:1440]]
    cold = lambda recs: sum(s.occupied_minutes_below_lower_limit for s in summarise(recs, p))
    assert cold(forecast) <= cold(legacy)


# --- supply temperature controller ---------------------------------------------------
from datetime import datetime

from twin.supply_controller import SupplyTempController


def _supply_target(t_room: float) -> float:
    p = load_params()
    c = SupplyTempController(LegacyController(p.heating, p.comfort), p.comfort, min_supply_C=16.0)
    return c.act(datetime(2026, 10, 13, 10, 0), Measurements(t_room, 2.0, 26)).air_supply_target_C


def test_supply_target_is_legacy_at_or_below_setpoint():
    assert _supply_target(19.0) == 21.0
    assert _supply_target(21.0) == 21.0


def test_supply_target_falls_with_room_temperature_and_stops_at_minimum():
    assert _supply_target(22.0) == pytest.approx(19.0)
    assert _supply_target(30.0) == 16.0


def test_supply_controller_rejects_minimum_above_setpoint():
    p = load_params()
    with pytest.raises(ValueError):
        SupplyTempController(LegacyController(p.heating, p.comfort), p.comfort, min_supply_C=22.0)


def test_supply_control_saves_heat_and_keeps_comfort():
    p = load_params()
    legacy = run(p, days=3)
    new = run(p, days=3, controller=SupplyTempController(LegacyController(p.heating, p.comfort), p.comfort))
    heat = lambda recs: sum(s.radiator_kWh + s.coil_kWh for s in summarise(recs, p))
    cold = lambda recs: sum(s.occupied_minutes_below_lower_limit for s in summarise(recs, p))
    assert heat(new) < 0.9 * heat(legacy)
    assert cold(new) <= cold(legacy)


# --- combined controller and parameter plumbing --------------------------------------
from dataclasses import replace

from scenarios.compare_combined import make_controllers


def test_build_default_twin_uses_the_params_it_is_given():
    from twin.simulation import build_default_twin
    p = load_params()
    p2 = replace(p, ventilation=replace(p.ventilation, heat_recovery_eff=0.7))
    assert build_default_twin(params=p2).params.ventilation.heat_recovery_eff == 0.7


def test_heat_recovery_cuts_ventilation_heating_in_the_scenario():
    p = load_params()
    p2 = replace(p, ventilation=replace(p.ventilation, heat_recovery_eff=0.7))
    coil = lambda recs: sum(r.q_coil_W for r in recs)
    assert coil(run(p2, days=2)) < 0.5 * coil(run(p, days=2))


def test_combined_controller_previews_with_supply_control_and_beats_each_alone_on_comfort():
    p = load_params()
    runs = {n: run(p, days=3, controller=c) for n, c in make_controllers(p).items()}
    heat = lambda recs: sum(s.radiator_kWh + s.coil_kWh for s in summarise(recs, p))
    cold = lambda recs: sum(s.occupied_minutes_below_lower_limit for s in summarise(recs, p))
    assert heat(runs["combined"]) < 0.9 * heat(runs["legacy"])
    assert cold(runs["combined"]) <= cold(runs["supply temp"])
    assert cold(runs["combined"]) < cold(runs["legacy"])
