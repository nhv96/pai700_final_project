"""Four-panel figure of the overshoot scenario (matplotlib, light surface).

Colour follows the entity, not the panel: room air = blue, radiator = orange,
ventilation coil = aqua, sun = yellow, outdoor air = grey. Thresholds are thin dashed
lines labelled in place. Grey bands mark when the room is occupied.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from twin.params import TwinParams
from twin.simulation import Record

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8984"


def _occupied_spans(records: list[Record]) -> list[tuple]:
    spans, start = [], None
    for r in records:
        if r.occupants > 0 and start is None:
            start = r.time
        elif r.occupants == 0 and start is not None:
            spans.append((start, r.time))
            start = None
    if start is not None:
        spans.append((start, records[-1].time))
    return spans


def plot_overshoot(records: list[Record], params: TwinParams, path: Path) -> None:
    t = [r.time for r in records]
    c, v = params.comfort, params.ventilation
    fig, axes = plt.subplots(
        5, 1, figsize=(13, 11), sharex=True, facecolor=SURFACE,
        gridspec_kw={"height_ratios": [3.2, 1.1, 1.1, 1.5, 1.5], "hspace": 0.14},
    )
    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_2, length=0, labelsize=9)
        for a, b in _occupied_spans(records):
            ax.axvspan(a, b, color="#000000", alpha=0.05, linewidth=0)

    x_end = t[-1] + (t[-1] - t[0]) * 0.015

    # 1. room temperature
    ax = axes[0]
    ax.set_ylim(15, 27.5)
    ax.plot(t, [r.t_air_C for r in records], color=BLUE, linewidth=2)
    for y, label in [
        (c.setpoint_C, f"setpoint {c.setpoint_C:.0f} °C"),
        (v.purge_trigger_C, f"ventilation purge starts {v.purge_trigger_C:.0f} °C"),
        (c.discomfort_above_C, f"discomfort {c.discomfort_above_C:.0f} °C"),
    ]:
        ax.axhline(y, color=INK_2, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.text(t[0], y + 0.15, label, color=INK_2, fontsize=9, va="bottom")
    ax.text(x_end, records[-1].t_air_C, "room air", color=INK, fontsize=10, va="center", fontweight="bold")
    ax.set_ylabel("Room air (°C)", color=INK_2)
    ax.set_title(
        "Room drifts above setpoint and the purge starts, while ventilation air is still being heated",
        loc="left", color=INK, fontsize=12, fontweight="bold", pad=28,
    )
    ax.text(0, 1.03, "Simulated classroom, assumed parameters, not measured data. Grey bands = lessons.",
            transform=ax.transAxes, color=INK_2, fontsize=9)

    # 1b. outdoor temperature
    ax = axes[1]
    ax.plot(t, [r.t_outdoor_C for r in records], color=GREY, linewidth=1.8)
    ax.set_ylabel("Outdoor\n(°C)", color=INK_2)
    ax.text(x_end, records[-1].t_outdoor_C, "outdoor", color=INK_2, fontsize=10, va="center")

    # 2. sun and people
    ax = axes[2]
    ax.fill_between(t, [r.solar_W_m2 for r in records], color=YELLOW, alpha=0.35, linewidth=0)
    ax.plot(t, [r.solar_W_m2 for r in records], color=YELLOW, linewidth=1.8)
    ax.set_ylabel("Sun on window\n(W/m²)", color=INK_2)
    ax.text(x_end, max(r.solar_W_m2 for r in records) * 0.5, "sun", color=INK_2, fontsize=10, va="center")

    # 3. radiator
    ax = axes[3]
    ax.fill_between(t, [r.q_radiator_W / 1000 for r in records], color=ORANGE, alpha=0.3, linewidth=0)
    ax.plot(t, [r.q_radiator_W / 1000 for r in records], color=ORANGE, linewidth=1.8)
    ax.set_ylabel("Radiator heat\n(kW)", color=INK_2)
    ax.text(x_end, 0.5, "radiator", color=INK_2, fontsize=10, va="center")

    # 4. ventilation coil
    ax = axes[4]
    ax.fill_between(t, [r.q_coil_W / 1000 for r in records], color=AQUA, alpha=0.3, linewidth=0, step="post")
    ax.step(t, [r.q_coil_W / 1000 for r in records], color=AQUA, linewidth=1.8, where="post")
    ax.set_ylabel("Ventilation air\nheating (kW)", color=INK_2)
    ax.text(x_end, 3, "ventilation\nheating", color=INK_2, fontsize=10, va="center")

    axes[4].xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    axes[4].xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M"))
    axes[4].set_xlim(t[0], t[-1])
    fig.subplots_adjust(left=0.08, right=0.9, top=0.92, bottom=0.05)
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_comparison(
    legacy: list[Record],
    forecast: list[Record],
    params: TwinParams,
    path: Path,
    title: str = "Forecast pre-heating changes the radiator, but not the overshoot or the main energy cost",
    new_label: str = "forecast",
    lower: str = "radiator",
    note: str = "Forecast controller sees perfect weather and a perfect room model (best case). ",
) -> None:
    """Legacy vs a new controller on the same weather: room air, two lower panels, and total
    energy split into radiator and ventilation heating.

    ``lower="radiator"``: radiator power and sun. ``lower="ventilation"``: ventilation
    heating power and supply air temperature."""
    t = [r.time for r in legacy]
    h = params.step_seconds / 3600.0 / 1000.0
    c, v = params.comfort, params.ventilation
    fig = plt.figure(figsize=(13, 9), facecolor=SURFACE)
    gs = fig.add_gridspec(3, 2, width_ratios=[4.2, 1], height_ratios=[3, 1.5, 1.1], hspace=0.14, wspace=0.28)
    axes = [fig.add_subplot(gs[i, 0]) for i in range(3)]
    for i in (1, 2):
        axes[i].sharex(axes[0])
    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_2, length=0, labelsize=9)
        for a, b in _occupied_spans(legacy):
            ax.axvspan(a, b, color="#000000", alpha=0.05, linewidth=0)
        if ax is not axes[2]:
            ax.tick_params(labelbottom=False)
    x_end = t[-1] + (t[-1] - t[0]) * 0.012

    ax = axes[0]
    ax.set_ylim(15, 27.5)
    for y, label in [(c.setpoint_C, f"setpoint {c.setpoint_C:.0f} °C"),
                     (v.purge_trigger_C, f"purge starts {v.purge_trigger_C:.0f} °C")]:
        ax.axhline(y, color=INK_2, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.text(t[0], y + 0.15, label, color=INK_2, fontsize=9, va="bottom",
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
    ax.plot(t, [r.t_air_C for r in legacy], color=GREY, linewidth=2)
    ax.plot(t, [r.t_air_C for r in forecast], color=BLUE, linewidth=2)
    ax.text(x_end, legacy[-1].t_air_C - 0.35, "legacy", color=INK_2, fontsize=10, va="center")
    ax.text(x_end, forecast[-1].t_air_C + 0.35, new_label, color=INK, fontsize=10, va="center", fontweight="bold")
    ax.set_ylabel("Room air (°C)", color=INK_2)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=28)
    ax.text(0, 1.03, "Simulated classroom, assumed parameters. " + note + "Grey bands = lessons.", transform=ax.transAxes, color=INK_2, fontsize=9)

    ax = axes[1]
    ax2 = axes[2]
    if lower == "radiator":
        ax.plot(t, [r.q_radiator_W / 1000 for r in legacy], color=GREY, linewidth=1.8)
        ax.plot(t, [r.q_radiator_W / 1000 for r in forecast], color=BLUE, linewidth=1.8)
        ax.set_ylabel("Radiator heat\n(kW)", color=INK_2)
        ax2.fill_between(t, [r.solar_W_m2 for r in legacy], color=YELLOW, alpha=0.35, linewidth=0)
        ax2.plot(t, [r.solar_W_m2 for r in legacy], color=YELLOW, linewidth=1.8)
        ax2.set_ylabel("Sun on window\n(W/m²)", color=INK_2)
    else:
        ax.step(t, [r.q_coil_W / 1000 for r in legacy], color=GREY, linewidth=1.8, where="post")
        ax.step(t, [r.q_coil_W / 1000 for r in forecast], color=BLUE, linewidth=1.8, where="post")
        ax.set_ylabel("Ventilation\nheating (kW)", color=INK_2)
        on = lambda recs: [r.t_supply_air_C if r.ventilation_flow_L_s > 0 else float("nan") for r in recs]
        ax2.plot(t, on(legacy), color=GREY, linewidth=1.8)
        ax2.plot(t, on(forecast), color=BLUE, linewidth=1.8)
        ax2.set_ylim(14, 22.5)
        ax2.set_ylabel("Supply air\n(°C)", color=INK_2)
    ax = ax2
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M"))
    ax.set_xlim(t[0], t[-1])

    # Total energy, split by what it paid for
    ax = fig.add_subplot(gs[:, 1])
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0, labelsize=9)
    for i, (name, recs) in enumerate((("legacy", legacy), (new_label, forecast))):
        rad = sum(r.q_radiator_W for r in recs) * h
        coil = sum(r.q_coil_W for r in recs) * h
        ax.bar(i, rad, width=0.55, color=ORANGE, linewidth=0)
        ax.bar(i, coil, width=0.55, bottom=rad + 1.0, color=AQUA, linewidth=0)  # 1 kWh surface gap
        ax.text(i, rad / 2, f"{rad:.1f}", ha="center", va="center", color=INK, fontsize=9)
        ax.text(i, rad + 1.0 + coil / 2, f"{coil:.1f}", ha="center", va="center", color=INK, fontsize=9)
    ax.set_xticks([0, 1], ["legacy", new_label])
    ax.set_ylabel(f"Heat over {len(legacy) * params.step_seconds / 86400:.0f} days (kWh)", color=INK_2)
    ax.text(1.42, 8, "radiator", color=INK_2, fontsize=9, va="center")
    ax.text(1.42, 90, "ventilation\nheating", color=INK_2, fontsize=9, va="center")
    ax.set_xlim(-0.5, 1.9)

    fig.subplots_adjust(left=0.08, right=0.95, top=0.9, bottom=0.07)
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def plot_sensitivity(rows: list[dict], path: Path) -> None:
    """One row per changed assumption. Left: heat saving vs legacy (supply-temp control alone
    = hollow, both controllers combined = filled). Middle: change of the peak room
    temperature. Right: lesson minutes below the lower limit, legacy vs combined."""
    n = len(rows)
    fig, axes = plt.subplots(1, 3, figsize=(14, 0.36 * n + 2.2), sharey=True, facecolor=SURFACE,
                             gridspec_kw={"wspace": 0.06, "width_ratios": [1.2, 1, 1]})
    ys = list(range(n))[::-1]
    labels = [r["case"] if r["group"] == "base case" else f'{r["group"]}: {r["case"]}' for r in rows]
    base = rows[0]
    panels = [
        ("Heat saved vs legacy (%)", [
            ("supply temp only", "supply_temp_saving_pct", BLUE, "hollow"),
            ("both combined", "combined_saving_pct", BLUE, "filled"),
        ], base["combined_saving_pct"]),
        ("Peak room temperature change (K)", [
            ("both combined", "combined_peak_change_K", BLUE, "filled"),
        ], base["combined_peak_change_K"]),
        ("Lesson minutes below 20 °C (5 days)", [
            ("legacy", "legacy_cold_lesson_min", GREY, "filled"),
            ("both combined", "combined_cold_lesson_min", BLUE, "filled"),
        ], None),
    ]
    for ax, (title, series, ref) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        for i, r in enumerate(rows):
            if i % 2 == 0:
                ax.axhspan(ys[i] - 0.5, ys[i] + 0.5, color="#000000", alpha=0.035, linewidth=0)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_2, length=0, labelsize=9)
        if ref is not None:
            ax.axvline(ref, color=INK_2, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.axvline(0, color=INK_2, linewidth=0.8)
        for label, key, color, style in series:
            xs = [r[key] for r in rows]
            ax.scatter(xs, ys, s=38, zorder=3, label=label,
                       facecolors=SURFACE if style == "hollow" else color, edgecolors=color, linewidths=1.6)
        ax.set_title(title, loc="left", color=INK, fontsize=10, fontweight="bold", pad=22)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8.5,
                  labelcolor=INK_2, handletextpad=0.2, columnspacing=1.2)
        ax.set_ylim(-0.7, n - 0.3)
    axes[0].set_yticks(ys, labels)
    axes[0].tick_params(axis="y", labelcolor=INK, labelsize=9)
    fig.suptitle("The saving depends on how much the room overshoots; the combined controller never adds cold lesson minutes",
                 x=0.01, ha="left", color=INK, fontsize=12, fontweight="bold")
    fig.text(0.01, 0.945, "Each row changes ONE assumed value from the base case (dashed line). 5 simulated days, "
             "perfect forecast for the forecast part.", color=INK_2, fontsize=9)
    fig.subplots_adjust(left=0.21, right=0.98, top=0.86, bottom=0.05)
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)
