"""Transactional, run-versioned local store; published pointer prevents partial reads."""
import json
import sqlite3
from pathlib import Path

from maritime.models import stable_id, utcnow


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "maritime.db"
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL,
                    ended_at TEXT, report TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS products (
                    run_id TEXT NOT NULL, product TEXT NOT NULL, record_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(run_id, product, record_id));
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS products_lookup ON products(product, run_id);
            """)

    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def metadata(self, key, default=None):
        with self.connect() as con:
            row = con.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_metadata(self, key, value):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value)))

    def write(self, run_id, product, records):
        with self.connect() as con:
            con.execute("DELETE FROM products WHERE run_id=? AND product=?", (run_id, product))
            con.executemany("INSERT INTO products VALUES (?,?,?,?)", [
                (run_id, product, stable_id(i, record), json.dumps(record, default=str, allow_nan=False))
                for i, record in enumerate(records)
            ])

    def read(self, product, run_id=None):
        run_id = run_id or self.metadata("published_run")
        with self.connect() as con:
            rows = con.execute("SELECT payload FROM products WHERE run_id=? AND product=? ORDER BY rowid", (run_id, product)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def run(self, report):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)", (
                report["run_id"], report["status"], report["start_time"], report.get("end_time"), json.dumps(report, default=str)))

    def audit(self, kind, payload):
        at = utcnow()
        audit_id = stable_id(at, kind, payload)
        with self.connect() as con:
            con.execute("INSERT INTO audit VALUES (?,?,?,?)", (audit_id, at, kind, json.dumps(payload)))
        return audit_id

    def audits(self, kind):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT payload FROM audit WHERE kind=? ORDER BY created_at", (kind,))]

    def latest_report(self):
        with self.connect() as con:
            row = con.execute("SELECT report FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None
