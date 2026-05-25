"""
flight_fetcher — 统一抓取接口，支持 provider 切换：
  demo    : 读取 data/raw/demo_flights.json
  google  : fast-flights 真实查询
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from app.schemas import FlightOption, SearchConfig

logger = logging.getLogger(__name__)

_DEMO_PATH = Path(__file__).parent.parent.parent / "data" / "raw" / "demo_flights.json"


def _load_demo() -> list[FlightOption]:
    raw = json.loads(_DEMO_PATH.read_text())
    return [FlightOption(**f) for f in raw]


def fetch_flights(
    config: SearchConfig,
    provider: Optional[str] = None,
    max_stops: Optional[int] = None,
) -> list[FlightOption]:
    """
    根据 provider 拉取航班列表。
    provider 优先级: 参数 > 环境变量 FLIGHT_PROVIDER > 'demo'
    """
    p = (provider or os.getenv("FLIGHT_PROVIDER", "demo")).lower()

    if p == "google":
        from app.providers.fast_flights_provider import fetch_google_flights
        flights = fetch_google_flights(
            origin=config.origin,
            destination=config.destination,
            depart_date=config.depart_date,
            passengers=config.passengers,
            max_stops=max_stops,
        )
        if not flights:
            logger.warning("google provider returned 0 flights, falling back to demo")
            return _load_demo()
        return flights

    # default: demo
    return _load_demo()
