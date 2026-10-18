"""Metrics over a list of twin ``Record`` steps: per-day summary and totals.

Used by the scenarios and by the twin service. Counts are minutes only when the step
is 60 s (the twin default); energies are exact for any step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .params import TwinParams
from .simulation import Record


@dataclass(frozen=True)
class DaySummary:
    day: str
    peak_t_air_C: float
    peak_time: str
    min_occupied_t_air_C: float
    occupied_minutes_below_lower_limit: int
    minutes_above_setpoint: int
    minutes_above_purge: int
    minutes_above_discomfort: int
    radiator_kWh: float
    coil_kWh: float
    energy_while_above_setpoint_kWh: float  # radiator + coil spent while room >= setpoint
    purge_extra_air_kWh: float  # coil energy for the extra air flow of the purge


def summarise(records: list[Record], params: TwinParams) -> list[DaySummary]:
    c, v = params.comfort, params.ventilation
    per_day = int(timedelta(days=1).total_seconds() // params.step_seconds)
    h = params.step_seconds / 3600.0 / 1000.0  # W per step -> kWh
    out = []
    for i in range(0, len(records), per_day):
        day = records[i : i + per_day]
        peak = max(day, key=lambda r: r.t_air_C)
        occupied = [r.t_air_C for r in day if r.occupants > 0]
        above = [r for r in day if r.t_air_C >= c.setpoint_C]
        purging = [r for r in day if r.t_air_C >= v.purge_trigger_C and r.ventilation_flow_L_s > 0]
        # coil power would be flow/multiplier of the actual during purge
        purge_extra = sum(r.q_coil_W * (1 - 1 / v.purge_flow_multiplier) for r in purging) * h
        out.append(
            DaySummary(
                day=f"{day[0].time:%a %d %b}",
                peak_t_air_C=round(peak.t_air_C, 2),
                peak_time=f"{peak.time:%H:%M}",
                min_occupied_t_air_C=round(min(occupied), 2) if occupied else float("nan"),
                occupied_minutes_below_lower_limit=sum(t < c.lower_limit_C for t in occupied),
                minutes_above_setpoint=len(above),
                minutes_above_purge=sum(r.t_air_C >= v.purge_trigger_C for r in day),
                minutes_above_discomfort=sum(r.t_air_C >= c.discomfort_above_C for r in day),
                radiator_kWh=round(sum(r.q_radiator_W for r in day) * h, 2),
                coil_kWh=round(sum(r.q_coil_W for r in day) * h, 2),
                energy_while_above_setpoint_kWh=round(sum(r.q_radiator_W + r.q_coil_W for r in above) * h, 2),
                purge_extra_air_kWh=round(purge_extra, 2),
            )
        )
    return out


@dataclass(frozen=True)
class Totals:
    radiator_kWh: float
    coil_kWh: float
    peak_t_air_C: float
    minutes_above_purge: int
    occupied_minutes_below_lower_limit: int
    energy_while_above_setpoint_kWh: float


def totals(records, params) -> Totals:
    days = summarise(records, params)
    return Totals(
        radiator_kWh=round(sum(d.radiator_kWh for d in days), 2),
        coil_kWh=round(sum(d.coil_kWh for d in days), 2),
        peak_t_air_C=max(d.peak_t_air_C for d in days),
        minutes_above_purge=sum(d.minutes_above_purge for d in days),
        occupied_minutes_below_lower_limit=sum(d.occupied_minutes_below_lower_limit for d in days),
        energy_while_above_setpoint_kWh=round(sum(d.energy_while_above_setpoint_kWh for d in days), 2),
    )
