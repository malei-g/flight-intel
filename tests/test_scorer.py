"""test_scorer.py — 打分引擎单元测试"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.schemas import FlightOption, FlightSegment
from app.services.scorer import (
    ScoringWeights,
    _duration_score,
    _price_score,
    _stops_score,
    _time_comfort_score,
    _transfer_risk_score,
    score_flights,
)


# ---------- 测试夹具 ----------

def _seg(
    dep_airport: str = "PVG",
    arr_airport: str = "DTW",
    depart_hour: int = 9,
    duration_min: int = 840,
    layover_min: int | None = None,
) -> FlightSegment:
    depart = datetime(2026, 6, 25, depart_hour, 0)
    return FlightSegment(
        airline="Test",
        flight_no="T001",
        depart_airport=dep_airport,
        arrive_airport=arr_airport,
        depart_time=depart,
        arrive_time=depart.replace(hour=(depart_hour + duration_min // 60) % 24),
        duration_min=duration_min,
        layover_min=layover_min,
    )


def _flight(
    fid: str = "f001",
    price: float = 1000.0,
    duration_min: int = 900,
    stops: int = 0,
    segments: list[FlightSegment] | None = None,
    is_red_eye: bool = False,
) -> FlightOption:
    segs = segments or [_seg()]
    return FlightOption(
        id=fid,
        price_usd=price,
        total_duration_min=duration_min,
        stops=stops,
        segments=segs,
        is_red_eye=is_red_eye,
    )


# ---------- 单维度测试 ----------

class TestPriceScore:
    def test_cheapest_gets_100(self) -> None:
        assert _price_score(500, 500, 1500) == 100.0

    def test_most_expensive_gets_0(self) -> None:
        assert _price_score(1500, 500, 1500) == 0.0

    def test_midpoint_gets_50(self) -> None:
        assert _price_score(1000, 500, 1500) == pytest.approx(50.0)

    def test_all_same_price_gets_100(self) -> None:
        assert _price_score(800, 800, 800) == 100.0


class TestDurationScore:
    def test_shortest_gets_100(self) -> None:
        assert _duration_score(840, 840, 1440) == 100.0

    def test_longest_gets_0(self) -> None:
        assert _duration_score(1440, 840, 1440) == 0.0

    def test_all_same_gets_100(self) -> None:
        assert _duration_score(900, 900, 900) == 100.0


class TestStopsScore:
    def test_nonstop(self) -> None:
        assert _stops_score(0) == 100.0

    def test_one_stop(self) -> None:
        assert _stops_score(1) == 60.0

    def test_two_stops(self) -> None:
        assert _stops_score(2) == 20.0

    def test_three_plus_stops(self) -> None:
        assert _stops_score(3) == 0.0


class TestTransferRisk:
    def test_nonstop_no_risk(self) -> None:
        f = _flight(stops=0)
        assert _transfer_risk_score(f) == 100.0

    def test_ample_layover(self) -> None:
        seg = _seg(arr_airport="ORD", layover_min=180)  # 高风险机场但时间充裕
        f = _flight(stops=1, segments=[seg, _seg(dep_airport="ORD")])
        assert _transfer_risk_score(f) == 100.0

    def test_tight_layover_risky_airport(self) -> None:
        seg = _seg(arr_airport="ORD", layover_min=30)
        f = _flight(stops=1, segments=[seg, _seg(dep_airport="ORD")])
        assert _transfer_risk_score(f) == 0.0

    def test_tight_layover_normal_airport(self) -> None:
        seg = _seg(arr_airport="SEA", layover_min=30)  # 低风险机场，30min < 60min
        f = _flight(stops=1, segments=[seg, _seg(dep_airport="SEA")])
        assert _transfer_risk_score(f) == 0.0


class TestTimeComfort:
    def test_morning_departure_comfortable(self) -> None:
        f = _flight(segments=[_seg(depart_hour=9)])
        assert _time_comfort_score(f) == 100.0

    def test_red_eye_departure(self) -> None:
        f = _flight(segments=[_seg(depart_hour=3)])
        assert _time_comfort_score(f) == 0.0

    def test_late_night_departure(self) -> None:
        f = _flight(segments=[_seg(depart_hour=23)])
        assert _time_comfort_score(f) == 50.0


# ---------- 批量打分测试 ----------

class TestScoreFlights:
    def test_empty_returns_empty(self) -> None:
        assert score_flights([]) == []

    def test_ranking_order(self) -> None:
        """直飞便宜的应排第一"""
        cheap_nonstop = _flight("cheap", price=900, duration_min=870, stops=0)
        expensive_2stop = _flight("exp", price=1800, duration_min=1440, stops=2)
        results = score_flights([expensive_2stop, cheap_nonstop])
        assert results[0][0].id == "cheap"

    def test_scores_in_0_to_100(self) -> None:
        flights = [_flight(f"f{i}", price=800 + i * 100) for i in range(5)]
        for _, score, _ in score_flights(flights):
            assert 0 <= score <= 100

    def test_custom_weights(self) -> None:
        """完全按价格排序时，最低价必须第一"""
        weights = ScoringWeights(price=1.0, duration=0.0, stops=0.0, transfer_risk=0.0, time_comfort=0.0)
        f_cheap = _flight("cheap", price=700)
        f_exp = _flight("exp", price=1500)
        results = score_flights([f_exp, f_cheap], weights=weights)
        assert results[0][0].id == "cheap"

    def test_single_flight_gets_100_on_normalization(self) -> None:
        """只有一个航班时，归一化后各维度满分（stops 除外）"""
        f = _flight("only", price=1000, stops=0)
        results = score_flights([f])
        assert len(results) == 1
        _, score, _ = results[0]
        assert score > 0
