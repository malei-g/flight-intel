from __future__ import annotations

from app.schemas import FlightOption, ScoreBreakdown, ScoredFlight
from app.services.scorer import ScoringWeights, score_flights


def _build_reason(
    flight: FlightOption,
    breakdown: ScoreBreakdown,
    rank: int,
    min_price: float,
) -> str:
    parts: list[str] = []

    price_diff_pct = (flight.price_usd - min_price) / min_price * 100 if min_price > 0 else 0
    if price_diff_pct <= 5:
        parts.append(f"价格接近最低价（${flight.price_usd:.0f}）")
    elif price_diff_pct <= 20:
        parts.append(f"价格合理（高于最低价 {price_diff_pct:.0f}%）")
    else:
        parts.append(f"价格偏高（高于最低价 {price_diff_pct:.0f}%）")

    hours, mins = divmod(flight.total_duration_min, 60)
    if flight.stops == 0:
        parts.append(f"直飞 {hours}h{mins:02d}m")
    else:
        parts.append(f"{flight.stops} 次中转，总时长 {hours}h{mins:02d}m")

    if breakdown.time_comfort_score == 100:
        parts.append("起飞时间舒适")
    elif breakdown.time_comfort_score == 0:
        parts.append("红眼航班")

    if breakdown.transfer_risk_score < 50 and flight.stops > 0:
        parts.append("中转时间紧张，注意赶机风险")

    return "；".join(parts)


def _buy_or_wait(score: float, rank: int, total: int) -> str:
    if score >= 75 and rank == 1:
        return "BUY"
    if score >= 60:
        return "WAIT"
    return "SKIP"


def recommend(
    flights: list[FlightOption],
    top_n: int = 5,
    weights: ScoringWeights | None = None,
) -> list[ScoredFlight]:
    """对航班列表打分并返回 Top N 推荐结果。"""
    if not flights:
        return []

    scored = score_flights(flights, weights)
    min_price = min(f.price_usd for f in flights)
    total = len(scored)

    results: list[ScoredFlight] = []
    for rank, (flight, score, breakdown) in enumerate(scored[:top_n], start=1):
        results.append(
            ScoredFlight(
                flight=flight,
                score=score,
                rank=rank,
                recommend_reason=_build_reason(flight, breakdown, rank, min_price),
                buy_or_wait=_buy_or_wait(score, rank, total),
                breakdown=breakdown,
            )
        )
    return results
