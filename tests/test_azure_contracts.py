import json
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from maritime.azure_ml_job import batch, monitor, train
from maritime.ml_contract import export_features, load_features, promotion_check
from maritime.pipeline import load_json


def test_azure_ml_job_logic_preserves_model_and_classifications(tmp_path):
    bundle = load_json("tests/data/portwatch_sample.json")
    export_features(bundle["activity"], tmp_path / "features", "fabric-test-run")
    report = train(
        tmp_path / "features",
        tmp_path / "training",
        load_json("configs/azure.json")["promotion"],
        tracking=False,
    )
    assert report["training_end"] < report["calibration_start"] < report["validation_start"]
    assert report["sla_model_status"] == "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA"
    predictions = batch(tmp_path / "features", tmp_path / "training/model", tmp_path / "inference")
    assert len(predictions) == 6
    assert all(
        p["classification"] == "PREDICTED" and p["fabric_run_id"] == "fabric-test-run"
        for p in predictions
    )
    result = monitor(
        tmp_path / "inference/predictions.json", tmp_path / "features", tmp_path / "monitor"
    )
    assert result["status"] == "AWAITING_SUBSEQUENT_OBSERVATIONS"
    model_path = tmp_path / "training/model/model.joblib"
    model_path.write_bytes(b"not a trusted model")
    with pytest.raises(ValueError, match="integrity"):
        batch(tmp_path / "features", tmp_path / "training/model", tmp_path / "corrupt-inference")
    report["metrics"]["mae"] = report["metrics"]["persistence_mae"] * 2
    assert not promotion_check(report, load_json("configs/azure.json")["promotion"])["eligible"]
    (tmp_path / "features/activity.json").write_text("[]")
    with pytest.raises(ValueError, match="checksum"):
        load_features(tmp_path / "features")


def test_synthetic_data_rejected_at_production_ml_boundary(tmp_path, bundle):
    with pytest.raises(ValueError, match="OBSERVED"):
        export_features(bundle["activity"], tmp_path, "test")


def test_azure_openai_request_and_grounding(monkeypatch):
    from maritime.genai import extract

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://unit-test.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "unit-test-only")
    text = "On 2026-10-01, Port Alpha may close due to storm conditions."
    raw = {
        "quoted_evidence": text,
        "event": "may close",
        "location": "Port Alpha",
        "time": "2026-10-01",
        "confidence": 0.5,
    }

    def response(request):
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["api-key"] == "unit-test-only"
        assert json.loads(request.content)["model"] == "test-deployment"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"signals": [raw, {**raw, "event": "fabricated closure"}]}
                            )
                        }
                    }
                ]
            },
        )

    accepted, metrics = extract(
        text,
        "https://publisher.example",
        client=httpx.Client(transport=httpx.MockTransport(response)),
    )
    assert len(accepted) == 1 and metrics["rejected"] == 1
    assert accepted[0]["classification"] == "ANTICIPATED"


def test_entra_signature_audience_expiry_and_roles(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    import maritime.azure_security as security

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tenant = "12345678-1234-1234-1234-123456789abc"
    monkeypatch.setenv("AZURE_TENANT_ID", tenant)
    monkeypatch.setenv("AZURE_API_AUDIENCE", "api://maritime-test")
    monkeypatch.setattr(
        security,
        "jwks",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
        ),
    )
    claims = {
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "aud": "api://maritime-test",
        "oid": "operator-id",
        "tid": tenant,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
        "roles": ["Maritime.Reader"],
    }

    def token(c):
        return "Bearer " + jwt.encode(c, private, algorithm="RS256")

    assert security.verify_entra(token(claims), "reader")["oid"] == "operator-id"
    for changed, role in [
        (claims, "operator"),
        ({**claims, "aud": "wrong"}, "reader"),
        ({**claims, "exp": 1}, "reader"),
    ]:
        with pytest.raises(HTTPException):
            security.verify_entra(token(changed), role)


def test_fabric_mode_exports_features_instead_of_training(tmp_path):
    from maritime.pipeline import run

    report = run(tmp_path, fixture="tests/data/portwatch_sample.json", ml_backend="azure_ml")
    assert report["ml"]["status"] == "EXPORTED_FOR_AZURE_ML"
    assert not (tmp_path / "models").exists()
    assert (tmp_path / "azure_features" / report["run_id"] / "manifest.json").exists()


def test_azure_serving_checksum_publication_and_audit_isolation(tmp_path, fixture_path):
    from maritime.azure_store import AzureStore
    from maritime.pipeline import run

    class Container:
        def __init__(self):
            self.blobs = {}

        def upload_blob(self, name, data, overwrite=False):
            assert overwrite or name not in self.blobs
            self.blobs[name] = data.encode() if isinstance(data, str) else data

        def download_blob(self, name):
            from azure.core.exceptions import ResourceNotFoundError

            if name not in self.blobs:
                raise ResourceNotFoundError("missing")
            return SimpleNamespace(readall=lambda: self.blobs[name])

        def list_blobs(self, name_starts_with):
            return [SimpleNamespace(name=n) for n in self.blobs if n.startswith(name_starts_with)]

    serving, audit = Container(), Container()
    store = AzureStore(serving, audit)
    report = {"status": "SUCCESS", "data_quality": {"status": "PASS"}, "run_id": "test"}
    with pytest.raises(ValueError, match="Missing required"):
        store.publish(tmp_path, report)
    assert "published.json" not in serving.blobs
    report = run(tmp_path / "pipeline", fixture=fixture_path)
    run_id = report["run_id"]
    manifest = store.publish(tmp_path / "pipeline/gold" / run_id, report)
    assert store.metadata("published_run") == run_id
    assert store.read_approved("ports")[0]["run_id"] == run_id
    store.audit("review", {"operator": "verified-actor"})
    assert len(store.audits("review")) == 1
    assert not any(n.startswith("audit/") for n in serving.blobs)
    serving.blobs[manifest["products"]["ports"]["blob"]] = b"[]"
    with pytest.raises(ValueError, match="checksum"):
        store.read("ports")
