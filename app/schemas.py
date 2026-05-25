from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class SearchConfig:
    origin: str
    destination: str
    depart_date: str        # YYYY-MM-DD
    passengers: int = 1


class FlightSegment(BaseModel):
    airline: str
    flight_no: str
    depart_airport: str
    arrive_airport: str
    depart_time: datetime
    arrive_time: datetime
    duration_min: int
    layover_min: Optional[int] = None   # 下一段前的等待时间


class FlightOption(BaseModel):
    id: str
    price_usd: float
    total_duration_min: int
    stops: int                          # 0=直飞
    segments: list[FlightSegment]
    is_red_eye: bool = False
    source: str = "demo"                # demo | google | mcp


class ScoreBreakdown(BaseModel):
    price_score: float = Field(ge=0, le=100)
    duration_score: float = Field(ge=0, le=100)
    stops_score: float = Field(ge=0, le=100)
    transfer_risk_score: float = Field(ge=0, le=100)
    time_comfort_score: float = Field(ge=0, le=100)


class ScoredFlight(BaseModel):
    flight: FlightOption
    score: float = Field(ge=0, le=100)
    rank: int
    recommend_reason: str
    buy_or_wait: str                    # BUY | WAIT | SKIP
    breakdown: ScoreBreakdown


class SearchRequest(BaseModel):
    origin: str = "PVG"
    destination: str = "DTW"
    depart_date: str                    # YYYY-MM-DD
    passengers: int = 1


class ScoreRequest(BaseModel):
    flights: list[FlightOption]
