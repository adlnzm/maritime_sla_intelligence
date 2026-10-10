"""Transactional, run-versioned local store; published pointer prevents partial reads."""

import json
import sqlite3
from pathlib import Path

from maritime.models import json_default, stable_id, utcnow


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
                CREATE TABLE IF NOT EXISTS releases (run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit_chain (sequence INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT UNIQUE, previous_hash TEXT, digest TEXT);
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS chain_no_update BEFORE UPDATE ON audit_chain BEGIN SELECT RAISE(ABORT,'audit chain is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS chain_no_delete BEFORE DELETE ON audit_chain BEGIN SELECT RAISE(ABORT,'audit chain is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS release_no_update BEFORE UPDATE ON releases BEGIN SELECT RAISE(ABORT,'release is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS release_no_delete BEFORE DELETE ON releases BEGIN SELECT RAISE(ABORT,'release is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS released_product_no_delete BEFORE DELETE ON products WHEN EXISTS(SELECT 1 FROM releases WHERE run_id=OLD.run_id) BEGIN SELECT RAISE(ABORT,'approved product is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS released_product_no_update BEFORE UPDATE ON products WHEN EXISTS(SELECT 1 FROM releases WHERE run_id=OLD.run_id) BEGIN SELECT RAISE(ABORT,'approved product is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS released_product_no_insert BEFORE INSERT ON products WHEN EXISTS(SELECT 1 FROM releases WHERE run_id=NEW.run_id) BEGIN SELECT RAISE(ABORT,'approved product is immutable'); END;
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
        if key == "published_run":
            raise ValueError("Publication requires an approved release manifest")
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value)))

    def write(self, run_id, product, records):
        with self.connect() as con:
            con.execute("DELETE FROM products WHERE run_id=? AND product=?", (run_id, product))
            con.executemany(
                "INSERT INTO products VALUES (?,?,?,?)",
                [
                    (
                        run_id,
                        product,
                        stable_id(i, record),
                        json.dumps(record, default=json_default, allow_nan=False),
                    )
                    for i, record in enumerate(records)
                ],
            )

    def read(self, product, run_id=None):
        run_id = run_id or self.metadata("published_run")
        with self.connect() as con:
            rows = con.execute(
                "SELECT payload FROM products WHERE run_id=? AND product=? ORDER BY rowid",
                (run_id, product),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def run(self, report):
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                (
                    report["run_id"],
                    report["status"],
                    report["start_time"],
                    report.get("end_time"),
                    json.dumps(report, default=json_default, allow_nan=False),
                ),
            )

    def audit(self, kind, payload):
        from maritime.governance import fingerprint

        at = utcnow()
        audit_id = stable_id(at, kind, payload)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute(
                "SELECT digest FROM audit_chain ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = previous[0] if previous else "GENESIS"
            con.execute(
                "INSERT INTO audit VALUES (?,?,?,?)", (audit_id, at, kind, json.dumps(payload))
            )
            con.execute(
                "INSERT INTO audit_chain(audit_id,previous_hash,digest) VALUES (?,?,?)",
                (audit_id, previous, fingerprint([previous, audit_id, at, kind, payload])),
            )
        return audit_id

    def verify_audit(self):
        from maritime.governance import fingerprint

        with self.connect() as con:
            rows = con.execute(
                "SELECT a.*, c.previous_hash, c.digest FROM audit_chain c JOIN audit a ON a.id=c.audit_id ORDER BY c.sequence"
            ).fetchall()
            unchained = con.execute(
                "SELECT COUNT(*) FROM audit WHERE id NOT IN (SELECT audit_id FROM audit_chain)"
            ).fetchone()[0]
        previous = "GENESIS"
        for row in rows:
            if (
                row["previous_hash"] != previous
                or fingerprint(
                    [
                        previous,
                        row["id"],
                        row["created_at"],
                        row["kind"],
                        json.loads(row["payload"]),
                    ]
                )
                != row["digest"]
            ):
                raise ValueError("Audit chain verification failed")
            previous = row["digest"]
        return {
            "verified_records": len(rows),
            "legacy_unchained_records": unchained,
            "status": "PASS" if not unchained else "BLOCKED",
        }

    def release(self, run_id=None):
        run_id = run_id or self.metadata("published_run")
        with self.connect() as con:
            row = con.execute("SELECT manifest FROM releases WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def publish(self, report, manifest):
        from maritime.governance import verify_manifest

        if report["status"] != "SUCCESS" or report["governance"]["stages"]["publication"][
            "status"
        ] not in {"PASS", "PASS_WITH_WARNINGS"}:
            raise ValueError("Publication gate not approved")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            products = {
                n: [
                    json.loads(r[0])
                    for r in con.execute(
                        "SELECT payload FROM products WHERE run_id=? AND product=? ORDER BY rowid",
                        (report["run_id"], n),
                    )
                ]
                for n in manifest["datasets"]
            }
            verify_manifest(products, manifest)
            con.execute(
                "INSERT INTO releases VALUES (?,?)", (report["run_id"], json.dumps(manifest))
            )
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?,?)",
                ("published_run", json.dumps(report["run_id"])),
            )
            con.execute(
                "UPDATE runs SET status=?,ended_at=?,report=? WHERE run_id=?",
                (
                    "SUCCESS",
                    report.get("end_time"),
                    json.dumps(report, default=json_default),
                    report["run_id"],
                ),
            )

    def read_approved(self, product, run_id=None):
        from maritime.governance import contract, fingerprint

        manifest = self.release(run_id)
        if not manifest or manifest["status"] not in contract()["allowed_release_states"]:
            raise ValueError("No approved release for requested run")
        rows = self.read(product, manifest["run_id"])
        expected = manifest["datasets"].get(product)
        if not expected or len(rows) != expected["rows"] or fingerprint(rows) != expected["sha256"]:
            raise ValueError("Serving release integrity failure")
        return rows

    def audits(self, kind):
        with self.connect() as con:
            return [
                json.loads(r[0])
                for r in con.execute(
                    "SELECT payload FROM audit WHERE kind=? ORDER BY created_at", (kind,)
                )
            ]

    def latest_report(self):
        with self.connect() as con:
            row = con.execute("SELECT report FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def published_report(self):
        with self.connect() as con:
            row = con.execute(
                "SELECT report FROM runs WHERE run_id=?", (self.metadata("published_run"),)
            ).fetchone()
        return json.loads(row[0]) if row else None
