"""Content-verified boundary between Fabric Gold and Azure ML jobs."""

import hashlib
import json
from pathlib import Path

from maritime.ml import FEATURE_VERSION, FEATURES, features
from maritime.models import Activity, utcnow
from maritime.pipeline import write_json


def export_features(activity, folder, run_id):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    clean = []
    for row in activity:
        fields = {k: row[k] for k in Activity.model_fields if k in row}
        item = Activity.model_validate(fields).model_dump(mode="json")
        if item["classification"] != "OBSERVED":
            raise ValueError("Production forecasting accepts only OBSERVED port activity")
        clean.append(item)
    if not clean:
        raise ValueError("Empty activity export")
    keys = [(r["port_id"], r["date"]) for r in clean]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate port/date in feature export")
    write_json(folder / "activity.json", clean)
    frame = features(clean)
    frame.to_csv(folder / "features.csv", index=False)
    manifest = {
        "contract_version": "1",
        "feature_version": FEATURE_VERSION,
        "features": FEATURES,
        "target": "next-day vessel_calls",
        "classification": "DERIVED",
        "input_classification": "OBSERVED",
        "fabric_run_id": run_id,
        "exported_at": utcnow(),
        "records": len(clean),
        "files": {
            name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in ("activity.json", "features.csv")
        },
    }
    write_json(folder / "manifest.json", manifest)
    return manifest


def load_features(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["feature_version"] != FEATURE_VERSION or manifest["features"] != FEATURES:
        raise ValueError("Feature/model compatibility contract mismatch")
    if (
        manifest["input_classification"] != "OBSERVED"
        or manifest["target"] != "next-day vessel_calls"
    ):
        raise ValueError("Invalid production training target or classification")
    for name in ("activity.json", "features.csv"):
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != manifest["files"][name]:
            raise ValueError(f"Feature asset checksum mismatch: {name}")
    rows = json.loads((folder / "activity.json").read_text(encoding="utf-8"))
    if len(rows) != manifest["records"] or any(r["classification"] != "OBSERVED" for r in rows):
        raise ValueError("Invalid feature asset record count or classification")
    for row in rows:
        Activity.model_validate(row)
    return rows, manifest


def promotion_check(report, policy):
    reasons = []
    if report.get("status") != "VALIDATED_TEMPORAL_HOLDOUT":
        return {"eligible": False, "reasons": ["No validated temporal holdout"]}
    if (
        report["metrics"]["mae"]
        > report["metrics"]["persistence_mae"] * policy["max_mae_ratio_to_persistence"]
    ):
        reasons.append("Model does not meet baseline-relative MAE gate")
    coverage = report["calibration"]["empirical_holdout_coverage"]
    if not policy["min_interval_coverage"] <= coverage <= policy["max_interval_coverage"]:
        reasons.append("Interval coverage outside promotion policy")
    if report["feature_version"] != FEATURE_VERSION:
        reasons.append("Feature version mismatch")
    return {"eligible": not reasons, "reasons": reasons, "policy": policy}
