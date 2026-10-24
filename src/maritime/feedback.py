"""Audited learning snapshots; repeated export is content-addressed and replay safe."""

from maritime.governance import fingerprint


def validate_feedback(packet, decisions):
    by_id = {r["decision_id"]: r for r in decisions}
    rows = packet["records"]
    if packet["schema_version"] != "1.0" or fingerprint(rows) != packet["sha256"]:
        raise ValueError("Feedback contract or checksum mismatch")
    ids = [r["audit_id"] for r in rows]
    if len(ids) != len(set(ids)) or len(rows) != packet["record_count"]:
        raise ValueError("Feedback count or duplicate mismatch")
    for row in rows:
        decision = by_id.get(row["decision_id"])
        if (
            not decision
            or row["run_id"] != packet["source_run_id"]
            or decision["run_id"] != packet["source_run_id"]
        ):
            raise ValueError("Feedback references an unknown run or decision")
        if row["kind"] not in {"review", "outcome"} or not row.get("created_at"):
            raise ValueError("Feedback provenance missing")
        if row["classification"] not in {"OBSERVED", "SIMULATED"}:
            raise ValueError("Invalid feedback classification")
        if decision["classification"] == "SIMULATED" and row["classification"] != "SIMULATED":
            raise ValueError("Synthetic decision cannot have observed feedback")
    return rows


def export_feedback(store, run_id):
    if hasattr(store, "verify_audit") and store.verify_audit()["status"] != "PASS":
        raise ValueError("Audit integrity verification failed")
    decisions = store.read_approved("decisions", run_id)
    by_id = {r["decision_id"]: r for r in decisions}
    rows = []
    for kind in ("review", "outcome"):
        for original in store.audits(kind):
            if original.get("run_id") != run_id:
                continue
            row = {**original, "kind": kind}
            if kind == "review":
                row["classification"] = by_id[row["decision_id"]]["classification"]
            rows.append(row)
    rows.sort(key=lambda r: (r["created_at"], r["audit_id"]))
    packet = {
        "schema_version": "1.0",
        "source_run_id": run_id,
        "record_count": len(rows),
        "sha256": fingerprint(rows),
        "records": rows,
        "limitations": "Audited feedback, not causal intervention effectiveness or SLA training eligibility",
    }
    validate_feedback(packet, decisions)
    return packet


def _persist_feedback(packet, decisions, destination):
    """Local destination adapter: atomic insert-only import with actual SQL readback.

    Fabric has a separate Delta adapter; this is not evidence of cloud execution.
    """
    import json
    import sqlite3
    from pathlib import Path

    rows = validate_feedback(packet, decisions)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS feedback (audit_id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL)"
        )
        con.execute("BEGIN IMMEDIATE")
        inserted = duplicates = 0
        for row in rows:
            digest = fingerprint(row)
            existing = con.execute(
                "SELECT sha256 FROM feedback WHERE audit_id=?", (row["audit_id"],)
            ).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError("Feedback audit identity conflict")
                duplicates += 1
            else:
                con.execute(
                    "INSERT INTO feedback VALUES (?,?,?)",
                    (row["audit_id"], json.dumps(row, sort_keys=True, allow_nan=False), digest),
                )
                inserted += 1
        readback = [
            json.loads(
                con.execute(
                    "SELECT payload FROM feedback WHERE audit_id=?", (row["audit_id"],)
                ).fetchone()[0]
            )
            for row in rows
        ]
        if fingerprint(readback) != packet["sha256"]:
            raise ValueError("Feedback destination readback mismatch")
    return {
        "status": "PASS_SQLITE_READBACK",
        "sha256": fingerprint(readback),
        "accounting": {
            "input": len(rows),
            "persisted": inserted,
            "duplicate": duplicates,
            "rejected": 0,
            "quarantined": 0,
            "failed": 0,
        },
    }


def persist_feedback(packet, decisions, destination):
    """Retain a terminal receipt for every atomic import attempt, including failures."""
    import json
    import uuid
    from pathlib import Path

    from maritime.models import utcnow

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "attempt_id": uuid.uuid4().hex,
        "started_at": utcnow(),
        "source_sha256": packet.get("sha256"),
        "source_run_id": packet.get("source_run_id"),
    }
    try:
        result = _persist_feedback(packet, decisions, destination)
        receipt.update(result)
        return result
    except Exception as exc:
        receipt.update(
            status="FAILED",
            failure_type=type(exc).__name__,
            accounting={
                "input": len(packet.get("records", [])),
                "persisted": 0,
                "duplicate": 0,
                "rejected": 0,
                "quarantined": 0,
                "failed": len(packet.get("records", [])),
            },
        )
        raise
    finally:
        receipt["ended_at"] = utcnow()
        folder = path.parent / (path.name + "-receipts")
        folder.mkdir(exist_ok=True)
        (folder / (receipt["attempt_id"] + ".json")).write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
