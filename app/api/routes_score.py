from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import FlightOption, ScoreRequest, ScoredFlight
from app.services.recommender import recommend
from app.services.scorer import ScoringWeights

router = APIRouter(prefix="/score", tags=["score"])


@router.post("", response_model=list[ScoredFlight], summary="对传入的航班列表打分")
def score_flights(
    body: ScoreRequest,
    top_n: int = Query(default=10, ge=1, le=200),
    w_price: float = Query(default=0.40, ge=0, le=1),
    w_duration: float = Query(default=0.25, ge=0, le=1),
    w_stops: float = Query(default=0.20, ge=0, le=1),
    w_transfer_risk: float = Query(default=0.10, ge=0, le=1),
    w_time_comfort: float = Query(default=0.05, ge=0, le=1),
) -> list[ScoredFlight]:
    if not body.flights:
        raise HTTPException(status_code=422, detail="flights list is empty")

    total_w = w_price + w_duration + w_stops + w_transfer_risk + w_time_comfort
    if abs(total_w - 1.0) > 0.05:
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to ~1.0, got {total_w:.3f}",
        )

    weights = ScoringWeights(
        price=w_price,
        duration=w_duration,
        stops=w_stops,
        transfer_risk=w_transfer_risk,
        time_comfort=w_time_comfort,
    )
    return recommend(body.flights, top_n=top_n, weights=weights)
