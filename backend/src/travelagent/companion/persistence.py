"""SQLite persistence layer for the ambient monitoring loop.

Stores trip state, polling snapshots, committee runs, and action logs.
Uses aiosqlite for async compat with the monitoring loop.
Falls back to synchronous sqlite3 if aiosqlite is unavailable.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_DB = Path(__file__).parent / "companion.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trip (
    trip_id        TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    flight_number  TEXT NOT NULL,
    meeting_event_id TEXT,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    status         TEXT NOT NULL DEFAULT 'active',
    deadline       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state_snapshot (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id        TEXT NOT NULL REFERENCES trip(trip_id),
    polled_at      TEXT NOT NULL,
    flight_status  TEXT,
    delay_minutes  INTEGER,
    delay_trend    TEXT,
    weather_condition TEXT,
    weather_trend  TEXT,
    traffic_level  TEXT,
    drive_time_min INTEGER,
    raw_payload    TEXT
);

CREATE TABLE IF NOT EXISTS committee_run (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id        TEXT NOT NULL REFERENCES trip(trip_id),
    snapshot_id    INTEGER REFERENCES state_snapshot(snapshot_id),
    time_signal    TEXT NOT NULL,
    time_p         REAL,
    risk_signal    TEXT NOT NULL,
    risk_multiplier REAL,
    risk_factors   TEXT,
    impact_signal  TEXT NOT NULL,
    impact_weight  REAL,
    decision       TEXT NOT NULL,
    rationale      TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    action_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER REFERENCES committee_run(run_id),
    action_type    TEXT NOT NULL,
    payload        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshot_trip ON state_snapshot(trip_id, polled_at);
CREATE INDEX IF NOT EXISTS idx_run_trip ON committee_run(trip_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trip_status ON trip(status);
"""


class DB:
    """Synchronous SQLite wrapper for trip persistence."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    # ── Trip ──────────────────────────────────────────

    def create_trip(self, trip_id: str, user_id: str, flight_number: str,
                    deadline: datetime, meeting_event_id: str = "") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO trip (trip_id, user_id, flight_number, meeting_event_id, "
            "started_at, status, deadline) VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (trip_id, user_id, flight_number, meeting_event_id, now,
             deadline.isoformat()),
        )
        self.conn.commit()
        return {"trip_id": trip_id, "status": "active"}

    def end_trip(self, trip_id: str, status: str = "completed"):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE trip SET status=?, ended_at=? WHERE trip_id=?",
            (status, now, trip_id),
        )
        self.conn.commit()

    def get_trip(self, trip_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM trip WHERE trip_id=?", (trip_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_active_trips(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trip WHERE status='active'"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Snapshot ──────────────────────────────────────

    def save_snapshot(self, trip_id: str, polled_at: datetime,
                      flight_status: str, delay_minutes: int,
                      delay_trend: str, weather_condition: str,
                      weather_trend: str, traffic_level: str,
                      drive_time_min: int, raw_payload: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO state_snapshot "
            "(trip_id, polled_at, flight_status, delay_minutes, delay_trend, "
            "weather_condition, weather_trend, traffic_level, drive_time_min, raw_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trip_id, polled_at.isoformat(), flight_status, delay_minutes,
             delay_trend, weather_condition, weather_trend, traffic_level,
             drive_time_min, json.dumps(raw_payload)),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_latest_snapshot(self, trip_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM state_snapshot WHERE trip_id=? ORDER BY polled_at DESC LIMIT 1",
            (trip_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_snapshots(self, trip_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM state_snapshot WHERE trip_id=? ORDER BY polled_at",
            (trip_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Committee Run ─────────────────────────────────

    def save_committee_run(self, trip_id: str, snapshot_id: int,
                           time_signal: str, time_p: float,
                           risk_signal: str, risk_multiplier: float,
                           risk_factors: list, impact_signal: str,
                           impact_weight: float, decision: str,
                           rationale: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO committee_run "
            "(trip_id, snapshot_id, time_signal, time_p, risk_signal, "
            "risk_multiplier, risk_factors, impact_signal, impact_weight, "
            "decision, rationale, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trip_id, snapshot_id, time_signal, time_p, risk_signal,
             risk_multiplier, json.dumps(risk_factors), impact_signal,
             impact_weight, decision, rationale, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_latest_decision(self, trip_id: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT decision FROM committee_run WHERE trip_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (trip_id,),
        ).fetchone()
        return row["decision"] if row else None

    def get_committee_runs(self, trip_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM committee_run WHERE trip_id=? ORDER BY created_at",
            (trip_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Action Log ────────────────────────────────────

    def save_action(self, run_id: int, action_type: str,
                    payload: dict, status: str = "pending") -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO action_log (run_id, action_type, payload, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, action_type, json.dumps(payload), status, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_actions(self, trip_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT a.* FROM action_log a "
            "JOIN committee_run c ON a.run_id = c.run_id "
            "WHERE c.trip_id=? ORDER BY a.created_at",
            (trip_id,),
        ).fetchall()
        return [dict(r) for r in rows]
