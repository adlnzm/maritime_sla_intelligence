import pytest

from maritime.genai import verify_signal
from maritime.ml import experiment, features


def test_ml_cannot_train_on_simulation(tmp_path, bundle):
    report, predictions = experiment(bundle["activity"], tmp_path)
    assert report["status"].startswith("DEFERRED")
    assert predictions == []


def test_features_are_lagged(bundle):
    frame = features(bundle["activity"])
    sample = frame[frame.port_id == "A"].iloc[0]
    original = {r["date"]: r["vessel_calls"] for r in bundle["activity"] if r["port_id"] == "A"}
    import pandas as pd

    assert sample.lag1 == original[str((sample.date - pd.Timedelta(days=1)).date())]


def test_grounding_rejects_fabricated_claims():
    text = "On 2026-10-01, Port Alpha may close due to storm conditions."
    signal = {
        "quoted_evidence": text,
        "event": "may close",
        "location": "Port Alpha",
        "time": "2026-10-01",
        "confidence": 0.7,
    }
    assert (
        verify_signal(signal, text, "https://example.org", "2026-10-07T00:00:00Z")["classification"]
        == "ANTICIPATED"
    )
    signal["event"] = "has closed"
    with pytest.raises(ValueError, match="Unsupported"):
        verify_signal(signal, text, "https://example.org", "2026-10-07T00:00:00Z")
