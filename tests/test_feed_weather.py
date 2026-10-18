from datetime import datetime

import pytest

from twin.feed_weather import FeedWeather, to_data_clock

ROWS = [
    {"timestamp": "2022-11-07T00:00:00+01:00", "Tout": 4.0, "SolGlob": 0.0},
    {"timestamp": "2022-11-07T01:00:00+01:00", "Tout": 6.0, "SolGlob": 100.0},
    {"timestamp": "2022-11-07T02:00:00+01:00", "Tout": 6.0, "SolGlob": -1e-9},
]


def test_interpolates_linearly_and_scales_sun():
    w = FeedWeather(ROWS, south_facade_ratio=2.0)
    s = w.at(datetime(2022, 11, 7, 0, 30))
    assert s.t_outdoor_C == pytest.approx(5.0)
    assert s.solar_irradiance_W_m2 == pytest.approx(100.0)  # (0 + 100) / 2 * ratio 2


def test_exact_hour_and_negative_sun_is_clipped():
    w = FeedWeather(ROWS, south_facade_ratio=1.5)
    assert w.at(datetime(2022, 11, 7, 1, 0)).solar_irradiance_W_m2 == pytest.approx(150.0)
    assert w.at(datetime(2022, 11, 7, 2, 0)).solar_irradiance_W_m2 == 0.0


def test_holds_first_and_last_value_outside_the_data():
    w = FeedWeather(ROWS, south_facade_ratio=1.0)
    assert w.at(datetime(2022, 11, 6, 12)).t_outdoor_C == 4.0
    assert w.at(datetime(2022, 11, 8, 12)).t_outdoor_C == 6.0
    assert (w.first, w.last) == (datetime(2022, 11, 7, 0), datetime(2022, 11, 7, 2))


def test_rows_may_arrive_in_any_order():
    assert FeedWeather(ROWS[::-1], 1.0).at(datetime(2022, 11, 7, 0, 30)).t_outdoor_C == pytest.approx(5.0)


def test_data_clock_is_fixed_utc_plus_1():
    assert to_data_clock("2022-11-07T08:00:00+01:00") == datetime(2022, 11, 7, 8)
    assert to_data_clock("2022-11-07T07:00:00+00:00") == datetime(2022, 11, 7, 8)
    assert to_data_clock("2022-11-07T08:00") == datetime(2022, 11, 7, 8)


def test_rejects_empty_and_negative_ratio():
    with pytest.raises(ValueError):
        FeedWeather([], 1.0)
    with pytest.raises(ValueError):
        FeedWeather(ROWS, -1.0)
