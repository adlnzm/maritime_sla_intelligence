import pytest
from fastapi.testclient import TestClient

from maritime.api import create_app


def test_startup_requires_auth_and_separates_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_AUTH_MODE", "key")
    monkeypatch.delenv("MARITIME_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MARITIME_API_KEY"):
        create_app(tmp_path)
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "reader")
    with pytest.raises(ValueError, match="must differ"):
        create_app(tmp_path)
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").status_code == 200
    result = client.get("/ready", headers={"X-API-Key": "reader"})
    assert result.status_code == 503
    assert len(result.headers["X-Correlation-ID"]) == 32


def test_invalid_configuration_is_retained(tmp_path):
    from maritime.pipeline import run
    from maritime.store import Store

    with pytest.raises(FileNotFoundError):
        run(tmp_path, config_path=tmp_path / "missing.json")
    store = Store(tmp_path)
    assert store.latest_report()["stage_status"] == {"preflight": "BLOCKED"}
    assert store.latest_report()["status"] == "FAILED"
    assert store.metadata("published_run") is None
    assert store.verify_audit()["status"] == "PASS"


def test_gate_initialization_failure_is_retained(tmp_path, monkeypatch):
    import maritime.pipeline as pipeline
    from maritime.store import Store

    def unavailable(*args):
        raise ValueError("Invalid gate contract")

    monkeypatch.setattr(pipeline, "Gates", unavailable)
    with pytest.raises(ValueError, match="Invalid gate"):
        pipeline.run(tmp_path, run_id="bad-contract")
    report = Store(tmp_path).latest_report()
    assert report["run_id"] == "bad-contract"
    assert report["status"] == "FAILED"
