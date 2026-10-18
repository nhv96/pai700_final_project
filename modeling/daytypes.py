"""Day types for Norway/Oslo: public holidays and school breaks, as 0/1 flags per calendar day.

Public holidays come from the `holidays` library, plus 24 and 31 December (de facto days off).
School breaks follow the common Oslo school calendar (osloskolen.no: the autumn break is always week 40
and the winter break always week 8). Easter break: Monday of Holy Week to Easter Monday. Christmas
break: 21 December to 1 January, which is approximate (the real first and last school day move by a
day or two between years). School planning days are not included.
"""
from datetime import date, timedelta

import holidays
import numpy as np
import pandas as pd
from dateutil.easter import easter

FIRST_YEAR, LAST_YEAR = 2011, 2024


def _public(years) -> set:
    days = set(holidays.Norway(years=years))
    for y in years:
        days |= {date(y, 12, 24), date(y, 12, 31)}
    return days


def _school_break(years) -> set:
    days = set()
    for y in years:
        week = lambda n: date.fromisocalendar(y, n, 1)             # Monday of ISO week n
        for start in (week(8), week(40)):                          # winter break, autumn break
            days |= {start + timedelta(d) for d in range(5)}
        easter_sun = easter(y)
        days |= {easter_sun - timedelta(6) + timedelta(d) for d in range(7)}      # Mon of Holy Week .. Easter Mon
        days |= {date(y, 12, 21) + timedelta(d) for d in range(12)}               # 21 Dec .. 1 Jan
    return days


_YEARS = range(FIRST_YEAR, LAST_YEAR + 1)
PUBLIC, SCHOOL_BREAK = _public(_YEARS), _school_break(_YEARS)


def day_flags(days: pd.DatetimeIndex) -> pd.DataFrame:
    """holiday, school_break and off (weekend or holiday) for each calendar day, as float32 0/1."""
    d = days.normalize().tz_localize(None).date if days.tz is not None else days.normalize().date
    if min(d) < date(FIRST_YEAR, 1, 1) or max(d) > date(LAST_YEAR, 12, 31):
        raise ValueError("dates outside the supported years")
    hol = np.fromiter((x in PUBLIC for x in d), bool, len(d))
    brk = np.fromiter((x in SCHOOL_BREAK for x in d), bool, len(d))
    wkend = np.fromiter((x.weekday() >= 5 for x in d), bool, len(d))
    return pd.DataFrame({"holiday": hol, "school_break": brk, "off": hol | wkend}).astype(np.float32)


def daytype_features(target_time: pd.DatetimeIndex) -> pd.DataFrame:
    """Flags for the target day and for the day before and after it, one row per window."""
    cols = {}
    for name, shift in (("", 0), ("_prev", -1), ("_next", 1)):
        f = day_flags(target_time + pd.Timedelta(days=shift))
        for c in f:
            cols[f"{c}{name}"] = f[c].to_numpy()
    return pd.DataFrame(cols)
