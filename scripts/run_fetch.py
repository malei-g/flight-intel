"""
run_fetch.py — 拉取真实航班数据并打分，结果写入 data/processed/
用法: PYTHONPATH=. uv run python scripts/run_fetch.py [--provider demo|google] [--top 10]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import SearchConfig
from app.services.flight_fetcher import fetch_flights
from app.services.recommender import recommend

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch & score flights")
    parser.add_argument("--provider", default="google", choices=["demo", "google"])
    parser.add_argument("--origin", default="PVG")
    parser.add_argument("--dest", default="DTW")
    parser.add_argument("--days", type=int, default=30, help="Days from today")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    depart_date = (datetime.now() + timedelta(days=args.days)).strftime("%Y-%m-%d")
    config = SearchConfig(
        origin=args.origin,
        destination=args.dest,
        depart_date=depart_date,
    )

    logger.info("Fetching %s→%s on %s (provider=%s)", args.origin, args.dest, depart_date, args.provider)
    flights = fetch_flights(config, provider=args.provider)
    logger.info("Fetched %d unique flights", len(flights))

    scored = recommend(flights, top_n=len(flights))
    top = scored[: args.top]

    print(f"\n{'─'*90}")
    print(f"  PVG → DTW | {depart_date} | provider={args.provider} | {len(flights)} flights")
    print(f"{'─'*90}")
    print(f"{'#':<3} {'Score':>5} {'$':>6} {'Duration':>10} {'St':>3} {'Verdict':<6}  Airline / Reason")
    print(f"{'─'*90}")
    for sf in top:
        f = sf.flight
        h, m = divmod(f.total_duration_min, 60)
        airline = f.segments[0].airline if f.segments else "—"
        print(
            f"#{sf.rank:<2} {sf.score:>5.1f} ${f.price_usd:>5.0f} "
            f"{h:>3}h{m:02d}m {f.stops:>3}  {sf.buy_or_wait:<6}  "
            f"{airline[:28]:<28}  {sf.recommend_reason[:50]}"
        )
    print(f"{'─'*90}")

    # 写结果到 data/processed/
    out_dir = Path(__file__).parent.parent / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"scored_{args.provider}_{ts}.json"
    payload = [sf.model_dump(mode="json") for sf in scored]
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)
    logger.info("Saved %d scored flights → %s", len(scored), out_path)


if __name__ == "__main__":
    main()
