"""
flight_fetcher — 统一抓取接口（Google Flights via fast-flights）
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
    失败时抛出 RuntimeError，由调用方处理。
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
