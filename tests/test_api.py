"""test_api.py — FastAPI 路由集成测试（mock fetch_flights，不依赖真实网络）"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import FlightOption

client = TestClient(app)

DEPART = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

_RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "demo_flights.json"


def _load_demo_flights(n: int = 20) -> list[FlightOption]:
    data = json.loads(_RAW_PATH.read_text())[:n]
    return [FlightOption.model_validate(d) for d in data]


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ── /search ───────────────────────────────────────────────────────────────────

MOCK_TARGET = "app.api.routes_search.fetch_flights"


class TestSearchEndpoint:
    def test_basic_search(self) -> None:
        with patch(MOCK_TARGET, return_value=_load_demo_flights(20)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW",
                "depart_date": DEPART, "top_n": 5,
            })
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5
        ranks = [d["rank"] for d in data]
        assert ranks == sorted(ranks)

    def test_scores_in_range(self) -> None:
        with patch(MOCK_TARGET, return_value=_load_demo_flights(20)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW",
                "depart_date": DEPART, "top_n": 20,
            })
        assert r.status_code == 200
        for item in r.json():
            assert 0 <= item["score"] <= 100

    def test_buy_or_wait_valid_values(self) -> None:
        with patch(MOCK_TARGET, return_value=_load_demo_flights(20)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW", "depart_date": DEPART,
            })
        assert r.status_code == 200
        for item in r.json():
            assert item["buy_or_wait"] in ("BUY", "WAIT", "SKIP")

    def test_response_contains_breakdown(self) -> None:
        with patch(MOCK_TARGET, return_value=_load_demo_flights(5)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW",
                "depart_date": DEPART, "top_n": 1,
            })
        assert r.status_code == 200
        bd = r.json()[0]["breakdown"]
        for key in ("price_score", "duration_score", "stops_score",
                    "transfer_risk_score", "time_comfort_score"):
            assert key in bd
            assert 0 <= bd[key] <= 100

    def test_invalid_date_format(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW", "depart_date": "not-a-date",
        })
        assert r.status_code == 422

    def test_bad_weight_sum(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW", "depart_date": DEPART,
            "w_price": 0.9, "w_duration": 0.9,
            "w_stops": 0.0, "w_transfer_risk": 0.0, "w_time_comfort": 0.0,
        })
        assert r.status_code == 422

    def test_custom_weights_change_ranking(self) -> None:
        """全权重给价格时，最低价航班应排第一"""
        with patch(MOCK_TARGET, return_value=_load_demo_flights(20)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW",
                "depart_date": DEPART, "top_n": 20,
                "w_price": 1.0, "w_duration": 0.0,
                "w_stops": 0.0, "w_transfer_risk": 0.0, "w_time_comfort": 0.0,
            })
        assert r.status_code == 200
        data = r.json()
        prices = [d["flight"]["price_usd"] for d in data]
        assert prices[0] == min(prices)

    def test_top_n_exceeds_available_returns_all(self) -> None:
        """top_n 大于实际航班数时，返回全部可用"""
        with patch(MOCK_TARGET, return_value=_load_demo_flights(20)):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW",
                "depart_date": DEPART, "top_n": 100,
            })
        assert r.status_code == 200
        assert len(r.json()) <= 20

    def test_top_n_over_limit_rejected(self) -> None:
        """top_n > 100 应被 API 拒绝"""
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "top_n": 9999,
        })
        assert r.status_code == 422

    def test_default_date_auto_filled(self) -> None:
        """不传 depart_date 时自动补今天+30天，不应报错"""
        with patch(MOCK_TARGET, return_value=_load_demo_flights(5)):
            r = client.get("/search", params={"origin": "PVG", "destination": "DTW"})
        assert r.status_code == 200

    def test_airport_code_case_insensitive(self) -> None:
        with patch(MOCK_TARGET, return_value=_load_demo_flights(5)):
            r = client.get("/search", params={
                "origin": "pvg", "destination": "dtw",
                "depart_date": DEPART, "top_n": 3,
            })
        assert r.status_code == 200

    def test_fetch_error_returns_503(self) -> None:
        """当 fetch_flights 抛出 RuntimeError 时，API 应返回 503"""
        with patch(MOCK_TARGET, side_effect=RuntimeError("Google Flights timeout")):
            r = client.get("/search", params={
                "origin": "PVG", "destination": "DTW", "depart_date": DEPART,
            })
        assert r.status_code == 503


# ── /score ────────────────────────────────────────────────────────────────────

def _demo_flights_payload(n: int = 5) -> dict:
    flights = json.loads(_RAW_PATH.read_text())[:n]
    return {"flights": flights}


class TestScoreEndpoint:
    def test_basic_scoring(self) -> None:
        r = client.post("/score", json=_demo_flights_payload(5))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5
        ranks = [d["rank"] for d in data]
        assert ranks == sorted(ranks)

    def test_empty_flights_returns_422(self) -> None:
        r = client.post("/score", json={"flights": []})
        assert r.status_code == 422

    def test_single_flight(self) -> None:
        r = client.post("/score", json=_demo_flights_payload(1), params={"top_n": 1})
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_top_n_limits_results(self) -> None:
        r = client.post("/score", json=_demo_flights_payload(10), params={"top_n": 3})
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_scores_descending(self) -> None:
        r = client.post("/score", json=_demo_flights_payload(10))
        assert r.status_code == 200
        scores = [d["score"] for d in r.json()]
        assert scores == sorted(scores, reverse=True)

    def test_recommend_reason_non_empty(self) -> None:
        r = client.post("/score", json=_demo_flights_payload(3))
        assert r.status_code == 200
        for item in r.json():
            assert len(item["recommend_reason"]) > 0

    def test_bad_weight_sum_422(self) -> None:
        r = client.post(
            "/score",
            json=_demo_flights_payload(3),
            params={"w_price": 0.5, "w_duration": 0.5,
                    "w_stops": 0.5, "w_transfer_risk": 0.0, "w_time_comfort": 0.0},
        )
        assert r.status_code == 422


# ── /history ──────────────────────────────────────────────────────────────────

class TestHistoryEndpoint:
    def test_sessions_returns_list(self) -> None:
        r = client.get("/history/sessions", params={"origin": "PVG", "destination": "DTW"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sessions_limit_param(self) -> None:
        r = client.get("/history/sessions", params={
            "origin": "PVG", "destination": "DTW", "limit": 5,
        })
        assert r.status_code == 200
        assert len(r.json()) <= 5

    def test_session_flights_404_like_on_missing(self) -> None:
        """不存在的 session_id 应返回空列表而非 500"""
        r = client.get("/history/sessions/999999")
        assert r.status_code == 200
        assert r.json() == []

    def test_price_trend_returns_list(self) -> None:
        r = client.get("/history/price-trend", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "top_n": 5,
        })
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_price_trend_auto_date(self) -> None:
        """不传 depart_date 时应自动补默认值，不应报错"""
        r = client.get("/history/price-trend", params={"origin": "PVG", "destination": "DTW"})
        assert r.status_code == 200
