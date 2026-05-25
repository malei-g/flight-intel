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

# 航司全称 → IATA 二字码（仅覆盖 PVG→DTW 常见承运人）
_AIRLINE_IATA: dict[str, str] = {
    "Air Canada":        "AC",
    "Air China":         "CA",
    "Air France":        "AF",
    "ANA":               "NH",
    "American":          "AA",
    "Cathay Pacific":    "CX",
    "China Airlines":    "CI",
    "China Eastern":     "MU",
    "Condor":            "DE",
    "Delta":             "DL",
    "JetBlue":           "B6",
    "Korean Air":        "KE",
    "Lufthansa":         "LH",
    "Turkish Airlines":  "TK",
    "United":            "UA",
    "WestJet":           "WS",
}


def _airline_code(name: str) -> str:
    """取航司名第一段（主承运人）的 IATA 二字码，未知航司返回首字母缩写。"""
    primary = name.split(",")[0].strip()
    if primary in _AIRLINE_IATA:
        return _AIRLINE_IATA[primary]
    # fallback：取每个单词首字母，最多 2 位
    initials = "".join(w[0].upper() for w in primary.split() if w)
    return initials[:2] or "XX"

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


def _ff_to_option(
    ff: FFlight,
    idx: int,
    depart_date_str: str,
    origin: str,
    destination: str,
) -> Optional[FlightOption]:
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
        # fast-flights 偶尔返回错误的到达时刻（如 PM/AM 混淆）
        # 若解析值与 duration 偏差 >30 min，以 duration 为准覆盖
        if abs((arr_dt - dep_dt).total_seconds() / 60 - dur_min) > 30:
            arr_dt = dep_dt + timedelta(minutes=dur_min)
    else:
        dep_dt = dep_dt or datetime.strptime(depart_date_str, "%Y-%m-%d").replace(hour=8)
        arr_dt = dep_dt + timedelta(minutes=dur_min)

    is_red_eye = dep_dt.hour >= 22 or dep_dt.hour <= 4

    # 航司名：多航司用 " / " 分隔；生成主承运人 IATA 代码
    airline = ff.name.replace(", ", " / ")
    iata = _airline_code(ff.name)
    flight_no = f"{iata}-{idx + 1:03d}"

    # 构造单段 Segment（fast-flights 不拆分段信息）
    seg = FlightSegment(
        airline=airline,
        flight_no=flight_no,
        depart_airport=origin.upper(),
        arrive_airport=destination.upper(),
        depart_time=dep_dt,
        arrive_time=arr_dt,
        duration_min=dur_min,
        layover_min=None,
    )

    return FlightOption(
        id=flight_no,
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
        opt = _ff_to_option(ff, idx, depart_date, origin, destination)
        if opt:
            options.append(opt)

    # 去重：相同价格+时长+stops+出发时刻 只保留一条
    seen: set[tuple[float, int, int, int]] = set()
    deduped: list[FlightOption] = []
    for opt in options:
        dep_hour = opt.segments[0].depart_time.hour if opt.segments else -1
        key = (opt.price_usd, opt.total_duration_min, opt.stops, dep_hour)
        if key not in seen:
            seen.add(key)
            deduped.append(opt)

    logger.info("after dedup: %d unique flights", len(deduped))
    return deduped
