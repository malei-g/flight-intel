from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import list_sessions, load_session_flights, price_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/sessions", summary="历史抓取会话列表")
def get_sessions(
    origin: str = Query(default="PVG"),
    destination: str = Query(default="DTW"),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict]:
    return list_sessions(origin.upper(), destination.upper(), limit)


@router.get("/sessions/{session_id}", summary="某次会话的航班快照")
def get_session_flights(session_id: int) -> list[dict]:
    return load_session_flights(session_id)


@router.get("/price-trend", summary="历史最低价 / 均价趋势")
def get_price_trend(
    origin: str = Query(default="PVG"),
    destination: str = Query(default="DTW"),
    depart_date: str = Query(default=""),
    top_n: int = Query(default=5, ge=1, le=20),
) -> list[dict]:
    from datetime import datetime, timedelta
    if not depart_date:
        depart_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    return price_history(origin.upper(), destination.upper(), depart_date, top_n)
