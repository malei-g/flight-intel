"""test_recommender.py — recommender._buy_or_wait 及 recommend() 历史均价逻辑测试"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.schemas import FlightOption, FlightSegment
from app.services.recommender import _buy_or_wait, recommend
from app.services.scorer import ScoringWeights


# ---------- 夹具 ----------

def _seg(depart_hour: int = 9, duration_min: int = 840) -> FlightSegment:
    dep = datetime(2026, 6, 25, depart_hour, 0)
    return FlightSegment(
        airline="TestAir", flight_no="T001",
        depart_airport="PVG", arrive_airport="DTW",
        depart_time=dep,
        arrive_time=dep.replace(hour=(depart_hour + duration_min // 60) % 24),
        duration_min=duration_min,
    )


def _flight(fid: str = "f1", price: float = 1000.0, stops: int = 0) -> FlightOption:
    return FlightOption(
        id=fid, price_usd=price, total_duration_min=840,
        stops=stops, segments=[_seg()],
    )


# ---------- _buy_or_wait：无历史基线（原逻辑回退）----------

class TestBuyOrWaitNoHistory:
    def test_high_score_rank1_buys(self) -> None:
        assert _buy_or_wait(score=80, rank=1, price=1000, hist_avg=None) == "BUY"

    def test_high_score_not_rank1_waits(self) -> None:
        assert _buy_or_wait(score=80, rank=2, price=1000, hist_avg=None) == "WAIT"

    def test_medium_score_waits(self) -> None:
        assert _buy_or_wait(score=65, rank=1, price=1000, hist_avg=None) == "WAIT"

    def test_low_score_skips(self) -> None:
        assert _buy_or_wait(score=40, rank=3, price=1000, hist_avg=None) == "SKIP"


# ---------- _buy_or_wait：有历史基线 ----------

class TestBuyOrWaitWithHistory:
    def test_price_well_below_hist_avg_buys(self) -> None:
        # 当前价 800，均价 1000 → -20%，超过 -10% 阈值 → BUY
        assert _buy_or_wait(score=60, rank=2, price=800, hist_avg=1000) == "BUY"

    def test_price_slightly_below_hist_avg_uses_score(self) -> None:
        # 当前价 950，均价 1000 → -5%，未超阈值，看评分
        # score=72 rank=1 → BUY
        assert _buy_or_wait(score=72, rank=1, price=950, hist_avg=1000) == "BUY"

    def test_price_slightly_below_hist_avg_rank2_waits(self) -> None:
        # score=65 rank=2 → WAIT
        assert _buy_or_wait(score=65, rank=2, price=950, hist_avg=1000) == "WAIT"

    def test_price_well_above_hist_avg_skips(self) -> None:
        # 当前价 1200，均价 1000 → +20%，超过 +15% 阈值 → SKIP
        assert _buy_or_wait(score=80, rank=1, price=1200, hist_avg=1000) == "SKIP"

    def test_price_at_hist_avg_uses_score(self) -> None:
        # 价格持平，看评分
        assert _buy_or_wait(score=71, rank=1, price=1000, hist_avg=1000) == "BUY"
        assert _buy_or_wait(score=55, rank=2, price=1000, hist_avg=1000) == "WAIT"

    def test_low_score_price_drop_still_buys(self) -> None:
        # 价格大幅下跌但 score < 55 → 不触发 BUY（防止垃圾航班被推荐）
        assert _buy_or_wait(score=40, rank=3, price=800, hist_avg=1000) != "BUY"


# ---------- recommend()：hist_avg_price 端到端 ----------

class TestRecommendWithHistory:
    def test_no_history_returns_results(self) -> None:
        flights = [_flight("f1", 1000), _flight("f2", 1200)]
        result = recommend(flights, top_n=2, hist_avg_price=None)
        assert len(result) == 2

    def test_cheap_flight_gets_buy_with_history(self) -> None:
        # f1 价格比历史均价低 20%
        flights = [_flight("f1", price=800), _flight("f2", price=1000)]
        result = recommend(flights, top_n=2, hist_avg_price=1000.0)
        top = result[0]
        assert top.flight.id == "f1"
        assert top.buy_or_wait == "BUY"

    def test_expensive_flight_gets_skip_with_history(self) -> None:
        # 只有一个价格远高于历史均价的航班
        flights = [_flight("f1", price=1200)]
        result = recommend(flights, top_n=1, hist_avg_price=1000.0)
        assert result[0].buy_or_wait == "SKIP"

    def test_reason_contains_hist_context_when_cheap(self) -> None:
        flights = [_flight("f1", price=800), _flight("f2", price=1000)]
        result = recommend(flights, top_n=1, hist_avg_price=1000.0)
        assert "历史均价" in result[0].recommend_reason

    def test_reason_contains_hist_context_when_expensive(self) -> None:
        flights = [_flight("f1", price=1200), _flight("f2", price=1000)]
        result = recommend(flights, top_n=2, hist_avg_price=1000.0)
        expensive = next(r for r in result if r.flight.id == "f1")
        assert "历史均价" in expensive.recommend_reason

    def test_no_hist_context_in_reason_when_none(self) -> None:
        flights = [_flight("f1", price=800)]
        result = recommend(flights, top_n=1, hist_avg_price=None)
        assert "历史均价" not in result[0].recommend_reason
