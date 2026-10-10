"""Next-day port-call forecasting only; never trained on scenario breach labels."""

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from maritime.models import stable_id

FEATURES = ["lag1", "lag7", "mean7", "std7", "day_of_week"]
FEATURE_VERSION = "portcalls-lags-v1"


def features(activity):
    frames = []
    for port_id, group in pd.DataFrame(activity).groupby("port_id"):
        group = group.copy()
        group.index = pd.to_datetime(group["date"])
        # Missing days remain missing; no accidental seven-record/seven-day confusion.
        y = group["vessel_calls"].astype(float).sort_index().asfreq("D")
        frame = pd.DataFrame(
            {
                "target": y,
                "lag1": y.shift(1),
                "lag7": y.shift(7),
                "mean7": y.shift(1).rolling(7).mean(),
                "std7": y.shift(1).rolling(7).std(ddof=0),
            }
        )
        frame["day_of_week"] = frame.index.dayofweek
        frame["port_id"] = port_id
        frame["date"] = frame.index
        frames.append(frame.dropna().reset_index(drop=True))
    return pd.concat(frames).sort_values(["date", "port_id"]).reset_index(drop=True)


def predict(model, frame):
    if model is None:
        return frame["lag1"].to_numpy()
    return np.maximum(0, model.predict(frame[FEATURES]))


def candidates():
    return {
        "persistence": None,
        **{
            f"ridge_{alpha}": make_pipeline(
                SimpleImputer(), VarianceThreshold(), StandardScaler(), Ridge(alpha=alpha)
            )
            for alpha in (1, 10)
        },
        **{
            f"forest_{depth}": RandomForestRegressor(
                n_estimators=80, max_depth=depth, min_samples_leaf=5, random_state=1729, n_jobs=1
            )
            for depth in (4, 8)
        },
    }


def experiment(activity, output_dir, minimum_days=120):
    started = time.perf_counter()
    observed = [r for r in activity if r["classification"] == "OBSERVED"]
    deferred = {
        "status": "DEFERRED — INSUFFICIENT VALIDATED HISTORY",
        "training_records": 0,
        "validation_records": 0,
        "target": "next-day vessel_calls",
        "metrics": None,
    }
    if not observed:
        return deferred, []
    frame = features(observed)
    days = sorted(frame["date"].unique())
    if len(days) < minimum_days or len(frame) < 300:
        return {**deferred, "available_days": len(days), "available_records": len(frame)}, []
    # Selection, calibration and final holdout are disjoint calendar periods across all ports.
    train_end, calibration_end = int(len(days) * 0.7), int(len(days) * 0.85)
    selection = frame[frame.date < days[train_end]]
    calibration = frame[(frame.date >= days[train_end]) & (frame.date < days[calibration_end])]
    test = frame[frame.date >= days[calibration_end]]
    pool = candidates()
    comparisons = []
    for name, model in pool.items():
        fold_scores = []
        folds = []
        for fraction in (0.5, 0.65, 0.8):
            split = int(train_end * fraction)
            stop = min(train_end, split + max(7, train_end // 8))
            train = selection[selection.date < days[split]]
            val = selection[(selection.date >= days[split]) & (selection.date < days[stop])]
            if model is not None:
                model.fit(train[FEATURES], train.target)
            score = float(mean_absolute_error(val.target, predict(model, val)))
            fold_scores.append(score)
            folds.append(
                {
                    "train_end": str(train.date.max().date()),
                    "validation_start": str(val.date.min().date()),
                    "validation_end": str(val.date.max().date()),
                    "mae": score,
                }
            )
        comparisons.append({"name": name, "mae": float(np.mean(fold_scores)), "folds": folds})
    winner = min(comparisons, key=lambda c: (c["mae"], c["name"]))
    model = pool[winner["name"]]
    if model is not None:
        model.fit(selection[FEATURES], selection.target)
    residual = np.abs(calibration.target - predict(model, calibration))
    q = min(1, np.ceil((len(residual) + 1) * 0.9) / len(residual))
    radius = float(np.quantile(residual, q, method="higher"))
    forecast = predict(model, test)
    mae = float(mean_absolute_error(test.target, forecast))
    coverage = float(
        np.mean(
            (test.target >= np.maximum(0, forecast - radius)) & (test.target <= forecast + radius)
        )
    )
    drift = {
        f: float(abs(test[f].mean() - selection[f].mean()) / max(selection[f].std(ddof=0), 1e-6))
        for f in FEATURES
    }
    dataset_version = stable_id(
        [(r["port_id"], r["date"], r["vessel_calls"], r["lineage_id"]) for r in observed]
    )
    version = stable_id(dataset_version, FEATURE_VERSION, winner["name"])
    report = {
        "status": "VALIDATED_TEMPORAL_HOLDOUT",
        "target": "next-day vessel_calls",
        "training_records": len(selection),
        "calibration_records": len(calibration),
        "validation_records": len(test),
        "model": winner["name"],
        "model_version": version,
        "feature_version": FEATURE_VERSION,
        "features": FEATURES,
        "dataset_version": dataset_version,
        "training_start": str(selection.date.min().date()),
        "training_end": str(selection.date.max().date()),
        "calibration_start": str(calibration.date.min().date()),
        "calibration_end": str(calibration.date.max().date()),
        "validation_start": str(test.date.min().date()),
        "validation_end": str(test.date.max().date()),
        "metrics": {
            "mae": mae,
            "rmse": float(np.sqrt(mean_squared_error(test.target, forecast))),
            "persistence_mae": float(mean_absolute_error(test.target, test.lag1)),
        },
        "calibration": {
            "method": "split conformal absolute residual",
            "nominal_coverage": 0.9,
            "empirical_holdout_coverage": coverage,
            "radius": radius,
            "caveat": "Temporal dependence invalidates exchangeability guarantees",
        },
        "drift": {"standardized_mean_shift": drift, "alert": any(v > 2 for v in drift.values())},
        "comparisons": comparisons,
        "selection_rationale": "Lowest mean expanding-window MAE before calibration and untouched holdout",
        "hyperparameters": model.get_params(deep=False)
        if isinstance(model, RandomForestRegressor)
        else {"candidate": winner["name"]},
        "error_analysis": {
            str(p): float(
                np.mean(np.abs(test.loc[idx, "target"] - forecast[test.index.get_indexer(idx)]))
            )
            for p, idx in test.groupby("port_id").groups.items()
        },
        "duration_seconds": time.perf_counter() - started,
        "sla_model_status": "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA",
    }
    folder = Path(output_dir) / version
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "radius": radius, "features": FEATURES, "version": version},
        folder / "model.joblib",
    )
    (folder / "registry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    predictions = []
    for port_id, group in pd.DataFrame(observed).groupby("port_id"):
        group = group.sort_values("date")
        y = group["vessel_calls"].astype(float).to_numpy()
        target_day = pd.Timestamp(group.iloc[-1]["date"]) + pd.Timedelta(days=1)
        last_dates = pd.to_datetime(group.tail(7)["date"])
        if len(y) < 7 or (last_dates.iloc[-1] - last_dates.iloc[0]).days != 6:
            continue
        feature = pd.DataFrame(
            [[y[-1], y[-7], y[-7:].mean(), y[-7:].std(), target_day.dayofweek]], columns=FEATURES
        )
        value = float(predict(model, feature)[0])
        predictions.append(
            {
                "port_id": port_id,
                "date": str(target_day.date()),
                "vessel_calls": value,
                "lower": max(0, value - radius),
                "upper": value + radius,
                "classification": "PREDICTED",
                "model_version": version,
                "lineage_id": dataset_version,
            }
        )
    return report, predictions
