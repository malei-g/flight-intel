"""tests/test_adjacent_baseline.py — adjacent_baseline 单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.adjacent_baseline import fetch_adjacent_baseline, _ADJACENT_DAYS


def _make_flight(price: float):
    f = MagicMock()
    f.price_usd = price
    return f


class TestFetchAdjacentBaseline:
    def test_returns_avg_of_top_n_prices(self):
        """6 天各返回 3 条；top_n=2 → 每天取最低 2 条，共 12 条均值。"""
        mock_flights = [_make_flight(p) for p in [500, 600, 700]]
        with patch(
            "app.services.adjacent_baseline.fetch_google_flights",
            return_value=mock_flights,
        ) as mock_fetch:
            result = fetch_adjacent_baseline("PVG", "DTW", "2026-06-20", top_n=2)

        assert mock_fetch.call_count == len(_ADJACENT_DAYS)
        # 每天 top_n=2 → [500, 600]；6天共 12 条，均值 = (500+600)*6/12 = 550
        assert result == pytest.approx(550.0)

    def test_returns_none_when_all_fail(self):
        with patch(
            "app.services.adjacent_baseline.fetch_google_flights",
            side_effect=RuntimeError("network error"),
        ):
            result = fetch_adjacent_baseline("PVG", "DTW", "2026-06-20")
        assert result is None

    def test_partial_failure_still_returns_avg(self):
        """部分日期失败时，用成功的数据计算均值。"""
        call_count = 0

        def _side_effect(origin, dest, date):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return [_make_flight(800.0)]
            raise RuntimeError("fail")

        with patch(
            "app.services.adjacent_baseline.fetch_google_flights",
            side_effect=_side_effect,
        ):
            result = fetch_adjacent_baseline("PVG", "DTW", "2026-06-20", top_n=5)

        assert result == pytest.approx(800.0)

    def test_queries_correct_adjacent_dates(self):
        """验证查询的 6 个日期相对 depart_date 的偏移正确。"""
        queried_dates: list[str] = []

        def _capture(origin, dest, date):
            queried_dates.append(date)
            return [_make_flight(1000.0)]

        with patch(
            "app.services.adjacent_baseline.fetch_google_flights",
            side_effect=_capture,
        ):
            fetch_adjacent_baseline("PVG", "DTW", "2026-06-20")

        assert sorted(queried_dates) == [
            "2026-06-17", "2026-06-18", "2026-06-19",
            "2026-06-21", "2026-06-22", "2026-06-23",
        ]

    def test_zero_price_flights_excluded(self):
        """price_usd=0 的航班不应计入均值。"""
        flights = [_make_flight(0.0), _make_flight(0.0), _make_flight(900.0)]
        with patch(
            "app.services.adjacent_baseline.fetch_google_flights",
            return_value=flights,
        ):
            result = fetch_adjacent_baseline("PVG", "DTW", "2026-06-20", top_n=5)
        # 每天只有 1 条有效价格 900，6 天均值仍是 900
        assert result == pytest.approx(900.0)
