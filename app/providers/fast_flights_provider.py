"""
fast-flights provider — 将 fast_flights.Flight 转换为项目内部 FlightOption
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fast_flights import FlightData, Passengers, get_flights
from fast_flights.schema import Flight as FFlight

from app.schemas import FlightOption, FlightSegment

logger = logging.getLogger(__name__)

# "14 hr 30 min" / "2 hr" / "45 min"
_DUR_RE = re.compile(r"(?:(\d+)\s*hr)?\s*(?:(\d+)\s*min)?")
# "$1,234" / "1234"
_PRICE_RE = re.compile(r"[\$,]")
# "3:55 PM on Wed, Jun 24" — 不含年份，需注入
_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2}\s*[AP]M)\s+on\s+\w+,\s+(\w+\s+\d{1,2})",
    re.IGNORECASE,
)


def _parse_duration(s: str) -> int:
    """'14 hr 30 min' → 870 (分钟)"""
    m = _DUR_RE.fullmatch(s.strip())
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    mins  = int(m.group(2) or 0)
    return hours * 60 + mins


def _parse_price(s: str) -> float:
    """'$1,234' → 1234.0"""
    cleaned = _PRICE_RE.sub("", s).strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_time(time_str: str, base_year: int) -> Optional[datetime]:
    """
    '3:55 PM on Wed, Jun 24' → datetime(base_year, 6, 24, 15, 55)
    arrival_time_ahead (+1 day) 由调用方处理。
    """
    m = _TIME_RE.search(time_str)
    if not m:
        return None
    try:
        raw = f"{m.group(2)} {base_year} {m.group(1)}"
        return datetime.strptime(raw, "%b %d %Y %I:%M %p")
    except ValueError:
        return None


def _ff_to_option(ff: FFlight, idx: int, depart_date_str: str) -> Optional[FlightOption]:
    """把一条 fast_flights.Flight 转成 FlightOption。"""
    price = _parse_price(ff.price)
    if price <= 0:
        return None

    dur_min = _parse_duration(ff.duration)
    if dur_min <= 0:
        return None

    year = int(depart_date_str[:4])

    dep_dt = _parse_time(ff.departure, year)
    arr_dt = _parse_time(ff.arrival, year)

    # arrival_time_ahead 如 "+1" 表示跨天
    days_ahead = 0
    ahead = (ff.arrival_time_ahead or "").strip()
    if ahead.startswith("+"):
        try:
            days_ahead = int(ahead[1:])
        except ValueError:
            pass

    if dep_dt and arr_dt:
        arr_dt = arr_dt + timedelta(days=days_ahead)
        # 到达比出发还早 → 跨年边缘，再加一年保护
        if arr_dt < dep_dt:
            arr_dt = arr_dt.replace(year=arr_dt.year + 1)
    else:
        dep_dt = dep_dt or datetime.strptime(depart_date_str, "%Y-%m-%d").replace(hour=8)
        arr_dt = dep_dt + timedelta(minutes=dur_min)

    is_red_eye = dep_dt.hour >= 22 or dep_dt.hour <= 4

    # 航司名：多航司用 " / " 分隔
    airline = ff.name.replace(", ", " / ")

    # 构造单段 Segment（fast-flights 不拆分段信息）
    seg = FlightSegment(
        airline=airline,
        flight_no=f"FF{idx:04d}",
        depart_airport="PVG",
        arrive_airport="DTW",
        depart_time=dep_dt,
        arrive_time=arr_dt,
        duration_min=dur_min,
        layover_min=None,
    )

    return FlightOption(
        id=f"ff_{idx:04d}",
        price_usd=price,
        total_duration_min=dur_min,
        stops=ff.stops,
        segments=[seg],
        is_red_eye=is_red_eye,
        source="google",
    )


def fetch_google_flights(
    origin: str,
    destination: str,
    depart_date: str,
    passengers: int = 1,
    max_stops: Optional[int] = None,
) -> list[FlightOption]:
    """
    调用 fast-flights 拉取真实数据，返回转换后的 FlightOption 列表。
    失败时返回空列表（调用方应 fallback 到 demo）。
    """
    logger.info("fast-flights query: %s→%s on %s", origin, destination, depart_date)
    try:
        result = get_flights(
            flight_data=[
                FlightData(
                    date=depart_date,
                    from_airport=origin,
                    to_airport=destination,
                    max_stops=max_stops,
                )
            ],
            trip="one-way",
            seat="economy",
            passengers=Passengers(adults=passengers),
        )
    except Exception as exc:
        logger.error("fast-flights fetch failed: %s", exc)
        return []

    logger.info("raw flights returned: %d  price_level=%s", len(result.flights), result.current_price)

    options: list[FlightOption] = []
    for idx, ff in enumerate(result.flights):
        opt = _ff_to_option(ff, idx, depart_date)
        if opt:
            options.append(opt)

    # 去重：相同价格+时长+stops 只保留一条（fast-flights 有大量重复）
    seen: set[tuple[float, int, int]] = set()
    deduped: list[FlightOption] = []
    for opt in options:
        key = (opt.price_usd, opt.total_duration_min, opt.stops)
        if key not in seen:
            seen.add(key)
            deduped.append(opt)

    logger.info("after dedup: %d unique flights", len(deduped))
    return deduped
