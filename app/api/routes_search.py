from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.db import save_session, historical_avg_price
from app.schemas import SearchConfig, ScoredFlight
from app.services.flight_fetcher import fetch_flights
from app.services.recommender import recommend
from app.services.scorer import ScoringWeights

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[ScoredFlight], summary="搜索并评分航班（结果自动入库）")
def search_flights(
    origin: str = Query(default="PVG", min_length=3, max_length=3),
    destination: str = Query(default="DTW", min_length=3, max_length=3),
    depart_date: str = Query(default="", description="YYYY-MM-DD，留空 = 今天+30天"),
    passengers: int = Query(default=1, ge=1, le=9),
    top_n: int = Query(default=settings.default_top_n, ge=1, le=100),
    w_price: float = Query(default=0.40, ge=0, le=1),
    w_duration: float = Query(default=0.25, ge=0, le=1),
    w_stops: float = Query(default=0.20, ge=0, le=1),
    w_transfer_risk: float = Query(default=0.10, ge=0, le=1),
    w_time_comfort: float = Query(default=0.05, ge=0, le=1),
) -> list[ScoredFlight]:
    if not depart_date:
        depart_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        datetime.strptime(depart_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="depart_date must be YYYY-MM-DD")

    total_w = w_price + w_duration + w_stops + w_transfer_risk + w_time_comfort
    if abs(total_w - 1.0) > 0.05:
        raise HTTPException(status_code=422, detail=f"Weights must sum to ~1.0, got {total_w:.3f}")

    config = SearchConfig(
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date,
        passengers=passengers,
    )
    try:
        flights = fetch_flights(config)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    weights = ScoringWeights(
        price=w_price, duration=w_duration, stops=w_stops,
        transfer_risk=w_transfer_risk, time_comfort=w_time_comfort,
    )
    hist_avg = historical_avg_price(config.origin, config.destination, config.depart_date)
    scored = recommend(flights, top_n=len(flights), weights=weights, hist_avg_price=hist_avg)

    try:
        session_id = save_session(config, scored)
        logger.info("saved session %d (%d flights)", session_id, len(scored))
    except Exception as exc:
        logger.warning("db save failed (non-fatal): %s", exc)

    return scored[:top_n]
