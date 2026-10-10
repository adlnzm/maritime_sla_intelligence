import json

import pytest
from fastapi.testclient import TestClient

from maritime.api import create_app
from maritime.pipeline import run
from maritime.store import Store


def test_full_pipeline_api_override_and_recovery(tmp_path, fixture_path, monkeypatch):
    root = tmp_path / "run"
    report = run(root, fixture=fixture_path)
    assert report["status"] == "SUCCESS"
    assert report["scenarios"]["executions"] == 300
    assert report["network"]["propagation_results"] > 0
    assert report["ml"]["status"].startswith("DEFERRED")
    store = Store(root)
    first = store.read("decisions")
    second = run(root, fixture=fixture_path)
    assert [d["recommended_action"] for d in first] == [
        d["recommended_action"] for d in store.read("decisions")
    ]
    monkeypatch.setenv("MARITIME_API_KEY", "reader-test-key")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator-test-key")
    client = TestClient(create_app(root))
    assert client.get("/health").status_code == 200
    assert client.get("/ports").status_code == 401
    reader = {"X-API-Key": "reader-test-key"}
    operator = {"X-API-Key": "operator-test-key"}
    for path in (
        "/ready",
        "/ports",
        "/congestion",
        "/network",
        "/network/exposure",
        "/disruptions",
        "/scenarios",
        "/sla-risk",
        "/interventions",
        "/decisions",
        "/lineage",
        "/data-quality",
        "/metrics",
    ):
        assert client.get(path, headers=reader).status_code == 200, path
    assert client.get("/ports?limit=-1", headers=reader).status_code == 422
    decision = store.read("decisions")[0]
    path = f"/decisions/{decision['decision_id']}/review"
    body = {
        "status": "override",
        "action": "NO_ACTION",
        "reason": "Regression operator review",
        "operator": "test",
    }
    assert client.post(path, json=body, headers=reader).status_code == 403
    assert client.post(path, json=body, headers=operator).status_code == 200
    assert client.get("/decisions", headers=reader).json()["items"][0]["status"] == "OVERRIDDEN"
    observed = {
        "decision_id": decision["decision_id"],
        "actual_action": "NO_ACTION",
        "actual_delay_hours": 24,
        "actual_loss": 100,
        "classification": "OBSERVED",
        "evidence": "test evidence",
    }
    assert client.post("/outcomes", json=observed, headers=operator).status_code == 422
    observed["classification"] = "SIMULATED"
    assert client.post("/outcomes", json=observed, headers=operator).status_code == 200
    assert store.audits("outcome")[0]["causal_intervention_effectiveness"] is None
    bad = json.loads(fixture_path.read_text())
    bad["ports"][0]["latitude"] = 100
    fixture_path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="DQ failed"):
        run(root, fixture=fixture_path)
    assert store.metadata("published_run") == second["run_id"]
    assert store.latest_report()["status"] == "FAILED"
    assert (root / "gold" / report["run_id"] / "operational.geojson").is_file()
