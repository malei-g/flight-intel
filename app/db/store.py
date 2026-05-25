"""
SQLite 持久层
表结构:
  fetch_sessions  — 每次抓取任务的元数据
  flight_snapshots — 每条航班的打分快照（关联 session）
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from app.schemas import ScoredFlight, SearchConfig

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "flights.db"


def get_db_path() -> Path:
    return _DB_PATH


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS fetch_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            origin      TEXT    NOT NULL,
            destination TEXT    NOT NULL,
            depart_date TEXT    NOT NULL,
            fetched_at  TEXT    NOT NULL,
            flight_count INTEGER NOT NULL,
            price_level TEXT
        );

        CREATE TABLE IF NOT EXISTS flight_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES fetch_sessions(id),
            flight_id       TEXT    NOT NULL,
            airline         TEXT,
            price_usd       REAL    NOT NULL,
            duration_min    INTEGER NOT NULL,
            stops           INTEGER NOT NULL,
            is_red_eye      INTEGER NOT NULL,
            score           REAL    NOT NULL,
            rank            INTEGER NOT NULL,
            buy_or_wait     TEXT    NOT NULL,
            recommend_reason TEXT,
            score_breakdown TEXT,
            raw_flight      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_session
            ON flight_snapshots(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_route
            ON fetch_sessions(origin, destination, depart_date);
        """)


def save_session(
    config: SearchConfig,
    scored: list[ScoredFlight],
    price_level: str = "",
) -> int:
    """保存一次抓取会话及所有打分快照，返回 session_id。"""
    init_db()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO fetch_sessions
               (origin, destination, depart_date, fetched_at, flight_count, price_level)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (config.origin, config.destination, config.depart_date,
             fetched_at, len(scored), price_level),
        )
        session_id = cur.lastrowid

        rows = []
        for sf in scored:
            f = sf.flight
            airline = f.segments[0].airline if f.segments else ""
            rows.append((
                session_id,
                f.id,
                airline,
                f.price_usd,
                f.total_duration_min,
                f.stops,
                int(f.is_red_eye),
                sf.score,
                sf.rank,
                sf.buy_or_wait,
                sf.recommend_reason,
                json.dumps(sf.breakdown.model_dump(), ensure_ascii=False),
                f.model_dump_json(),
            ))
        con.executemany(
            """INSERT INTO flight_snapshots
               (session_id, flight_id, airline, price_usd, duration_min,
                stops, is_red_eye, score, rank, buy_or_wait,
                recommend_reason, score_breakdown, raw_flight)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    return session_id  # type: ignore[return-value]


def list_sessions(
    origin: str = "PVG",
    destination: str = "DTW",
    limit: int = 30,
) -> list[dict]:
    """返回历史抓取会话列表（最新在前）。"""
    init_db()
    with _conn() as con:
        rows = con.execute(
            """SELECT id, origin, destination, depart_date,
                      fetched_at, flight_count, price_level
               FROM fetch_sessions
               WHERE origin = ? AND destination = ?
               ORDER BY fetched_at DESC
               LIMIT ?""",
            (origin, destination, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def load_session_flights(session_id: int) -> list[dict]:
    """加载某次会话的所有航班快照（按 rank 升序）。"""
    init_db()
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM flight_snapshots
               WHERE session_id = ?
               ORDER BY rank ASC""",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def price_history(
    origin: str,
    destination: str,
    depart_date: str,
    top_n: int = 5,
) -> list[dict]:
    """
    返回历次抓取中 Top-N 航班的最低价、均价，用于趋势图。
    每条记录: {fetched_at, min_price, avg_price, flight_count}
    """
    init_db()
    with _conn() as con:
        rows = con.execute(
            """SELECT s.fetched_at,
                      MIN(f.price_usd)  AS min_price,
                      AVG(f.price_usd)  AS avg_price,
                      COUNT(*)          AS flight_count
               FROM fetch_sessions s
               JOIN flight_snapshots f ON f.session_id = s.id
               WHERE s.origin = ? AND s.destination = ? AND s.depart_date = ?
                 AND f.rank <= ?
               GROUP BY s.id
               ORDER BY s.fetched_at ASC""",
            (origin, destination, depart_date, top_n),
        ).fetchall()
    return [dict(r) for r in rows]
