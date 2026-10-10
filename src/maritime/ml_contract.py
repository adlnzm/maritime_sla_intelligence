"""Content-verified boundary between Fabric Gold and Azure ML jobs."""

import hashlib
import json
from pathlib import Path

from maritime.governance import code_identity, fingerprint
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
        "code": code_identity(),
        "source_lineage": sorted({r["lineage_id"] for r in clean}),
        "date_range": [min(r["date"] for r in clean), max(r["date"] for r in clean)],
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
    if manifest.get("contract_version") != "1" or not manifest.get("fabric_run_id"):
        raise ValueError("Unknown feature contract or missing run lineage")
    keys = [(r["port_id"], r["date"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate feature entity/date")
    if features(rows).to_csv(index=False).encode() != (folder / "features.csv").read_bytes():
        raise ValueError("Feature computation skew detected")
    return rows, manifest


def prediction_manifest(rows, activity, run_id, approved_model_id=None, job_id=None):
    return {
        "contract_version": "1.0",
        "fabric_run_id": run_id,
        "feature_version": FEATURE_VERSION,
        "prediction_sha256": fingerprint(rows),
        "record_count": len(rows),
        "input_sha256": fingerprint(activity),
        "approved_model_id": approved_model_id,
        "azure_ml_job_id": job_id,
        "approval_status": "REGISTRY_APPROVED"
        if approved_model_id and job_id
        else "LOCAL_UNAPPROVED",
    }


def validate_predictions(rows, manifest, activity, run_id):
    import math
    from datetime import date, datetime, timedelta

    if (
        manifest.get("contract_version") != "1.0"
        or manifest.get("fabric_run_id") != run_id
        or manifest.get("feature_version") != FEATURE_VERSION
    ):
        raise ValueError("Prediction manifest contract/run mismatch")
    if (
        manifest.get("approval_status") != "REGISTRY_APPROVED"
        or not manifest.get("approved_model_id")
        or not manifest.get("azure_ml_job_id")
    ):
        raise ValueError("Unapproved model or missing Azure ML execution lineage")
    if (
        manifest.get("record_count") != len(rows)
        or manifest.get("prediction_sha256") != fingerprint(rows)
        or manifest.get("input_sha256") != fingerprint(activity)
    ):
        raise ValueError("Prediction checksum or input snapshot mismatch")
    latest = {}
    for r in activity:
        latest[r["port_id"]] = max(latest.get(r["port_id"], r["date"]), r["date"])
    expected = {
        (p, (date.fromisoformat(d) + timedelta(days=1)).isoformat()) for p, d in latest.items()
    }
    keys = []
    versions = set()
    for r in rows:
        if (
            r.get("classification") != "PREDICTED"
            or r.get("fabric_run_id") != run_id
            or r.get("feature_version") != FEATURE_VERSION
            or not r.get("model_version")
            or not r.get("lineage_id")
        ):
            raise ValueError("Prediction row schema/classification/lineage mismatch")
        if datetime.fromisoformat(r["generated_at"]).tzinfo is None:
            raise ValueError("Prediction timestamp must be timezone aware")
        values = [r[k] for k in ("lower", "vessel_calls", "upper")]
        if (
            not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in values
            )
            or not 0 <= values[0] <= values[1] <= values[2]
        ):
            raise ValueError("Invalid prediction interval")
        keys.append((r["port_id"], r["date"]))
        versions.add(r["model_version"])
    if len(keys) != len(set(keys)) or set(keys) != expected or len(versions) != 1:
        raise ValueError("Prediction completeness/uniqueness/model-version mismatch")
    return {"status": "PASS", "expected_rows": len(expected), "received_rows": len(rows)}


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
