"""
adjacent_baseline — 并行抓取目标日期 ±3 天作为冷启动价格基线。

仅在 historical_avg_price() 返回 None（首次查询该路线）时调用。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from app.providers.fast_flights_provider import fetch_google_flights

logger = logging.getLogger(__name__)

_ADJACENT_DAYS = [-3, -2, -1, 1, 2, 3]
_TIMEOUT_SEC = 12


def fetch_adjacent_baseline(
    origin: str,
    destination: str,
    depart_date: str,
    top_n: int = 5,
) -> float | None:
    """
    并行查询 depart_date ±3 天的航班，取各日 Top-N 最低价的均值作为基线。

    Args:
        top_n: 每个日期取最低的 N 条票价参与均值计算。

    Returns:
        float — 跨日均价基线；若所有并行请求均失败则返回 None。
    """
    base = datetime.strptime(depart_date, "%Y-%m-%d")
    dates = [
        (base + timedelta(days=d)).strftime("%Y-%m-%d")
        for d in _ADJACENT_DAYS
    ]

    def _fetch_one(date: str) -> list[float]:
        try:
            flights = fetch_google_flights(origin, destination, date)
            prices = sorted(f.price_usd for f in flights if f.price_usd > 0)
            return prices[:top_n]
        except Exception as exc:
            logger.debug("adjacent fetch failed for %s: %s", date, exc)
            return []

    all_prices: list[float] = []
    with ThreadPoolExecutor(max_workers=len(dates)) as pool:
        futures = {pool.submit(_fetch_one, d): d for d in dates}
        for future in as_completed(futures, timeout=_TIMEOUT_SEC):
            try:
                all_prices.extend(future.result())
            except Exception:
                pass

    if not all_prices:
        logger.warning("adjacent_baseline: no prices collected for %s→%s ±3d", origin, destination)
        return None

    baseline = sum(all_prices) / len(all_prices)
    logger.info(
        "adjacent_baseline: %s→%s (%s±3d) n=%d avg=$%.0f",
        origin, destination, depart_date, len(all_prices), baseline,
    )
    return baseline
