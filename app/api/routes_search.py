from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.schemas import (
    ScoreBreakdown,
    ScoredFlight,
    SearchRequest,
)
from app.services.flight_fetcher import fetch_flights
from app.services.recommender import recommend
from app.services.scorer import ScoringWeights
from app.schemas import SearchConfig

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[ScoredFlight], summary="搜索并评分航班")
def search_flights(
    origin: str = Query(default="PVG", min_length=3, max_length=3, description="出发机场 IATA 代码"),
    destination: str = Query(default="DTW", min_length=3, max_length=3, description="目的地机场 IATA 代码"),
    depart_date: str = Query(
        default="",
        description="出发日期 YYYY-MM-DD，留空则为今天起 30 天",
    ),
    passengers: int = Query(default=1, ge=1, le=9),
    top_n: int = Query(default=settings.default_top_n, ge=1, le=100),
    provider: Optional[str] = Query(default=None, description="demo | google，留空用环境变量"),
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
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to ~1.0, got {total_w:.3f}",
        )

    config = SearchConfig(
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date,
        passengers=passengers,
    )
    flights = fetch_flights(config, provider=provider or settings.flight_provider)
    if not flights:
        raise HTTPException(status_code=503, detail="No flights returned from provider")

    weights = ScoringWeights(
        price=w_price,
        duration=w_duration,
        stops=w_stops,
        transfer_risk=w_transfer_risk,
        time_comfort=w_time_comfort,
    )
    return recommend(flights, top_n=top_n, weights=weights)
