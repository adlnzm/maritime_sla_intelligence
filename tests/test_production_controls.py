import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from maritime.api import create_app
from maritime.feedback import export_feedback, persist_feedback
from maritime.governance import fingerprint
from maritime.pipeline import run
from maritime.recovery import backup, restore
from maritime.store import Store


@pytest.mark.parametrize("operation", ["decisions", "review", "outcome"])
def test_response_pins_decision_release_and_audit_during_publication(
    tmp_path, fixture_path, monkeypatch, operation
):
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    old = run(tmp_path / "data", fixture=fixture_path)
    store = Store(tmp_path / "data")
    decision = store.read_approved("decisions")[0]
    store.audit(
        "review",
        {"run_id": old["run_id"], "decision_id": decision["decision_id"], "status": "accept"},
    )
    client = TestClient(create_app(tmp_path / "data"))
    captured, published = Event(), Event()
    original = Store.read_approved

    def overlapping_read(self, product, run_id=None):
        rows = original(self, product, run_id)
        if product == "decisions" and not captured.is_set():
            captured.set()
            assert published.wait(60), "Concurrent publication did not complete"
        return rows

    monkeypatch.setattr(Store, "read_approved", overlapping_read)

    def request():
        headers = {"X-API-Key": "operator"}
        if operation == "decisions":
            return client.get("/decisions", headers=headers)
        if operation == "review":
            return client.post(
                f"/decisions/{decision['decision_id']}/review",
                headers=headers,
                json={"status": "reject", "reason": "Race regression", "operator": "test"},
            )
        return client.post(
            "/outcomes",
            headers=headers,
            json={
                "decision_id": decision["decision_id"],
                "actual_action": decision["recommended_action"],
                "actual_delay_hours": 5,
                "actual_loss": 10,
                "classification": "SIMULATED",
                "evidence": "Simulated regression",
            },
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(request)
        try:
            assert captured.wait(15)
            new = run(tmp_path / "data", fixture=fixture_path)
            assert new["run_id"] != old["run_id"]
        finally:
            published.set()
        response = pending.result(timeout=15)
    assert response.status_code == 200, response.text
    body = response.json()
    assert store.metadata("published_run") == new["run_id"]
    assert body["run_id"] == old["run_id"]
    if operation == "decisions":
        assert body["release"]["run_id"] == old["run_id"]
        assert all(row["run_id"] == old["run_id"] for row in body["items"])
        reviewed = next(
            row for row in body["items"] if row["decision_id"] == decision["decision_id"]
        )
        assert reviewed["review"]["run_id"] == old["run_id"]
    else:
        assert body["decision_id"] == decision["decision_id"]
        assert any(
            row["run_id"] == old["run_id"] and row["audit_id"] == body["audit_id"]
            for row in store.audits(operation)
        )
    assert store.verify_audit()["status"] == "PASS"


def test_concurrent_business_retry_and_orphan_detection(tmp_path):
    store = Store(tmp_path)
    payload = {"run_id": "r", "decision_id": "d", "status": "accept"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: store.audit("review", payload), range(20)))
    assert len(set(ids)) == 1
    assert len(store.audits("review")) == 1
    assert store.verify_audit()["verified_records"] == 1
    with store.connect() as con:
        con.execute(
            "INSERT INTO audit_chain(audit_id,previous_hash,digest) VALUES ('missing','x','x')"
        )
    with pytest.raises(ValueError, match="orphaned"):
        store.verify_audit()


def test_empty_legacy_and_future_database_schema(tmp_path):
    store = Store(tmp_path)
    store.audit("review", {"legacy": "preserved"})
    with store.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1
        con.execute("PRAGMA user_version=0")
    assert Store(tmp_path).audits("review")[0]["legacy"] == "preserved"
    with store.connect() as con:
        con.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError, match="newer"):
        Store(tmp_path)
    with sqlite3.connect(store.path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 999


def test_feedback_real_destination_replay_and_atomic_conflict(tmp_path, fixture_path):
    report = run(tmp_path / "source", fixture=fixture_path)
    store = Store(tmp_path / "source")
    decisions = store.read_approved("decisions")
    for status in ("accept", "reject"):
        store.audit(
            "review",
            {
                "run_id": report["run_id"],
                "decision_id": decisions[0]["decision_id"],
                "status": status,
            },
        )
    packet = export_feedback(store, report["run_id"])
    target = tmp_path / "destination.db"
    receipt = persist_feedback(packet, decisions, target)
    assert receipt["accounting"]["persisted"] == 2
    replay = persist_feedback(packet, decisions, target)
    assert replay["accounting"]["duplicate"] == 2
    old = {**packet, "records": packet["records"][:1], "record_count": 1}
    old["sha256"] = fingerprint(old["records"])
    persist_feedback(old, decisions, target)
    corrupt = copy.deepcopy(packet)
    corrupt["records"][0]["audit_id"] = "new-before-conflict"
    corrupt["records"][1]["status"] = "override"
    corrupt["sha256"] = fingerprint(corrupt["records"])
    with pytest.raises(ValueError, match="identity conflict"):
        persist_feedback(corrupt, decisions, target)
    with sqlite3.connect(target) as con:
        assert con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 2
    receipts = [
        json.loads(p.read_text()) for p in (tmp_path / "destination.db-receipts").glob("*.json")
    ]
    assert any(r["status"] == "FAILED" and r["accounting"]["failed"] == 2 for r in receipts)
    assert persist_feedback(packet, decisions, target)["sha256"] == packet["sha256"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: persist_feedback(packet, decisions, target), range(8)))
    assert all(r["accounting"]["duplicate"] == 2 for r in results)


def test_actual_backup_restore_and_tamper(tmp_path, fixture_path):
    source = tmp_path / "source"
    report = run(source, fixture=fixture_path)
    store = Store(source)
    store.audit("review", {"run_id": report["run_id"], "status": "accept"})
    snapshot = tmp_path / "snapshot"
    manifest = backup(source, snapshot)
    receipt = restore(snapshot, tmp_path / "restored")
    assert receipt["published_run"] == report["run_id"]
    assert receipt["audit"] == manifest["verification"]["audit"]
    with pytest.raises(ValueError, match="new, non-overlapping"):
        restore(snapshot, source)
    with pytest.raises(ValueError, match="new, non-overlapping"):
        backup(source, source / "nested")
    (snapshot / "maritime.db").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        restore(snapshot, tmp_path / "tampered-restore")
    assert not (tmp_path / "tampered-restore").exists()


def test_api_large_and_chunked_requests_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    client = TestClient(create_app(tmp_path))
    result = client.post("/outcomes", content=b"a" * 65537)
    assert result.status_code == 413
    assert result.headers["X-Correlation-ID"]
    result = client.post("/outcomes", content=iter([b"a" * 40000, b"b" * 40000]))
    assert result.status_code == 413
    assert client.get("/health").status_code == 200


def test_aoai_bounded_retry_timeout_and_no_fabricated_fallback(monkeypatch):
    from maritime.genai import extract

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-only")
    delays = []
    monkeypatch.setattr("maritime.genai.time.sleep", delays.append)
    calls = []

    def transient(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "900"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"signals": []})}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(transient)) as client:
        signals, metrics = extract("Public text", "https://source.example", client=client)
    assert signals == [] and metrics["attempts"] == 3
    assert delays == [5, 5]
    calls.clear()

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("test timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(httpx.ReadTimeout):
            extract("Public text", "https://source.example", client=client)
    assert len(calls) == 4
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://user:password@test.openai.azure.com")
    with pytest.raises(ValueError, match="HTTPS Azure"):
        extract("Public text", "https://source.example")


def test_powerbi_schemas_and_governed_field_bindings(tmp_path, fixture_path):
    import runpy

    report = run(tmp_path / "data", fixture=fixture_path)
    store = Store(tmp_path / "data")
    definitions = runpy.run_path("scripts/build_powerbi.py")
    folder = definitions["build"](tmp_path / "report")
    assert definitions["validate"](folder)["files"] == 29
    for _, _, table, date_field, columns in definitions["PAGES"]:
        rows = store.read_approved(table.removeprefix("fact_"), report["run_id"])
        assert rows
        # Delta's rectangular schema has nullable fields for infeasible alternatives.
        # Check the actual union of analytical columns and every eligible numeric row.
        fields = set(columns + [date_field, "run_id", "lineage_id", "classification"])
        assert fields <= set().union(*(row.keys() for row in rows))
        for row in rows:
            if table == "fact_interventions" and not row["feasible"]:
                assert row["reason"] and "expected_loss" not in row
                assert {date_field, "run_id", "lineage_id", "classification"} <= row.keys()
            else:
                assert fields <= row.keys()


def test_release_rejects_source_mismatch(monkeypatch):
    from maritime.release_evidence import verify_source

    monkeypatch.setattr("maritime.release_evidence.source_snapshot", lambda: {"a.py": "new"})
    with pytest.raises(ValueError, match="Source changed"):
        verify_source({"a.py": "old"})
