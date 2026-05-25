"""
flight_fetcher — 统一抓取接口（仅 Google Flights 真实数据）
抓取完成后自动写入 SQLite。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.schemas import FlightOption, SearchConfig

logger = logging.getLogger(__name__)


def fetch_flights(
    config: SearchConfig,
    max_stops: Optional[int] = None,
) -> list[FlightOption]:
    """
    查询 Google Flights，返回去重后的 FlightOption 列表。
    同时将本次结果持久化到 SQLite。
    失败时抛出异常，由调用方处理。
    """
    from app.providers.fast_flights_provider import fetch_google_flights
    flights = fetch_google_flights(
        origin=config.origin,
        destination=config.destination,
        depart_date=config.depart_date,
        passengers=config.passengers,
        max_stops=max_stops,
    )
    if not flights:
        raise RuntimeError(
            f"Google Flights returned 0 results for "
            f"{config.origin}→{config.destination} on {config.depart_date}"
        )
    return flights
