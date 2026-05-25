"""
打分引擎 — 规则模型 MVP
权重可通过环境变量覆盖（见 .env.example）
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.schemas import FlightOption, ScoreBreakdown

# 高风险转机机场（中转时间充裕要求更高）
_HIGH_RISK_AIRPORTS = {"ORD", "EWR", "LAX", "CDG", "AMS"}
# 最短安全中转时间（分钟）
_MIN_SAFE_LAYOVER = 60


@dataclass(frozen=True)
class ScoringWeights:
    price: float = float(os.getenv("WEIGHT_PRICE", "0.40"))
    duration: float = float(os.getenv("WEIGHT_DURATION", "0.25"))
    stops: float = float(os.getenv("WEIGHT_STOPS", "0.20"))
    transfer_risk: float = float(os.getenv("WEIGHT_TRANSFER_RISK", "0.10"))
    time_comfort: float = float(os.getenv("WEIGHT_TIME_COMFORT", "0.05"))


def _price_score(price: float, min_price: float, max_price: float) -> float:
    if max_price == min_price:
        return 100.0
    return (max_price - price) / (max_price - min_price) * 100


def _duration_score(dur: int, min_dur: int, max_dur: int) -> float:
    if max_dur == min_dur:
        return 100.0
    return (max_dur - dur) / (max_dur - min_dur) * 100


def _stops_score(stops: int) -> float:
    mapping = {0: 100.0, 1: 60.0, 2: 20.0}
    return mapping.get(stops, 0.0)


def _transfer_risk_score(flight: FlightOption) -> float:
    if flight.stops == 0:
        return 100.0
    scores: list[float] = []
    for seg in flight.segments[:-1]:
        layover = seg.layover_min or 0
        airport = seg.arrive_airport
        min_safe = _MIN_SAFE_LAYOVER * (1.5 if airport in _HIGH_RISK_AIRPORTS else 1.0)
        if layover < min_safe:
            s = 0.0
        elif layover < min_safe * 2:
            s = 50.0
        else:
            s = 100.0
        scores.append(s)
    return sum(scores) / len(scores) if scores else 100.0


def _time_comfort_score(flight: FlightOption) -> float:
    if not flight.segments:
        return 50.0
    depart_hour = flight.segments[0].depart_time.hour
    if 6 <= depart_hour <= 22:
        return 100.0
    if depart_hour in (23, 0, 1):
        return 50.0
    return 0.0


def score_flight(
    flight: FlightOption,
    min_price: float,
    max_price: float,
    min_dur: int,
    max_dur: int,
    weights: ScoringWeights | None = None,
) -> tuple[float, ScoreBreakdown]:
    """返回 (总分 0–100, 各维度分项)。"""
    w = weights or ScoringWeights()

    ps = _price_score(flight.price_usd, min_price, max_price)
    ds = _duration_score(flight.total_duration_min, min_dur, max_dur)
    ss = _stops_score(flight.stops)
    ts = _transfer_risk_score(flight)
    cs = _time_comfort_score(flight)

    total = ps * w.price + ds * w.duration + ss * w.stops + ts * w.transfer_risk + cs * w.time_comfort

    breakdown = ScoreBreakdown(
        price_score=round(ps, 1),
        duration_score=round(ds, 1),
        stops_score=round(ss, 1),
        transfer_risk_score=round(ts, 1),
        time_comfort_score=round(cs, 1),
    )
    return round(total, 1), breakdown


def score_flights(
    flights: list[FlightOption],
    weights: ScoringWeights | None = None,
) -> list[tuple[FlightOption, float, ScoreBreakdown]]:
    """批量打分，自动计算归一化所需的 min/max。"""
    if not flights:
        return []

    prices = [f.price_usd for f in flights]
    durs = [f.total_duration_min for f in flights]
    min_p, max_p = min(prices), max(prices)
    min_d, max_d = min(durs), max(durs)

    results = []
    for f in flights:
        total, breakdown = score_flight(f, min_p, max_p, min_d, max_d, weights)
        results.append((f, total, breakdown))

    return sorted(results, key=lambda x: x[1], reverse=True)
