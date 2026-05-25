"""test_provider.py — fast_flights_provider 单元测试"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.providers.fast_flights_provider import (
    _ff_to_option,
    _parse_duration,
    _parse_price,
    _parse_time,
    fetch_google_flights,
)


# ---------- 解析函数 ----------

class TestParseDuration:
    def test_hours_and_minutes(self) -> None:
        assert _parse_duration("14 hr 30 min") == 870

    def test_hours_only(self) -> None:
        assert _parse_duration("2 hr") == 120

    def test_minutes_only(self) -> None:
        assert _parse_duration("45 min") == 45

    def test_empty_returns_zero(self) -> None:
        assert _parse_duration("") == 0


class TestParsePrice:
    def test_dollar_sign_and_comma(self) -> None:
        assert _parse_price("$1,234") == 1234.0

    def test_plain_number(self) -> None:
        assert _parse_price("899") == 899.0

    def test_invalid_returns_zero(self) -> None:
        assert _parse_price("N/A") == 0.0


class TestParseTime:
    def test_valid_time(self) -> None:
        dt = _parse_time("3:55 PM on Wed, Jun 24", 2026)
        assert dt == datetime(2026, 6, 24, 15, 55)

    def test_invalid_returns_none(self) -> None:
        assert _parse_time("unknown", 2026) is None


# ---------- _ff_to_option 机场代码 ----------

def _make_ff(
    price: str = "$1,000",
    duration: str = "14 hr 30 min",
    stops: int = 1,
    departure: str = "9:00 AM on Mon, Jun 24",
    arrival: str = "11:30 PM on Mon, Jun 24",
    name: str = "Air Test",
    arrival_time_ahead: str = "",
) -> MagicMock:
    ff = MagicMock()
    ff.price = price
    ff.duration = duration
    ff.stops = stops
    ff.departure = departure
    ff.arrival = arrival
    ff.name = name
    ff.arrival_time_ahead = arrival_time_ahead
    return ff


class TestFfToOption:
    def test_airport_codes_passed_through(self) -> None:
        ff = _make_ff()
        opt = _ff_to_option(ff, 0, "2026-06-24", "SFO", "LHR")
        assert opt is not None
        assert opt.segments[0].depart_airport == "SFO"
        assert opt.segments[0].arrive_airport == "LHR"

    def test_airport_codes_uppercased(self) -> None:
        ff = _make_ff()
        opt = _ff_to_option(ff, 0, "2026-06-24", "pvg", "dtw")
        assert opt is not None
        assert opt.segments[0].depart_airport == "PVG"
        assert opt.segments[0].arrive_airport == "DTW"

    def test_invalid_price_returns_none(self) -> None:
        ff = _make_ff(price="N/A")
        assert _ff_to_option(ff, 0, "2026-06-24", "PVG", "DTW") is None

    def test_invalid_duration_returns_none(self) -> None:
        ff = _make_ff(duration="")
        assert _ff_to_option(ff, 0, "2026-06-24", "PVG", "DTW") is None

    def test_red_eye_detection(self) -> None:
        ff = _make_ff(departure="11:30 PM on Mon, Jun 24")
        opt = _ff_to_option(ff, 0, "2026-06-24", "PVG", "DTW")
        assert opt is not None
        assert opt.is_red_eye is True

    def test_daytime_not_red_eye(self) -> None:
        ff = _make_ff(departure="9:00 AM on Mon, Jun 24")
        opt = _ff_to_option(ff, 0, "2026-06-24", "PVG", "DTW")
        assert opt is not None
        assert opt.is_red_eye is False


# ---------- 去重逻辑 ----------

class TestDeduplication:
    def test_different_depart_hour_not_deduplicated(self) -> None:
        """相同价格+时长+stops 但不同出发时刻 → 保留两条"""
        ff1 = _make_ff(departure="9:00 AM on Mon, Jun 24")
        ff2 = _make_ff(departure="3:00 PM on Mon, Jun 24")

        fake_result = MagicMock()
        fake_result.flights = [ff1, ff2]
        fake_result.current_price = "typical"

        with patch("app.providers.fast_flights_provider.get_flights", return_value=fake_result):
            opts = fetch_google_flights("PVG", "DTW", "2026-06-24")

        assert len(opts) == 2

    def test_identical_flights_deduplicated(self) -> None:
        """完全相同的两条 → 只保留一条"""
        ff1 = _make_ff()
        ff2 = _make_ff()

        fake_result = MagicMock()
        fake_result.flights = [ff1, ff2]
        fake_result.current_price = "typical"

        with patch("app.providers.fast_flights_provider.get_flights", return_value=fake_result):
            opts = fetch_google_flights("PVG", "DTW", "2026-06-24")

        assert len(opts) == 1
