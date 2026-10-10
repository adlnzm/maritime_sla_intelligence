import copy
import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from maritime.governance import (
    GovernanceError,
    contract,
    exclusive_run,
    fingerprint,
    verify_manifest,
)
from maritime.pipeline import load_json, run, write_json
from maritime.quality import validate
from maritime.store import Store


def test_exclusive_dispositions_and_temporal_coverage(bundle, routes):
    rows = copy.deepcopy(bundle["activity"])
    rows[20].update(port_id="missing", date="2099-01-01")
    rows.append(dict(rows[1]))
    clean, dq = validate(bundle["ports"], rows, routes, date.fromisoformat(bundle["as_of"]))
    assert dq["status"] == "FAIL"
    assert dq["accounting"] == {
        "received": len(bundle["ports"]) + len(rows) + len(routes),
        "accepted": len(bundle["ports"]) + len(rows) + len(routes) - 2,
        "rejected": 2,
        "quarantined": 0,
        "balanced": True,
    }
    assert all(r["port_id"] != "missing" for r in clean["activity"])
    assert sum(d["status"] == "rejected" for d in dq["dispositions"]) == 2
    assert any(e["check"] == "missing_period" for e in dq["errors"])


def test_fail_closed_publication_idempotency_recovery_and_audit(
    tmp_path, fixture_path, monkeypatch
):
    import maritime.pipeline as pipeline
    from maritime.api import create_app

    root = tmp_path / "pipeline"
    approved = run(root, fixture=fixture_path, run_id="approved")
    store = Store(root)
    assert approved["governance"]["industrial_release"]["status"] == "BLOCKED"
    assert (
        run(root, fixture=fixture_path, run_id="approved")["release"]["release_id"]
        == approved["release"]["release_id"]
    )
    assert store.verify_audit()["status"] == "PASS"
    with store.connect() as connection:
        for sql in (
            "DELETE FROM audit",
            "UPDATE audit SET kind='tampered'",
            "DELETE FROM products WHERE run_id='approved'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql)
    with exclusive_run(root), pytest.raises(GovernanceError, match="Overlapping"):
        run(root, fixture=fixture_path)
    original = pipeline.congestion

    def corrupt(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows[-1]["baseline"] += 10
        return rows

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "congestion", corrupt)
        with pytest.raises(GovernanceError, match="metrics BLOCKED"):
            run(root, fixture=fixture_path, run_id="invalid-metric")
    assert store.metadata("published_run") == "approved"
    assert store.latest_report()["governance"]["stages"]["scenario"]["status"] == "NOT_EVALUATED"
    monkeypatch.setenv("MARITIME_API_KEY", "governance-reader")
    client = TestClient(create_app(root))
    headers = {"X-API-Key": "governance-reader"}
    assert client.get("/ports?run_id=invalid-metric", headers=headers).status_code == 503
    assert client.get("/ports", headers=headers).status_code == 200
    store.run({"run_id": "interrupted", "status": "RUNNING", "start_time": "2026-01-01T00:00:00Z"})
    recovered = run(root, fixture=fixture_path, run_id="recovered")
    assert store.metadata("published_run") == "recovered"
    assert store.audits("recovery")[-1]["run_id"] == "interrupted"
    data = {n: store.read(n, "recovered") for n in recovered["release"]["datasets"]}
    invalid = copy.deepcopy(recovered["release"])
    invalid["stage_evidence"]["silver"]["status"] = "NOT_EVALUATED"
    with pytest.raises(GovernanceError, match="mandatory release stage"):
        verify_manifest(data, invalid)
    data["ports"][0]["latitude"] += 0.1
    with pytest.raises(GovernanceError, match="content mismatch"):
        verify_manifest(data, recovered["release"])


def test_interrupted_persistence_does_not_publish(tmp_path, fixture_path, monkeypatch):
    first = run(tmp_path, fixture=fixture_path)
    original = Store.write

    def partial(self, run_id, product, records):
        original(self, run_id, product, records[:-1] if product == "decisions" else records)

    monkeypatch.setattr(Store, "write", partial)
    with pytest.raises(GovernanceError, match="content mismatch"):
        run(tmp_path, fixture=fixture_path)
    assert Store(tmp_path).metadata("published_run") == first["run_id"]


def test_prediction_import_contract_adverse_cases():
    from maritime.ml import FEATURE_VERSION
    from maritime.ml_contract import prediction_manifest, validate_predictions

    activity = load_json("tests/data/portwatch_sample.json")["activity"]
    latest = {}
    for r in activity:
        latest[r["port_id"]] = max(latest.get(r["port_id"], r["date"]), r["date"])
    rows = [
        {
            "port_id": p,
            "date": str(date.fromisoformat(day) + timedelta(days=1)),
            "vessel_calls": 10.0,
            "lower": 0.0,
            "upper": 20.0,
            "classification": "PREDICTED",
            "fabric_run_id": "test",
            "feature_version": FEATURE_VERSION,
            "model_version": "test-v1",
            "lineage_id": "test-contract-not-cloud-evidence",
            "generated_at": "2026-10-10T00:00:00Z",
        }
        for p, day in latest.items()
    ]
    manifest = prediction_manifest(
        rows, activity, "test", "azureml:test-contract-only", "test-job-not-live"
    )
    assert validate_predictions(rows, manifest, activity, "test")["status"] == "PASS"
    for bad in (
        rows[:-1],
        rows + [rows[0]],
        [{**r, "classification": "OBSERVED"} for r in rows],
        [{**r, "lower": 99} for r in rows],
    ):
        modified = {**manifest, "prediction_sha256": fingerprint(bad), "record_count": len(bad)}
        with pytest.raises(ValueError):
            validate_predictions(bad, modified, activity, "test")
    with pytest.raises(ValueError, match="checksum"):
        validate_predictions(rows, {**manifest, "prediction_sha256": "wrong"}, activity, "test")
    with pytest.raises(ValueError, match="Unapproved"):
        validate_predictions(rows, {**manifest, "approval_status": "CANDIDATE"}, activity, "test")


def test_unknown_contract_fails(tmp_path):
    value = contract()
    value["version"] = "999"
    path = tmp_path / "contract.json"
    write_json(path, value)
    with pytest.raises(GovernanceError, match="Unknown"):
        contract(path)


@pytest.mark.parametrize(
    "fault", ["stale", "schema", "classification", "coordinates", "missing_lineage"]
)
def test_canonical_adverse_controls(bundle, routes, fault):
    bundle = copy.deepcopy(bundle)
    day = date.fromisoformat(bundle["as_of"])
    if fault == "stale":
        day += timedelta(days=11)
    elif fault == "schema":
        bundle["activity"][0]["vessel_calls"] = "not-a-number"
    elif fault == "classification":
        bundle["activity"][0]["classification"] = "PREDICTED"
    elif fault == "coordinates":
        bundle["ports"][0]["longitude"] = 181
    else:
        bundle["activity"][0]["lineage_id"] = ""
    _, quality = validate(bundle["ports"], bundle["activity"], routes, day)
    assert quality["status"] == "FAIL"
    assert quality["accounting"]["balanced"]


def test_feature_skew_rejected_even_with_matching_file_hash(tmp_path):
    import hashlib

    from maritime.ml_contract import export_features, load_features

    activity = load_json("tests/data/portwatch_sample.json")["activity"]
    manifest = export_features(activity, tmp_path, "test")
    path = tmp_path / "features.csv"
    path.write_bytes(path.read_bytes().replace(b"lag1", b"unknown_feature"))
    manifest["files"]["features.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="skew"):
        load_features(tmp_path)


def test_raw_mutation_and_partial_extract_block(tmp_path):
    import httpx

    from maritime.sources import Fetcher, SourceError

    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"value": 1}))
    )
    fetch = Fetcher(tmp_path, client)
    _, event = fetch.get("test", "https://example.org")
    from pathlib import Path

    Path(event["raw_path"]).write_text("tampered")
    with pytest.raises(SourceError, match="modified"):
        fetch.get("test", "https://example.org")

    def partial(request):
        return httpx.Response(
            200,
            json={"count": 2}
            if "returnCountOnly" in request.url.params
            else {"features": [{"attributes": {"id": 1}}]},
        )

    fetch = Fetcher(tmp_path, httpx.Client(transport=httpx.MockTransport(partial)))
    with pytest.raises(SourceError, match="Partial extract"):
        fetch.arcgis(
            {
                "source_id": "partial",
                "source_url": "https://example.org",
                "required_fields": ["id"],
                "reconcile_count": True,
            },
            "1=1",
        )
