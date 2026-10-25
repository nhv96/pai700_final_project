"""Building status from heat use only: which building is using more heat than it should, and which is about to.

Pure functions, no I/O (app.py fetches the data). Everything is judged against what the building "should"
use at that hour:

  expected heat   what the forecast model predicted for that hour 24 h earlier, before anything unusual
                  happened (a 1 h-ahead forecast would see the surge in the last hour and follow it, which
                  hides sustained over-use); where it is missing, a baseline from the building's own recent
                  days: the median of the same hour on the same kind of day (weekday / weekend), moved
                  along the outdoor-temperature slope of those days.
  excess          how far actual heat is above expected, over the last 6 h and 24 h.
  load soon       the forecast for 1, 6 and 24 h ahead compared with the highest load of the last 14 days.
  data quality    a missing latest reading or a meter stuck at one value is reported as `no_data`, never as
                  a heating problem.

There is no indoor temperature in the data, so "overheating" here means "more heat than expected".
"""
from datetime import datetime, timedelta
from statistics import median

LEVELS = {"ok": 0, "watch": 1, "alert": 2}
HISTORY_DAYS = 14
RECENT_H, DAY_H = 6, 24
MIN_SAMPLES = 3            # same-hour days needed for a baseline value
SLOPE_SAMPLES = 6          # samples needed before the temperature slope is used
MIN_COVERAGE = 0.5         # share of the window's hours that need an expected value
STUCK_H = 6                # identical non-zero readings in a row = stuck meter
# Thresholds (watch, alert) for "actual is this far above expected", tuned on the whole replay window
# (dashboard/README.md, "How the thresholds were chosen"). The baseline is much noisier than the forecast,
# so it needs much bigger gaps before it says anything.
EXCESS = {"forecast": {"excess_6h": (0.25, 0.60), "excess_24h": (0.25, 0.40)},
          "baseline": {"excess_6h": (0.80, 1.50), "excess_24h": (0.60, 1.00)}}
MIN_EXCESS_SHARE = (0.05, 0.10)   # (watch, alert): mean excess must be at least this share of the building's highest load
PEAK_WATCH, PEAK_ALERT = 1.05, 1.15
HORIZONS = (1, 6, 24)
EXPECTED_HORIZON = 24             # hours between the forecast and the hour it is about


def day_kind(t: datetime) -> bool:
    return t.weekday() >= 5


def baseline(t: datetime, tout: float | None, history: dict[datetime, tuple[float, float | None]]) -> float | None:
    """Expected heat (Wh) at hour `t` from earlier days of the same history; None with too few samples."""
    same = [(h, o) for ts, (h, o) in history.items()
            if ts < t and ts.hour == t.hour and day_kind(ts) == day_kind(t)]
    if len(same) < MIN_SAMPLES:
        return None
    slope = 0.0
    pairs = [(o, h) for h, o in same if o is not None]
    if tout is not None and len(pairs) >= SLOPE_SAMPLES:
        mo = sum(o for o, _ in pairs) / len(pairs)
        mh = sum(h for _, h in pairs) / len(pairs)
        var = sum((o - mo) ** 2 for o, _ in pairs)
        if var > 0:
            slope = min(0.0, sum((o - mo) * (h - mh) for o, h in pairs) / var)   # heat never rises with warmth
    return max(0.0, median(h + (slope * (tout - o) if o is not None and tout is not None else 0.0) for h, o in same))


def excess(hours: list[datetime], history, expected: dict[datetime, float]) -> float | None:
    """(actual - expected) / expected over `hours`, or None if too few of them have an expected value."""
    pairs = [(history[t][0], expected[t]) for t in hours if t in history and expected.get(t) is not None]
    total = sum(e for _, e in pairs)
    if len(pairs) < MIN_COVERAGE * len(hours) or total <= 0:
        return None
    return (sum(a for a, _ in pairs) - total) / total


def assess(now: datetime, history: dict[datetime, tuple[float, float | None]],
           forecast_past: dict[datetime, float], forecast_ahead: dict[int, float]) -> dict:
    """One building. `history`: hour -> (heat Wh, outdoor °C), up to and including `now`.
    `forecast_past`: hour -> what the model predicted for it EXPECTED_HORIZON hours earlier. `forecast_ahead`: horizon h -> Wh at now+h."""
    last = [now - timedelta(hours=i) for i in range(DAY_H)][::-1]
    out = {"expected_kw": None, "actual_kw": None, "excess_6h": None, "excess_24h": None,
           "basis": None, "peak_ratio": None, "reasons": []}

    def finish(status):
        out["status"] = status
        out["reasons"].sort(key=lambda r: -LEVELS.get(r["level"], 0))
        return out

    if now not in history:
        out["reasons"].append({"code": "stale", "level": "no_data", "message": "No reading for the current hour."})
        return finish("no_data")
    out["actual_kw"] = history[now][0] / 1000
    recent = [history[t][0] for t in last[-STUCK_H:] if t in history]
    if len(recent) == STUCK_H and len(set(recent)) == 1 and recent[0] > 0:
        out["reasons"].append({"code": "stuck", "level": "no_data",
                               "message": f"The meter has shown {recent[0] / 1000:.0f} kW for {STUCK_H} hours; it looks stuck."})
        return finish("no_data")

    expected, source = {}, {}
    for t in last:
        if t in forecast_past:
            expected[t], source[t] = forecast_past[t], "forecast"
        elif t in history:
            b = baseline(t, history[t][1], history)
            if b is not None:
                expected[t], source[t] = b, "baseline"
    used = set(source.values())
    out["basis"] = "forecast" if used == {"forecast"} else "baseline" if used == {"baseline"} else "mixed" if used else None
    if now in expected:
        out["expected_kw"] = expected[now] / 1000
    peak = max((h for h, _ in history.values()), default=0.0)

    limits = EXCESS["forecast" if out["basis"] == "forecast" else "baseline"]    # "mixed" is judged as strictly as the baseline
    for key, hours, label in (("excess_6h", last[-RECENT_H:], "6 h"), ("excess_24h", last, "24 h")):
        e = excess(hours, history, expected)
        out[key] = e
        if e is None:
            continue
        diff = sum(history[t][0] - expected[t] for t in hours if t in expected) / sum(1 for t in hours if t in expected)
        watch, alert = limits[key]
        level = ("alert" if e >= alert and diff >= MIN_EXCESS_SHARE[1] * peak else
                 "watch" if e >= watch and diff >= MIN_EXCESS_SHARE[0] * peak else None)
        if level and not (key == "excess_24h" and any(r["code"] == "excess_6h" and r["level"] == level for r in out["reasons"])):
            out["reasons"].append({"code": key, "level": level,
                                   "message": f"Heat over the last {label} is {e:.0%} above expected."})

    ratios = {h: forecast_ahead[h] / peak for h in HORIZONS if h in forecast_ahead and peak > 0}
    if ratios:
        h, r = max(ratios.items(), key=lambda kv: kv[1])
        out["peak_ratio"] = r
        level = "alert" if r >= PEAK_ALERT else "watch" if r >= PEAK_WATCH else None
        if level:
            out["reasons"].append({"code": "load_soon", "level": level,
                                   "message": f"In {h} h the forecast is {r - 1:.0%} above the highest load of the last {HISTORY_DAYS} days."})

    if out["excess_6h"] is None and out["excess_24h"] is None:
        out["reasons"].append({"code": "no_baseline", "level": "info",
                               "message": "Not enough history yet to say what is normal."})
    return finish(max((r["level"] for r in out["reasons"] if r["level"] in LEVELS), key=LEVELS.get, default="ok"))


def summarize(buildings: list[dict]) -> dict:
    counts = {k: 0 for k in ("alert", "watch", "ok", "no_data")}
    for b in buildings:
        counts[b["status"]] += 1
    return counts
