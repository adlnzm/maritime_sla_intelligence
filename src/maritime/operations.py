"""Gold-consuming operational store. Reviews never update analytical or source tables."""

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from maritime.medallion import FRESHNESS_DAYS, GoldWeek
from maritime.models import stable_id


class Conflict(ValueError):
    pass


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,100}$")
    action: Literal["IGNORE", "MONITOR", "ESCALATE"]
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=0)
    risk_revision: str

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if len(value) < 10:
            raise ValueError("A meaningful reason of at least ten characters is required")
        return value


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_token: str
    outcome: Literal["SENT", "FAILED", "EXCEPTION"]
    failure_reason: str | None = Field(default=None, max_length=500)


def configuration(path="configs/workflow.json"):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version") != "1.0":
        raise ValueError("Unsupported workflow configuration")
    if not isinstance(config.get("recipients"), list) or any(
        not isinstance(r, str) or "@" not in r or any(c in r for c in "\r\n;,")
        for r in config["recipients"]
    ):
        raise ValueError("Workflow recipients must be an explicit list of addresses")
    for name, lower, upper in (
        ("max_attempts", 1, 10),
        ("retry_seconds", 1, 86400),
        ("lease_seconds", 30, 3600),
    ):
        if type(config.get(name)) is not int or not lower <= config[name] <= upper:
            raise ValueError(f"Invalid workflow configuration: {name}")
    return config


class Operations:
    def __init__(self, analytical_store, root, config=None, clock=None):
        self.source = analytical_store
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "workflow.db"
        self.config = config or configuration()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY, gold_json TEXT NOT NULL, version INTEGER NOT NULL,
                    action TEXT, owner TEXT, approved_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions (
                    request_id TEXT PRIMARY KEY, review_id TEXT NOT NULL,
                    request_json TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, attempts INTEGER NOT NULL, next_attempt TEXT NOT NULL,
                    lease_until TEXT, lease_token TEXT);
                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    lease_token TEXT PRIMARY KEY, event_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS actions_immutable_update BEFORE UPDATE ON actions
                    BEGIN SELECT RAISE(ABORT,'action history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS actions_immutable_delete BEFORE DELETE ON actions
                    BEGIN SELECT RAISE(ABORT,'action history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS attempts_immutable_update BEFORE UPDATE ON delivery_attempts
                    BEGIN SELECT RAISE(ABORT,'delivery history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS attempts_immutable_delete BEFORE DELETE ON delivery_attempts
                    BEGIN SELECT RAISE(ABORT,'delivery history is immutable'); END;
            """)

    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def availability(self, row):
        latest = row["source_latest_observation"]
        age = (self.clock().date() - date.fromisoformat(latest)).days if latest else None
        status = (
            "UNAVAILABLE" if age is None else "FRESH" if 0 <= age <= FRESHNESS_DAYS else "STALE"
        )
        return {
            **row,
            "freshness_status": status,
            "freshness_age_days": age,
            "review_eligible": status == "FRESH"
            and row["quality_status"] == "PASS"
            and row["risk_level"] in {"HIGH", "CRITICAL"},
        }

    def sync(self):
        """Reconcile a pinned approved Gold snapshot; retries create no duplicate transitions."""
        manifest = self.source.release()
        if not manifest:
            raise ValueError("No approved analytical publication")
        rows = self.source.read_layer("gold", "port_weeks", manifest["run_id"])
        for row in rows:
            GoldWeek.model_validate(row)
        now = self.clock().isoformat()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for source_row in rows:
                row = self.availability(source_row)
                prior = con.execute(
                    "SELECT * FROM reviews WHERE review_id=?", (row["review_id"],)
                ).fetchone()
                if prior and prior["approved_at"] > manifest["approved_at"]:
                    continue
                old = json.loads(prior["gold_json"]) if prior else None
                version = prior["version"] if prior else 0
                changed = old is not None and old["risk_revision"] != row["risk_revision"]
                action = prior["action"] if prior and not changed else None
                owner = prior["owner"] if prior and not changed else None
                con.execute(
                    "INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?)",
                    (
                        row["review_id"],
                        json.dumps(row),
                        version,
                        action,
                        owner,
                        manifest["approved_at"],
                    ),
                )
                if row["review_eligible"] and (
                    old is None or old["risk_level"] != row["risk_level"]
                ):
                    event_id = stable_id(
                        row["review_id"],
                        old["risk_revision"] if old else "INITIAL",
                        row["risk_revision"],
                        row["risk_level"],
                    )
                    event = {
                        "event_id": event_id,
                        "review_id": row["review_id"],
                        "port_id": row["port_id"],
                        "port_name": row["port_name"],
                        "week_start": row["week_start"],
                        "risk_level": row["risk_level"],
                        "previous_risk": old["risk_level"] if old else None,
                        "risk_revision": row["risk_revision"],
                        "risk_drivers": row["risk_drivers"],
                        "source_latest_observation": row["source_latest_observation"],
                        "freshness_status": row["freshness_status"],
                        "created_at": now,
                        "review_reference": "/operations/queue?review_id=" + row["review_id"],
                        "run_id": row["run_id"],
                        "classification": row["classification"],
                        "lineage_id": row["lineage_id"],
                        "simulated": row["simulated"],
                    }
                    con.execute(
                        "INSERT OR IGNORE INTO events VALUES (?,?,?,'PENDING',0,?,NULL,NULL)",
                        (event_id, row["review_id"], json.dumps(event), now),
                    )
        return rows

    def queue(self, **filters):
        active_ids = {row["review_id"] for row in self.sync()}
        with self.connect() as con:
            rows = con.execute("SELECT * FROM reviews ORDER BY review_id").fetchall()
        output = []
        for stored in rows:
            if stored["review_id"] not in active_ids:
                continue
            row = self.availability(json.loads(stored["gold_json"]))
            row.update(
                review_status=stored["action"] or "UNREVIEWED",
                review_version=stored["version"],
                owner=stored["owner"],
                risk_drivers_text=", ".join(row["risk_drivers"]),
            )
            if all(value is None or row.get(key) == value for key, value in filters.items()):
                output.append(row)
        return output

    def review(self, review_id, request, actor):
        if not actor:
            raise ValueError("Authenticated user identity required")
        self.sync()
        body = request.model_dump()
        request_json = json.dumps({"review_id": review_id, "actor": actor, **body}, sort_keys=True)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            replay = con.execute(
                "SELECT * FROM actions WHERE request_id=?", (request.request_id,)
            ).fetchone()
            if replay:
                if replay["request_json"] != request_json:
                    raise Conflict("Idempotency key already used for another decision")
                return json.loads(replay["payload"])
            saved = con.execute("SELECT * FROM reviews WHERE review_id=?", (review_id,)).fetchone()
            if not saved:
                raise ValueError("Unknown review")
            row = self.availability(json.loads(saved["gold_json"]))
            if not row["review_eligible"] or row["run_id"] != self.source.metadata("published_run"):
                raise Conflict("Review unavailable: stale, incomplete or unflagged Gold data")
            if (
                saved["version"] != request.expected_version
                or row["risk_revision"] != request.risk_revision
            ):
                raise Conflict("Gold risk or review changed; refresh before deciding")
            if request.action == "IGNORE" and len(request.reason) < 40:
                raise ValueError("Ignoring HIGH/CRITICAL risk requires at least forty characters")
            payload = {
                **body,
                "review_id": review_id,
                "previous_action": saved["action"],
                "version": saved["version"] + 1,
                "actor": actor,
                "owner": actor,
                "created_at": self.clock().isoformat(),
                **{
                    k: row[k]
                    for k in (
                        "port_id",
                        "week_start",
                        "risk_level",
                        "run_id",
                        "classification",
                        "lineage_id",
                    )
                },
            }
            con.execute(
                "INSERT INTO actions VALUES (?,?,?,?)",
                (request.request_id, review_id, request_json, json.dumps(payload)),
            )
            con.execute(
                "UPDATE reviews SET version=?,action=?,owner=? WHERE review_id=?",
                (payload["version"], request.action, actor, review_id),
            )
        return payload

    def history(self, review_id=None):
        with self.connect() as con:
            rows = con.execute(
                "SELECT payload FROM actions WHERE (? IS NULL OR review_id=?) ORDER BY rowid",
                (review_id, review_id),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def events(self):
        self.sync()
        with self.connect() as con:
            rows = con.execute("SELECT * FROM events ORDER BY rowid").fetchall()
            attempts = {
                r["event_id"]: json.loads(r["payload"])
                for r in con.execute("SELECT * FROM delivery_attempts ORDER BY rowid")
            }
        return [
            {
                **json.loads(r["payload"]),
                "delivery_status": r["state"],
                "attempts": r["attempts"],
                "last_attempt_at": attempts.get(r["event_id"], {}).get("created_at"),
                "last_failure_reason": attempts.get(r["event_id"], {}).get("failure_reason"),
                "unresolved_exception": r["state"] == "EXCEPTION",
            }
            for r in rows
        ]

    def claim(self):
        self.sync()
        now = self.clock()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Crashed workers leave an auditable attempt and a retryable durable event.
            for expired in con.execute(
                "SELECT * FROM events WHERE state='IN_FLIGHT' AND lease_until<=?",
                (now.isoformat(),),
            ).fetchall():
                con.execute(
                    "INSERT OR IGNORE INTO delivery_attempts VALUES (?,?,?)",
                    (
                        expired["lease_token"],
                        expired["event_id"],
                        json.dumps(
                            {
                                "event_id": expired["event_id"],
                                "outcome": "FAILED",
                                "failure_reason": "LEASE_EXPIRED",
                                "created_at": now.isoformat(),
                            }
                        ),
                    ),
                )
                state = (
                    "EXCEPTION" if expired["attempts"] >= self.config["max_attempts"] else "PENDING"
                )
                con.execute(
                    "UPDATE events SET state=?,lease_token=NULL,lease_until=NULL WHERE event_id=?",
                    (state, expired["event_id"]),
                )
            row = None
            for candidate in con.execute(
                "SELECT * FROM events WHERE state='PENDING' AND next_attempt<=? ORDER BY rowid",
                (now.isoformat(),),
            ).fetchall():
                saved = con.execute(
                    "SELECT gold_json FROM reviews WHERE review_id=?", (candidate["review_id"],)
                ).fetchone()
                gold = self.availability(json.loads(saved[0])) if saved else None
                event = json.loads(candidate["payload"])
                if (
                    gold
                    and gold["review_eligible"]
                    and gold["risk_revision"] == event["risk_revision"]
                    and gold["run_id"] == self.source.metadata("published_run")
                ):
                    row = candidate
                    break
                token = uuid.uuid4().hex
                con.execute(
                    "INSERT INTO delivery_attempts VALUES (?,?,?)",
                    (
                        token,
                        candidate["event_id"],
                        json.dumps(
                            {
                                "event_id": candidate["event_id"],
                                "outcome": "EXCEPTION",
                                "failure_reason": "SUPERSEDED_OR_STALE_GOLD",
                                "created_at": now.isoformat(),
                            }
                        ),
                    ),
                )
                con.execute(
                    "UPDATE events SET state='EXCEPTION' WHERE event_id=?", (candidate["event_id"],)
                )
            if not row:
                return None
            token = uuid.uuid4().hex
            con.execute(
                "UPDATE events SET state='IN_FLIGHT',attempts=attempts+1,lease_token=?,lease_until=? WHERE event_id=?",
                (
                    token,
                    (now + timedelta(seconds=self.config["lease_seconds"])).isoformat(),
                    row["event_id"],
                ),
            )
        return {
            **json.loads(row["payload"]),
            "lease_token": token,
            "recipients": self.config["recipients"],
            "attempt": row["attempts"] + 1,
        }

    def complete(self, event_id, result):
        now = self.clock()
        if result.outcome != "SENT" and not result.failure_reason:
            raise ValueError("Failure/exception reason required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute(
                "SELECT payload FROM delivery_attempts WHERE lease_token=?", (result.lease_token,)
            ).fetchone()
            if prior:
                old = json.loads(prior[0])
                if old.get("event_id") != event_id or any(
                    old.get(k) != v for k, v in result.model_dump().items()
                ):
                    raise Conflict("Conflicting delivery completion")
                return old
            event = con.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            if (
                not event
                or event["state"] != "IN_FLIGHT"
                or event["lease_token"] != result.lease_token
                or event["lease_until"] <= now.isoformat()
            ):
                raise Conflict("Delivery lease no longer owned")
            state = result.outcome
            if result.outcome == "FAILED":
                state = (
                    "EXCEPTION" if event["attempts"] >= self.config["max_attempts"] else "PENDING"
                )
            payload = {
                **result.model_dump(),
                "event_id": event_id,
                "created_at": now.isoformat(),
                "attempt": event["attempts"],
                "delivery_status": state,
            }
            con.execute(
                "INSERT INTO delivery_attempts VALUES (?,?,?)",
                (result.lease_token, event_id, json.dumps(payload)),
            )
            con.execute(
                "UPDATE events SET state=?,next_attempt=?,lease_token=NULL,lease_until=NULL WHERE event_id=?",
                (
                    state,
                    (
                        now
                        + timedelta(
                            seconds=self.config["retry_seconds"] * 2 ** (event["attempts"] - 1)
                        )
                    ).isoformat(),
                    event_id,
                ),
            )
        return payload

    def deliver_next(self, send):
        """Transport injection supports deterministic tests; no default live sender."""
        event = self.claim()
        if event is None:
            return None
        try:
            if not event["recipients"]:
                outcome, reason = "EXCEPTION", "RECIPIENTS_NOT_CONFIGURED"
            else:
                send(event)
                outcome, reason = "SENT", None
        except Exception:
            outcome, reason = "FAILED", "NOTIFICATION_TRANSPORT_FAILED"
        return self.complete(
            event["event_id"],
            DeliveryResult(
                lease_token=event["lease_token"], outcome=outcome, failure_reason=reason
            ),
        )
