"""test_api.py — FastAPI 路由集成测试（使用 TestClient，不依赖真实网络）"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DEPART = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ── /search ───────────────────────────────────────────────────────────────────

class TestSearchEndpoint:
    def test_basic_demo_search(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 5,
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5
        # 按 rank 升序
        ranks = [d["rank"] for d in data]
        assert ranks == sorted(ranks)

    def test_scores_in_range(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 20,
        })
        assert r.status_code == 200
        for item in r.json():
            assert 0 <= item["score"] <= 100

    def test_buy_or_wait_valid_values(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo",
        })
        assert r.status_code == 200
        for item in r.json():
            assert item["buy_or_wait"] in ("BUY", "WAIT", "SKIP")

    def test_response_contains_breakdown(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 1,
        })
        assert r.status_code == 200
        bd = r.json()[0]["breakdown"]
        for key in ("price_score", "duration_score", "stops_score", "transfer_risk_score", "time_comfort_score"):
            assert key in bd
            assert 0 <= bd[key] <= 100

    def test_invalid_date_format(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": "not-a-date", "provider": "demo",
        })
        assert r.status_code == 422

    def test_bad_weight_sum(self) -> None:
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo",
            "w_price": 0.9, "w_duration": 0.9,
            "w_stops": 0.0, "w_transfer_risk": 0.0, "w_time_comfort": 0.0,
        })
        assert r.status_code == 422

    def test_custom_weights_change_ranking(self) -> None:
        """全权重给价格时，最低价航班应排第一"""
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 20,
            "w_price": 1.0, "w_duration": 0.0,
            "w_stops": 0.0, "w_transfer_risk": 0.0, "w_time_comfort": 0.0,
        })
        assert r.status_code == 200
        data = r.json()
        prices = [d["flight"]["price_usd"] for d in data]
        assert prices[0] == min(prices)

    def test_top_n_exceeds_available_returns_all(self) -> None:
        """top_n 大于实际航班数时，返回全部（不超过 demo 的 20 条）"""
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 100,  # API 上限
        })
        assert r.status_code == 200
        assert len(r.json()) <= 20  # demo 只有 20 条

    def test_top_n_over_limit_rejected(self) -> None:
        """top_n > 100 应被 API 拒绝"""
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW",
            "depart_date": DEPART, "provider": "demo", "top_n": 9999,
        })
        assert r.status_code == 422

    def test_default_date_auto_filled(self) -> None:
        """不传 depart_date 时自动补今天+30天，不应报错"""
        r = client.get("/search", params={
            "origin": "PVG", "destination": "DTW", "provider": "demo",
        })
        assert r.status_code == 200

    def test_airport_code_case_insensitive(self) -> None:
        r = client.get("/search", params={
            "origin": "pvg", "destination": "dtw",
            "depart_date": DEPART, "provider": "demo", "top_n": 3,
        })
        assert r.status_code == 200


# ── /score ────────────────────────────────────────────────────────────────────

def _demo_flights_payload(n: int = 5) -> dict:
    raw_path = Path(__file__).parent.parent / "data" / "raw" / "demo_flights.json"
    flights = json.loads(raw_path.read_text())[:n]
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
