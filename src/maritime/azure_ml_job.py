"""Azure ML command-job entry points reuse the existing temporal experiment."""

import argparse
import shutil
import uuid
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from maritime.ml import FEATURE_VERSION, FEATURES, experiment, features, predict
from maritime.ml_contract import load_features, promotion_check
from maritime.models import utcnow
from maritime.pipeline import load_json, write_json


def train(data, output, policy, tracking=True):
    activity, manifest = load_features(data)
    output = Path(output)
    report, _ = experiment(activity, output / "experiments")
    if report["status"] != "VALIDATED_TEMPORAL_HOLDOUT":
        write_json(output / "evaluation.json", report)
        raise ValueError("Azure ML training deferred: insufficient validated observed history")
    folder = output / "experiments" / report["model_version"]
    artifact = joblib.load(folder / "model.joblib")
    # Each registered training run has distinct lineage, even for identical input bytes.
    report["model_version"] += "-" + uuid.uuid4().hex[:12]
    artifact["version"] = report["model_version"]
    artifact["feature_version"] = FEATURE_VERSION
    import sklearn

    artifact["runtime_versions"] = {
        "sklearn": sklearn.__version__,
        "numpy": np.__version__,
        "joblib": joblib.__version__,
    }
    artifact["dataset_manifest"] = manifest
    training = features(activity)
    training = training[training.date <= pd.Timestamp(report["training_end"])]
    artifact["reference_distribution"] = {
        f: {"mean": float(training[f].mean()), "std": float(training[f].std(ddof=0))}
        for f in FEATURES
    }
    (output / "model").mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output / "model" / "model.joblib")
    report["azure_ml_job_id"] = __import__("os").getenv("AZUREML_RUN_ID")
    report["fabric_manifest"] = manifest
    report["promotion"] = promotion_check(report, policy)
    report["sla_model_status"] = "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA"
    write_json(output / "evaluation.json", report)
    shutil.copy2(output / "evaluation.json", output / "model" / "evaluation.json")
    if tracking:
        import mlflow

        with mlflow.start_run():
            mlflow.log_params(
                {
                    "feature_version": FEATURE_VERSION,
                    "model": report["model"],
                    "dataset_version": report["dataset_version"],
                    "fabric_run_id": manifest["fabric_run_id"],
                }
            )
            mlflow.log_metrics(report["metrics"])
            mlflow.log_metric(
                "interval_coverage", report["calibration"]["empirical_holdout_coverage"]
            )
            mlflow.log_artifact(str(output / "evaluation.json"))
            mlflow.log_artifacts(str(output / "model"), artifact_path="model")
    return report


def batch(data, model_dir, output):
    activity, manifest = load_features(data)
    artifact = joblib.load(Path(model_dir) / "model.joblib")
    import sklearn

    runtime = {
        "sklearn": sklearn.__version__,
        "numpy": np.__version__,
        "joblib": joblib.__version__,
    }
    if artifact.get("runtime_versions") != runtime:
        raise ValueError("Training/inference runtime compatibility mismatch")
    if artifact.get("feature_version") != FEATURE_VERSION or artifact["features"] != FEATURES:
        raise ValueError("Model/feature schema mismatch")
    rows = []
    for port_id, group in pd.DataFrame(activity).groupby("port_id"):
        group = group.sort_values("date")
        days = pd.to_datetime(group.date)
        if len(group) < 7 or (days.iloc[-1] - days.iloc[-7]).days != 6:
            raise ValueError(f"Missing inference history: {port_id}")
        y = group.vessel_calls.to_numpy(dtype=float)
        target = days.iloc[-1] + pd.Timedelta(days=1)
        frame = pd.DataFrame(
            [[y[-1], y[-7], y[-7:].mean(), y[-7:].std(), target.dayofweek]], columns=FEATURES
        )
        value = float(predict(artifact["model"], frame)[0])
        rows.append(
            {
                "port_id": port_id,
                "date": str(target.date()),
                "vessel_calls": value,
                "lower": max(0, value - artifact["radius"]),
                "upper": value + artifact["radius"],
                "classification": "PREDICTED",
                "model_version": artifact["version"],
                "feature_version": FEATURE_VERSION,
                "fabric_run_id": manifest["fabric_run_id"],
                "lineage_id": manifest["files"]["activity.json"],
                "generated_at": utcnow(),
            }
        )
    write_json(Path(output) / "predictions.json", rows)
    frame = features(activity)
    shifts = {
        f: float(
            abs(frame[f].mean() - artifact["reference_distribution"][f]["mean"])
            / max(artifact["reference_distribution"][f]["std"], 1e-6)
        )
        for f in FEATURES
    }
    write_json(
        Path(output) / "monitoring.json",
        {
            "status": "DRIFT_ALERT" if any(v > 2 for v in shifts.values()) else "NO_DRIFT_ALERT",
            "mean_shifts": shifts,
            "prediction_count": len(rows),
            "model_version": artifact["version"],
            "realized_error_status": "AWAITING_SUBSEQUENT_OBSERVATIONS",
        },
    )
    return rows


def monitor(predictions_path, data, output):
    activity, _ = load_features(data)
    actual = {(r["port_id"], r["date"]): r["vessel_calls"] for r in activity}
    predictions = load_json(predictions_path)
    matched = [
        (p, actual[(p["port_id"], p["date"])])
        for p in predictions
        if (p["port_id"], p["date"]) in actual
    ]
    result = {
        "matched_records": len(matched),
        "unmatched_records": len(predictions) - len(matched),
        "status": "MEASURED" if matched else "AWAITING_SUBSEQUENT_OBSERVATIONS",
    }
    if matched:
        result["mae"] = float(np.mean([abs(p["vessel_calls"] - y) for p, y in matched]))
        result["coverage"] = float(np.mean([p["lower"] <= y <= p["upper"] for p, y in matched]))
    write_json(Path(output) / "outcome-monitoring.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["train", "batch", "monitor"])
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model")
    parser.add_argument("--predictions")
    parser.add_argument("--policy", default="configs/azure.json")
    args = parser.parse_args()
    if args.mode == "train":
        train(args.data, args.output, load_json(args.policy)["promotion"])
    elif args.mode == "batch":
        batch(args.data, args.model, args.output)
    else:
        monitor(args.predictions, args.data, args.output)


if __name__ == "__main__":
    main()
