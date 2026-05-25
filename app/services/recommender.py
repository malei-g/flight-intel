from __future__ import annotations

from app.schemas import FlightOption, ScoreBreakdown, ScoredFlight
from app.services.scorer import ScoringWeights, score_flights

# 价格下跌阈值：当前价低于历史均价超过此比例 → BUY 信号加分
_PRICE_DROP_BUY_PCT = 0.10   # -10% 即触发 BUY
# 价格上涨阈值：当前价高于历史均价超过此比例 → 降为 WAIT/SKIP
_PRICE_SURGE_PCT    = 0.15   # +15% 视为偏贵


def _build_reason(
    flight: FlightOption,
    breakdown: ScoreBreakdown,
    rank: int,
    min_price: float,
    hist_avg: float | None,
) -> str:
    parts: list[str] = []

    price_diff_pct = (flight.price_usd - min_price) / min_price * 100 if min_price > 0 else 0
    if price_diff_pct <= 5:
        parts.append(f"价格接近最低价（${flight.price_usd:.0f}）")
    elif price_diff_pct <= 20:
        parts.append(f"价格合理（高于最低价 {price_diff_pct:.0f}%）")
    else:
        parts.append(f"价格偏高（高于最低价 {price_diff_pct:.0f}%）")

    # 历史对比提示
    if hist_avg is not None:
        diff_vs_hist = (flight.price_usd - hist_avg) / hist_avg * 100
        if diff_vs_hist <= -_PRICE_DROP_BUY_PCT * 100:
            parts.append(f"低于历史均价 {abs(diff_vs_hist):.0f}%，价格较好")
        elif diff_vs_hist >= _PRICE_SURGE_PCT * 100:
            parts.append(f"高于历史均价 {diff_vs_hist:.0f}%，可等待")

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


def _buy_or_wait(
    score: float,
    rank: int,
    price: float,
    hist_avg: float | None,
) -> str:
    """
    决策逻辑（优先级从高到低）：
    1. 有历史基线时，价格显著低于均价 → BUY
    2. 有历史基线时，价格显著高于均价 → SKIP
    3. 无历史基线时，回退到评分规则
    """
    if hist_avg is not None:
        ratio = price / hist_avg
        if ratio <= 1 - _PRICE_DROP_BUY_PCT and score >= 55:
            return "BUY"
        if ratio >= 1 + _PRICE_SURGE_PCT:
            return "SKIP"
        # 价格在历史正常区间内 → 看评分
        return "BUY" if score >= 70 and rank == 1 else "WAIT"

    # 无历史数据：保留原逻辑
    if score >= 75 and rank == 1:
        return "BUY"
    if score >= 60:
        return "WAIT"
    return "SKIP"


def recommend(
    flights: list[FlightOption],
    top_n: int = 5,
    weights: ScoringWeights | None = None,
    hist_avg_price: float | None = None,
) -> list[ScoredFlight]:
    """对航班列表打分并返回 Top N 推荐结果。

    Args:
        hist_avg_price: 历史 Top-5 均价基线（由调用方从 DB 查询后传入）。
                        传 None 时退化为原规则逻辑。
    """
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
                recommend_reason=_build_reason(
                    flight, breakdown, rank, min_price, hist_avg_price
                ),
                buy_or_wait=_buy_or_wait(score, rank, flight.price_usd, hist_avg_price),
                breakdown=breakdown,
            )
        )
    return results
