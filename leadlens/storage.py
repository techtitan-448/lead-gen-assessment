"""SQLite-backed cache for enrichment + MX lookups.

Local dev uses a single file (data/leadlens.db). The same interface maps
cleanly onto Postgres/Redis in production — see README "Architecture".
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Optional

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "leadlens.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS enrichment_cache (
    domain      TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mx_cache (
    domain      TEXT PRIMARY KEY,
    has_mx      INTEGER NOT NULL,
    checked_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL NOT NULL,
    source      TEXT,
    rows_in     INTEGER,
    rows_out    INTEGER,
    hot         INTEGER,
    warm        INTEGER,
    cold        INTEGER
);
"""


class Cache:
    def __init__(self, path: str = DEFAULT_DB, ttl_seconds: int = 7 * 24 * 3600):
        self.path = path
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    # -- enrichment -----------------------------------------------------
    def get_enrichment(self, domain: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, fetched_at FROM enrichment_cache WHERE domain=?", (domain,)
            ).fetchone()
        if not row:
            return None
        payload, fetched_at = row
        if time.time() - fetched_at > self.ttl:
            return None
        return json.loads(payload)

    def put_enrichment(self, domain: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO enrichment_cache(domain, payload, fetched_at) VALUES (?,?,?)",
                (domain, json.dumps(payload), time.time()),
            )
            self._conn.commit()

    # -- MX -------------------------------------------------------------
    def get_mx(self, domain: str) -> Optional[bool]:
        with self._lock:
            row = self._conn.execute(
                "SELECT has_mx, checked_at FROM mx_cache WHERE domain=?", (domain,)
            ).fetchone()
        if not row or time.time() - row[1] > self.ttl:
            return None
        return bool(row[0])

    def put_mx(self, domain: str, has_mx: bool) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO mx_cache(domain, has_mx, checked_at) VALUES (?,?,?)",
                (domain, int(has_mx), time.time()),
            )
            self._conn.commit()

    # -- runs -----------------------------------------------------------
    def record_run(self, source: str, rows_in: int, rows_out: int, hot: int, warm: int, cold: int) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO runs(created_at, source, rows_in, rows_out, hot, warm, cold) VALUES (?,?,?,?,?,?,?)",
                (time.time(), source, rows_in, rows_out, hot, warm, cold),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def recent_runs(self, limit: int = 10) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, created_at, source, rows_in, rows_out, hot, warm, cold FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        keys = ["id", "created_at", "source", "rows_in", "rows_out", "hot", "warm", "cold"]
        return [dict(zip(keys, r)) for r in rows]

    def stats(self) -> dict:
        with self._lock:
            e = self._conn.execute("SELECT COUNT(*) FROM enrichment_cache").fetchone()[0]
            m = self._conn.execute("SELECT COUNT(*) FROM mx_cache").fetchone()[0]
        return {"enrichment_cached": e, "mx_cached": m}

    def close(self) -> None:
        self._conn.close()
