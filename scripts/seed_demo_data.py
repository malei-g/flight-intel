"""
生成 20 条 mock 航班数据（上海 PVG → 底特律 DTW），
写入 data/raw/demo_flights.json，无需真实网络请求。
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from app.schemas import FlightOption, FlightSegment

random.seed(42)

DEPART_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

_AIRLINES = ["Air China", "United", "Delta", "American", "Cathay Pacific", "Korean Air"]
_HUB_AIRPORTS = ["LAX", "ORD", "SFO", "SEA", "ICN", "HKG", "NRT"]

# (stops, price_range, duration_range_h, layover_min_range)
_TEMPLATES = [
    (0, (1800, 2200), (14, 16), None),          # 直飞（罕见）
    (1, (900,  1400), (16, 22), (70, 180)),      # 一次中转（主流）
    (1, (750,  1000), (20, 26), (45, 90)),       # 一次中转（便宜但中转紧）
    (2, (600,  850),  (26, 34), (55, 120)),      # 两次中转
]

# 直飞极少，大多数为一次中转
_WEIGHTS = [2, 8, 6, 4]


def _make_segment(
    airline: str,
    flight_num: int,
    dep_airport: str,
    arr_airport: str,
    depart: datetime,
    duration_min: int,
    layover_min: int | None,
) -> FlightSegment:
    return FlightSegment(
        airline=airline,
        flight_no=f"{airline[:2].upper()}{flight_num}",
        depart_airport=dep_airport,
        arrive_airport=arr_airport,
        depart_time=depart,
        arrive_time=depart + timedelta(minutes=duration_min),
        duration_min=duration_min,
        layover_min=layover_min,
    )


def _make_flight(idx: int) -> FlightOption:
    template = random.choices(_TEMPLATES, weights=_WEIGHTS, k=1)[0]
    stops, price_range, dur_range_h, layover_range = template

    price = round(random.uniform(*price_range), 2)
    total_dur = random.randint(dur_range_h[0] * 60, dur_range_h[1] * 60)

    depart_hour = random.choice([7, 8, 9, 10, 11, 14, 15, 16, 22, 23, 0])
    depart_dt = datetime.strptime(DEPART_DATE, "%Y-%m-%d").replace(hour=depart_hour, minute=random.choice([0, 15, 30, 45]))
    is_red_eye = depart_hour in (22, 23, 0)

    airline = random.choice(_AIRLINES)

    if stops == 0:
        segs = [_make_segment(airline, 1000 + idx, "PVG", "DTW", depart_dt, total_dur, None)]
    elif stops == 1:
        hub = random.choice(_HUB_AIRPORTS)
        layover = random.randint(*layover_range)
        seg1_dur = total_dur - layover - random.randint(180, 360)
        seg2_dur = total_dur - seg1_dur - layover
        seg1_dur = max(seg1_dur, 60)
        seg2_dur = max(seg2_dur, 60)
        arr1 = depart_dt + timedelta(minutes=seg1_dur)
        dep2 = arr1 + timedelta(minutes=layover)
        segs = [
            _make_segment(airline, 1000 + idx, "PVG", hub, depart_dt, seg1_dur, layover),
            _make_segment(airline, 2000 + idx, hub, "DTW", dep2, seg2_dur, None),
        ]
    else:  # stops == 2
        hubs = random.sample(_HUB_AIRPORTS, 2)
        layover1 = random.randint(*layover_range)
        layover2 = random.randint(*layover_range)
        remaining = total_dur - layover1 - layover2
        seg1_dur = remaining // 3
        seg2_dur = remaining // 3
        seg3_dur = remaining - seg1_dur - seg2_dur
        arr1 = depart_dt + timedelta(minutes=seg1_dur)
        dep2 = arr1 + timedelta(minutes=layover1)
        arr2 = dep2 + timedelta(minutes=seg2_dur)
        dep3 = arr2 + timedelta(minutes=layover2)
        segs = [
            _make_segment(airline, 1000 + idx, "PVG", hubs[0], depart_dt, seg1_dur, layover1),
            _make_segment(airline, 2000 + idx, hubs[0], hubs[1], dep2, seg2_dur, layover2),
            _make_segment(airline, 3000 + idx, hubs[1], "DTW", dep3, seg3_dur, None),
        ]

    return FlightOption(
        id=f"demo_{idx:03d}",
        price_usd=price,
        total_duration_min=total_dur,
        stops=stops,
        segments=segs,
        is_red_eye=is_red_eye,
        source="demo",
    )


def main() -> None:
    out_dir = Path(__file__).parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "demo_flights.json"

    flights = [_make_flight(i) for i in range(20)]
    payload = [f.model_dump(mode="json") for f in flights]

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)

    print(f"Generated {len(flights)} demo flights → {out_path}")
    for f in flights:
        print(f"  {f.id}  stops={f.stops}  ${f.price_usd:.0f}  {f.total_duration_min//60}h{f.total_duration_min%60:02d}m")


if __name__ == "__main__":
    main()
