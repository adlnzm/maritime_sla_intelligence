import json
from pathlib import Path

import joblib

from maritime.ml import FEATURES, features, predict
from maritime.pipeline import run
from maritime.store import Store


def test_retained_public_data_end_to_end_and_model_loading(tmp_path):
    sample = Path("tests/data/portwatch_sample.json")
    bundle = json.loads(sample.read_text())
    assert all(r["classification"] == "OBSERVED" for r in bundle["activity"])
    report = run(tmp_path, fixture=sample)
    assert report["status"] == "SUCCESS"
    assert report["ml"]["status"] == "VALIDATED_TEMPORAL_HOLDOUT"
    assert report["ml"]["training_end"] < report["ml"]["calibration_start"]
    assert report["ml"]["calibration_end"] < report["ml"]["validation_start"]
    for comparison in report["ml"]["comparisons"]:
        for fold in comparison["folds"]:
            assert fold["train_end"] < fold["validation_start"]
    artifact = joblib.load(tmp_path / "models" / report["ml"]["model_version"] / "model.joblib")
    frame = features(bundle["activity"]).tail(5)
    assert artifact["features"] == FEATURES
    assert len(predict(artifact["model"], frame)) == 5
    assert all(r["classification"] == "PREDICTED" for r in Store(tmp_path).read("predictions"))
    assert isinstance(
        json.loads((tmp_path / "reports" / report["run_id"] / "report.json").read_text())[
            "network"
        ]["affected_edges"],
        int,
    )
