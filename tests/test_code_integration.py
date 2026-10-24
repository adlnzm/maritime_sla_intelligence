"""Real local application paths with mocked external transports, never live cloud proof."""

import re
import runpy
import sys
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from maritime.api import create_app
from maritime.azure_store import AzureStore
from maritime.pipeline import load_json, run, write_json
from maritime.sources import Fetcher, SourceError
from maritime.store import Store


class BlobContainer:
    """SDK boundary fake; production AzureStore is used unchanged."""

    def __init__(self):
        self.blobs = {}
        self.fail_pointer = False
        self.corrupt_product = False

    def upload_blob(self, name, data, overwrite=False):
        from azure.core.exceptions import ServiceRequestError

        if name == "published.json" and self.fail_pointer:
            raise ServiceRequestError("test transport unavailable")
        assert overwrite or name not in self.blobs
        self.blobs[name] = data.encode() if isinstance(data, str) else data
        if self.corrupt_product and "/ports." in name:
            self.blobs[name] = b"[]"

    def download_blob(self, name):
        from azure.core.exceptions import ResourceNotFoundError

        if name not in self.blobs:
            raise ResourceNotFoundError("missing test blob")
        return SimpleNamespace(readall=lambda: self.blobs[name])

    def list_blobs(self, name_starts_with):
        return [SimpleNamespace(name=n) for n in self.blobs if n.startswith(name_starts_with)]


def test_acquisition_to_publication_api_and_failed_refresh(tmp_path, config, bundle, monkeypatch):
    """HTTP responses -> real adapter -> DQ/checkpoint -> analytics -> SQLite -> API."""
    config["port_names"] = [p["name"] for p in bundle["ports"]]
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    registry = load_json("configs/sources.json")
    registry["sources"] = [s for s in registry["sources"] if s["critical"]]
    registry_path = tmp_path / "sources.json"
    write_json(registry_path, registry)
    root = tmp_path / "data"
    fault = None
    calls = []

    def response(request):
        calls.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("test source timeout", request=request)
        is_ports = "portname IN" in request.url.params["where"]
        rows = (
            [
                {
                    "portid": p["port_id"],
                    "portname": p["name"],
                    "country": p["country"],
                    "lat": p["latitude"],
                    "lon": p["longitude"],
                    "LOCODE": None,
                }
                for p in bundle["ports"]
            ]
            if is_ports
            else [
                {"portid": r["port_id"], "date": r["date"], "portcalls": r["vessel_calls"]}
                for r in bundle["activity"]
            ]
        )
        if not is_ports:
            begin, end = re.findall(r"DATE '([^']+)'", request.url.params["where"])
            rows = [r for r in rows if begin <= r["date"] <= end]
        if fault == "duplicate" and not is_ports:
            rows.append(rows[0])
        if "returnCountOnly" in request.url.params:
            return httpx.Response(200, json={"count": len(rows)})
        return httpx.Response(200, json={"features": [{"attributes": r} for r in rows]})

    def execute(run_id):
        with httpx.Client(transport=httpx.MockTransport(response)) as client:
            return run(
                root,
                config_path,
                registry_path,
                as_of=date.fromisoformat(bundle["as_of"]),
                fetcher=Fetcher(root, client, sleep=lambda _: None),
                run_id=run_id,
                ml_backend="azure_ml",
            )

    report = execute("acquired")
    store = Store(root)
    assert report["execution_mode"] == "LIVE_PUBLIC_DATA"
    assert report["data_quality"]["status"] == "PASS"
    activity = store.read_approved("activity")
    assert {r["date"] for r in activity} == {r["date"] for r in bundle["activity"]}
    assert all(r["retrieved_at"][:10] != r["date"] for r in activity)
    assert all(r["lineage_id"] and r["run_id"] == "acquired" for r in activity)
    assert report["bronze_manifest"]
    assert all(r["classification"] == "SIMULATED" for r in store.read_approved("scenarios"))
    # Exercise data access on the pinned historical run without claiming it is fresh today.
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    client = TestClient(create_app(root))
    headers = {"X-API-Key": "reader"}
    assert client.get("/ports", headers=headers).status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/run-report", headers=headers).json()["run_id"] == "acquired"
    cached = execute("cached")
    assert any(e.get("duplicate_payload") for e in cached["source_status"])
    assert len(store.read_approved("activity")) == len(activity)
    fault = "duplicate"
    with pytest.raises(SourceError, match="Duplicate/conflicting"):
        execute("duplicate")
    assert store.metadata("published_run") == "cached"
    fault = "timeout"
    with pytest.raises(SourceError):
        execute("timeout")
    assert store.metadata("published_run") == "cached"
    assert store.latest_report()["reliability"]["timeouts"] == 4
    assert store.latest_report()["reliability"]["retries"] == 3


def test_blob_interrupted_pointer_retry_and_corrupt_readback(tmp_path, fixture_path):
    from azure.core.exceptions import ServiceRequestError

    report = run(tmp_path / "pipeline", fixture=fixture_path)
    folder = tmp_path / "pipeline/gold" / report["run_id"]
    serving = BlobContainer()
    store = AzureStore(serving, BlobContainer())
    serving.fail_pointer = True
    with pytest.raises(ServiceRequestError):
        store.publish(folder, report)
    assert store.metadata("published_run") is None
    serving.fail_pointer = False
    store.publish(folder, report)
    assert store.metadata("published_run") == report["run_id"]
    assert store.read_approved("ports")
    newer = run(tmp_path / "pipeline", fixture=fixture_path)
    store.publish(tmp_path / "pipeline/gold" / newer["run_id"], newer)
    store.publish(folder, report)
    assert store.metadata("published_run") == newer["run_id"]
    corrupt = BlobContainer()
    corrupt.corrupt_product = True
    store = AzureStore(corrupt, BlobContainer())
    with pytest.raises(ValueError, match="checksum"):
        store.publish(folder, report)
    assert "published.json" not in corrupt.blobs
    with pytest.raises(ValueError, match="checksum"):
        store.publish(folder, report)
    assert "published.json" not in corrupt.blobs


def test_blob_read_pins_publication(tmp_path, fixture_path, monkeypatch):
    report = run(tmp_path / "pipeline", fixture=fixture_path)
    store = AzureStore(BlobContainer(), BlobContainer())
    store.publish(tmp_path / "pipeline/gold" / report["run_id"], report)
    calls = []

    def moving_pointer(key, default=None):
        calls.append(key)
        return report["run_id"] if len(calls) == 1 else "not-yet-visible"

    monkeypatch.setattr(store, "metadata", moving_pointer)
    assert store.read_approved("ports")[0]["run_id"] == report["run_id"]
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["/ready", "/ports", "/audit", "/metrics", "/run-report"])
def test_api_cloud_dependency_errors_are_redacted_503(tmp_path, monkeypatch, path):
    from azure.core.exceptions import ServiceRequestError

    store = AzureStore(BlobContainer(), BlobContainer())

    def unavailable(*args, **kwargs):
        raise ServiceRequestError("sensitive-test-value")

    monkeypatch.setattr(store.container, "download_blob", unavailable)
    monkeypatch.setattr(store.audit_container, "list_blobs", unavailable)
    monkeypatch.setattr("maritime.azure_store.AzureStore", lambda: store)
    monkeypatch.setenv("MARITIME_STORAGE_BACKEND", "azure_blob")
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    client = TestClient(create_app(tmp_path))
    response = client.get(path, headers={"X-API-Key": "operator"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Dependency unavailable"}
    assert response.headers["X-Correlation-ID"]
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://account.blob.core.windows.net",
        "https://user:secret@account.example",
        "https://account.example/?sig=test",
        "https://account.example/container",
    ],
)
def test_blob_configuration_rejected_before_authentication(monkeypatch, url):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", url)

    def forbidden():
        pytest.fail("Invalid configuration must not acquire credentials")

    monkeypatch.setattr("maritime.azure_security.credential", forbidden)
    with pytest.raises(ValueError, match="HTTPS account endpoint"):
        AzureStore()


def test_blob_identity_configuration_and_timeouts(monkeypatch):
    import azure.storage.blob

    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://account.blob.core.windows.net")
    identity = object()
    captured = {}

    class Service:
        def __init__(self, url, **kwargs):
            captured.update(url=url, **kwargs)

        def get_container_client(self, name):
            return name

    monkeypatch.setattr(azure.storage.blob, "BlobServiceClient", Service)
    monkeypatch.setattr("maritime.azure_security.credential", lambda: identity)
    store = AzureStore()
    assert captured["credential"] is identity
    assert captured["connection_timeout"] == 5 and captured["read_timeout"] == 15
    assert captured["retry_total"] == 3
    assert store.container == "maritime-serving" and store.audit_container == "maritime-audit"
    monkeypatch.setenv("AZURE_AUDIT_CONTAINER", "maritime-serving")
    with pytest.raises(ValueError, match="must differ"):
        AzureStore()


def test_fabric_task_dependency_retry_receipts_and_run_identity(tmp_path):
    from maritime.fabric_runtime import fabric_gate

    executions = []

    @fabric_gate("bronze")
    def bronze(root, run_id, fail=False):
        executions.append("bronze")
        if fail:
            raise TimeoutError("source unavailable")
        return {"rows": 3}

    @fabric_gate("silver")
    def silver(root, run_id):
        executions.append("silver")
        return {"accepted": 3}

    with pytest.raises(ValueError, match="dependency"):
        silver(tmp_path, "test")
    assert not executions
    assert bronze(tmp_path, "test") == {"rows": 3}
    assert silver(tmp_path, "test") == {"accepted": 3}
    with pytest.raises(TimeoutError):
        bronze(tmp_path, "test", fail=True)
    with pytest.raises(ValueError, match="dependency"):
        silver(tmp_path, "test")
    folder = tmp_path / "runs/test/stage-evidence"
    completed = sorted(folder.glob("bronze-*-completed.json"))
    receipt = load_json(completed[-1])
    assert receipt["status"] == "BLOCKED" and receipt["failure_type"] == "TimeoutError"
    bronze(tmp_path, "test")
    assert silver(tmp_path, "test") == {"accepted": 3}
    receipt = load_json(sorted(folder.glob("bronze-*-started.json"))[-1])
    receipt["execution_id"] = "future-incomplete-attempt"
    write_json(folder / "bronze-9999-started.json", receipt)
    with pytest.raises(ValueError, match="dependency"):
        silver(tmp_path, "test")
    with pytest.raises(ValueError, match="identifier"):
        bronze(tmp_path, "../escape")


@pytest.mark.parametrize("freshness_days", [9, 11])
def test_pipeline_rejects_freshness_configuration_drift(
    tmp_path, fixture_path, config, freshness_days
):
    from maritime.governance import GovernanceError

    config["freshness_days"] = freshness_days
    path = tmp_path / "config.json"
    write_json(path, config)
    with pytest.raises(GovernanceError, match="freshness_days"):
        run(tmp_path / "run", config_path=path, fixture=fixture_path)
    store = Store(tmp_path / "run")
    assert store.latest_report()["status"] == "FAILED"
    assert store.metadata("published_run") is None


def test_forecasts_are_supplemental_and_failure_preserves_publication(tmp_path, monkeypatch):
    import maritime.pipeline as pipeline

    sample = "tests/data/portwatch_sample.json"
    report = run(tmp_path, fixture=sample, run_id="research")
    store = Store(tmp_path)
    predictions = store.read_approved("predictions")
    decisions = store.read_approved("decisions")
    assert predictions and all(p["classification"] == "PREDICTED" for p in predictions)
    assert all(d["forecast_usage"] == "NOT_USED_FOR_RANKING" for d in decisions)
    assert report["decision"]["forecast_affects_ranking"] is False
    # A deliberately changed forecast result must not change scenario rankings.
    changed = [
        {**p, "vessel_calls": p["vessel_calls"] + 100, "upper": p["upper"] + 100}
        for p in predictions
    ]
    monkeypatch.setattr(pipeline, "experiment", lambda *args: (report["ml"], changed))
    run(tmp_path, fixture=sample, run_id="different-forecast")
    keys = ("shipment_id", "recommended_action", "expected_benefit", "expected_delay_avoided")
    assert [[d[k] for k in keys] for d in store.read_approved("decisions")] == [
        [d[k] for k in keys] for d in decisions
    ]
    assert store.read_approved("predictions")[0]["vessel_calls"] == changed[0]["vessel_calls"]

    def failed(*args):
        raise TimeoutError("forecast dependency unavailable")

    monkeypatch.setattr(pipeline, "experiment", failed)
    with pytest.raises(TimeoutError):
        run(tmp_path, fixture=sample, run_id="forecast-failure")
    assert store.metadata("published_run") == "different-forecast"
    assert store.latest_report()["status"] == "FAILED"


def test_fabric_rest_identity_retry_polling_and_timeout_contract(monkeypatch):
    adapter = runpy.run_path("scripts/deploy_fabric.py")
    fabric_type = adapter["Fabric"]
    sleeps, scopes, calls = [], [], []
    monkeypatch.setattr(adapter["time"], "sleep", sleeps.append)

    def token(scope):
        scopes.append(scope)
        return SimpleNamespace(token="test-only")

    def response(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-only"
        if len(calls) < 3:
            return httpx.Response(503, headers={"Retry-After": "malformed"})
        return httpx.Response(200, json={"value": [{"id": "test-item"}]})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        fabric = fabric_type(
            "12345678-1234-1234-1234-123456789abc",
            credential=SimpleNamespace(get_token=token),
            client=client,
        )
        assert fabric.items() == [{"id": "test-item"}]
        assert sleeps == [1, 2]
        assert scopes == ["https://api.fabric.microsoft.com/.default"] * 3
        with pytest.raises(ValueError, match="Unexpected"):
            fabric.request("GET", "https://unexpected.example/operation")
        with pytest.raises(ValueError, match="polling"):
            fabric.finish(
                httpx.Response(202, headers={"Location": "https://unexpected.example/operation"})
            )
    calls.clear()

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("contract timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        fabric.client = client
        with pytest.raises(httpx.ReadTimeout):
            fabric.request("GET", "/operations/test")
        assert len(calls) == 4
        calls.clear()
        with pytest.raises(httpx.ReadTimeout):
            fabric.request("POST", "/workspaces/test/items", json={})
        assert len(calls) == 1


def test_azure_ml_configuration_precedes_sdk_and_maps_identity(monkeypatch):
    import azure.identity

    factory = runpy.run_path("scripts/azure_ml.py")["client"]
    config = load_json("configs/azure.json")
    with pytest.raises(ValueError, match="ENVIRONMENT_DEPENDENT"):
        factory(config)
    identity = object()
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", lambda: identity)
    monkeypatch.setitem(sys.modules, "azure.ai.ml", SimpleNamespace(MLClient=lambda *args: args))
    for name, value in (
        ("AZURE_SUBSCRIPTION_ID", "contract-subscription"),
        ("AZURE_RESOURCE_GROUP", "contract-group"),
        ("AZURE_ML_WORKSPACE", "contract-workspace"),
    ):
        monkeypatch.setenv(name, value)
    assert factory(config) == (
        identity,
        "contract-subscription",
        "contract-group",
        "contract-workspace",
    )


def test_prediction_return_to_fabric_decisions_and_serving_contract(tmp_path, monkeypatch):
    """Exercise import orchestration with a fake Delta boundary, not live Spark/Delta."""
    import maritime.fabric_runtime as runtime
    from maritime.governance import fingerprint, verify_manifest
    from maritime.ml import FEATURE_VERSION
    from maritime.ml_contract import load_features, prediction_manifest

    run_id = "fabric-contract"
    folder = tmp_path / "runs" / run_id
    report = run(
        folder / "evidence",
        fixture="tests/data/portwatch_sample.json",
        run_id=run_id,
        ml_backend="azure_ml",
    )
    report["delta_counts"] = {"fact_predictions": 0}
    write_json(folder / "fabric-report.json", report)
    write_json(
        folder / "stage-evidence/acceptance-test-completed.json",
        {
            "run_id": run_id,
            "stage": "acceptance",
            "status": "PASS",
            "execution_id": "test",
            "contract_fingerprint": report["governance"]["contract_fingerprint"],
        },
    )
    activity, _ = load_features(folder / "evidence/azure_features" / run_id)
    latest = {}
    for row in activity:
        latest[row["port_id"]] = max(latest.get(row["port_id"], row["date"]), row["date"])
    predictions = [
        {
            "port_id": port,
            "date": str(date.fromisoformat(day) + timedelta(days=1)),
            "vessel_calls": 10.0,
            "lower": 0.0,
            "upper": 20.0,
            "classification": "PREDICTED",
            "fabric_run_id": run_id,
            "feature_version": FEATURE_VERSION,
            "model_version": "contract-model",
            "lineage_id": "contract-test",
            "generated_at": "2026-10-10T00:00:00Z",
        }
        for port, day in latest.items()
    ]
    manifest = prediction_manifest(
        predictions, activity, run_id, "azureml:contract-only", "contract-job-not-live"
    )
    write_json(folder / "azure-ml-predictions.json", predictions)
    write_json(folder / "azure-ml-prediction-manifest.json", manifest)
    tables = {}

    def write(spark, rows, table, selected_run):
        assert selected_run == run_id
        tables[table] = [{**r, "run_id": selected_run} for r in rows]
        return len(rows)

    class Frame:
        def filter(self, condition):
            assert condition
            return self

        def count(self):
            return len(tables["fact_predictions"])

        def collect(self):
            return [
                SimpleNamespace(asDict=lambda recursive, row=row: row)
                for row in tables["fact_predictions"]
            ]

    monkeypatch.setattr(runtime, "delta_write", write)
    monkeypatch.setitem(
        sys.modules,
        "pyspark.sql",
        SimpleNamespace(functions=SimpleNamespace(col=lambda name: run_id)),
    )
    exported = folder / "evidence/gold" / run_id
    before = load_json(exported / "decisions.json")
    assert (
        runtime.import_predictions(SimpleNamespace(table=lambda name: Frame()), tmp_path, run_id)
        == 6
    )
    after = load_json(exported / "decisions.json")
    assert [d["recommended_action"] for d in after] == [d["recommended_action"] for d in before]
    assert all(
        d["forecast_evidence"]
        and d["forecast_usage"] == "SUPPLEMENTAL_PORT_ACTIVITY_EVIDENCE_NOT_SLA_PROBABILITY"
        for d in after
    )
    products = {p.stem: load_json(p) for p in exported.glob("*.json")}
    returned_lineage = {row["resulting_field"]: row for row in products["lineage"]}
    assert returned_lineage["predictions.vessel_calls"]["input_tables"] == ["activity"]
    assert returned_lineage["decisions.forecast_evidence"]["input_tables"] == ["predictions"]
    updated = load_json(folder / "fabric-report.json")
    verify_manifest(products, updated["release"])
    assert updated["release"]["prediction_return"]["prediction_sha256"] == fingerprint(predictions)
    assert updated["release"]["parent_release_id"] == report["release"]["release_id"]
    serving = AzureStore(BlobContainer(), BlobContainer())
    serving.publish(exported, updated)
    assert len(serving.read_approved("predictions")) == 6
    assert serving.read_approved("decisions")[0]["forecast_evidence"]
