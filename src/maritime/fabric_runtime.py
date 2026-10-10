"""Fabric adapters: Delta medallion tables and run-isolated core execution.

PySpark imports are intentionally lazy so local business logic remains portable.
"""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from maritime.intelligence import scenario_routes
from maritime.models import utcnow
from maritime.pipeline import load_json, run, write_json
from maritime.quality import validate
from maritime.sources import Fetcher, ingest_optional, ingest_portwatch
from maritime.store import Store


def delta_write(spark, rows, table, run_id):
    from pyspark.sql import functions as F

    if not rows:
        return 0
    # JSON reader infers nested structures and handles null-only columns consistently.
    serialized = spark.sparkContext.parallelize([json.dumps(r, default=str) for r in rows])
    frame = spark.read.json(serialized).withColumn("run_id", F.lit(run_id))
    if spark.catalog.tableExists(table):
        frame.write.format("delta").mode("overwrite").option(
            "replaceWhere", f"run_id = '{run_id}'"
        ).option("mergeSchema", "true").saveAsTable(table)
    else:
        frame.write.format("delta").partitionBy("run_id").mode("overwrite").saveAsTable(table)
    return frame.count()


def bronze(spark, root, run_id, config_path, registry_path, as_of):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    config, registry = load_json(config_path), load_json(registry_path)
    # SQLite stays on the driver disk, never on the OneLake FUSE mount.
    with tempfile.TemporaryDirectory() as temp:
        store = Store(temp)
        checkpoint_path = root / "activity-checkpoint.json"
        if checkpoint_path.exists():
            key, value = load_json(checkpoint_path)
            store.set_metadata(key, value)
        fetcher = Fetcher(root)
        try:
            ports, activity, checkpoint = ingest_portwatch(
                fetcher, registry, config, store, date.fromisoformat(as_of)
            )
            optional, statuses = {}, []
            for source in registry["sources"]:
                if source["critical"]:
                    continue
                try:
                    rows = ingest_optional(fetcher, source, ports, date.fromisoformat(as_of))
                    optional[source["source_id"]] = rows
                    statuses.append(
                        {
                            "source_id": source["source_id"],
                            "status": "SUCCESS" if rows is not None else "NOT_CONFIGURED",
                            "record_count": len(rows or []),
                        }
                    )
                except (ValueError, KeyError, RuntimeError, OSError) as exc:
                    statuses.append(
                        {
                            "source_id": source["source_id"],
                            "status": "FAILED_OPTIONAL",
                            "error": str(exc),
                        }
                    )
            bundle = {
                "ports": ports,
                "activity": activity,
                "as_of": as_of,
                "source_status": statuses + fetcher.events,
                "optional": optional,
                "checkpoint": checkpoint,
            }
            write_json(root / "runs" / run_id / "bronze.json", bundle)
            delta_write(spark, ports, "bronze_ports", run_id)
            delta_write(spark, activity, "bronze_activity", run_id)
        finally:
            write_json(root / "runs" / run_id / "ingestion.json", fetcher.events)


def silver(spark, root, run_id, config_path):
    from pyspark.sql import functions as F

    config = load_json(config_path)
    bundle = load_json(Path(root) / "runs" / run_id / "bronze.json")
    # Typed distributed transformations and constraint checks operate in Spark.
    activity = (
        spark.table("bronze_activity")
        .filter(F.col("run_id") == run_id)
        .withColumn("vessel_calls", F.col("vessel_calls").cast("double"))
        .withColumn("date", F.to_date("date"))
    )
    duplicates = activity.groupBy("port_id", "date").count().filter("count > 1").count()
    invalid = activity.filter(
        F.col("date").isNull() | F.col("vessel_calls").isNull() | (F.col("vessel_calls") < 0)
    ).count()
    if duplicates or invalid:
        raise ValueError(f"Spark silver DQ failed: duplicates={duplicates}, invalid={invalid}")
    routes = bundle["optional"].get("routes")
    if routes is None:
        routes = scenario_routes(
            bundle["ports"], date.fromisoformat(bundle["as_of"]), config["scenario_assumptions"]
        )
    clean, dq = validate(
        bundle["ports"],
        bundle["activity"],
        routes,
        date.fromisoformat(bundle["as_of"]),
        config["freshness_days"],
        bundle["optional"].get("unlocode"),
    )
    write_json(Path(root) / "runs" / run_id / "dq.json", dq)
    if dq["status"] != "PASS":
        raise ValueError("Silver contract and freshness validation failed")
    for name, rows in clean.items():
        delta_write(spark, rows, "silver_" + name, run_id)
    write_json(
        Path(root) / "runs" / run_id / "silver.json",
        {
            **clean,
            "as_of": bundle["as_of"],
            "source_status": bundle["source_status"],
            "optional": bundle["optional"],
        },
    )
    write_json(Path(root) / "activity-checkpoint.json", bundle["checkpoint"])


def gold(spark, root, run_id, config_path, registry_path):
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    root = Path(root)
    # Distributed historical baseline available for warehouse-scale diagnostics.
    activity = spark.table("silver_activity").filter(F.col("run_id") == run_id)
    config = load_json(config_path)
    seconds = F.to_timestamp("date").cast("long")
    window = (
        Window.partitionBy("port_id")
        .orderBy(seconds)
        .rangeBetween(-config["baseline_days"] * 86400, -1)
    )
    rolling = activity.withColumn(
        "history_records", F.count("vessel_calls").over(window)
    ).withColumn(
        "baseline",
        F.when(
            F.col("history_records") >= config["min_history"], F.avg("vessel_calls").over(window)
        ),
    )
    rolling.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        "gold_activity_baseline_latest"
    )
    # Explicit bounded graph workload: business engines run on the driver.
    if activity.count() > 1000000:
        raise ValueError("Driver intelligence limit exceeded; partition configured port scope")
    with tempfile.TemporaryDirectory() as temp:
        report = run(
            temp,
            config_path,
            registry_path,
            root / "runs" / run_id / "silver.json",
            run_id=run_id,
            ml_backend="azure_ml",
        )
        report["environment"] = "fabric"
        report["gates"]["fabric"] = "EXECUTED_AWAITING_ACCEPTANCE_NOTEBOOK"
        folder = Path(temp) / "gold" / run_id
        counts = {}
        for file in folder.glob("*.json"):
            rows = load_json(file)
            table = (
                "dim_" if file.stem in {"ports", "routes", "sources", "scenarios"} else "fact_"
            ) + file.stem
            if file.stem.startswith("dim_"):
                table = file.stem
            counts[table] = delta_write(spark, rows, table, run_id)
        destination = root / "runs" / run_id / "evidence"
        shutil.copytree(
            Path(temp),
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.db", "*.db-wal", "*.db-shm"),
        )
        write_json(
            root / "runs" / run_id / "fabric-report.json",
            {
                **report,
                "delta_counts": counts,
                "serving_products": sorted(p.stem for p in folder.glob("*.json")),
            },
        )


def acceptance(spark, root, run_id):
    from pyspark.sql import functions as F

    root = Path(root)
    report = load_json(root / "runs" / run_id / "fabric-report.json")
    for table, expected in report["delta_counts"].items():
        if expected and spark.table(table).filter(F.col("run_id") == run_id).count() != expected:
            raise ValueError(f"Fabric persistence verification failed: {table}")
    if report["status"] != "SUCCESS" or report["data_quality"]["status"] != "PASS":
        raise ValueError("Fabric run or DQ failed")
    report["gates"]["fabric"] = "PASS_EXECUTED_DELTA_READBACK"
    write_json(root / "runs" / run_id / "fabric-report.json", report)
    delta_write(
        spark,
        [
            {
                "status": "SUCCESS",
                "published_at": utcnow(),
                "report_path": str(root / "runs" / run_id / "fabric-report.json"),
            }
        ],
        "maritime_published_runs",
        run_id,
    )
    return report


def import_predictions(spark, root, run_id):
    from maritime.ml import FEATURE_VERSION

    rows = load_json(Path(root) / "runs" / run_id / "azure-ml-predictions.json")
    if not rows:
        raise ValueError("No Azure ML predictions supplied")
    for row in rows:
        if (
            row["classification"] != "PREDICTED"
            or row["fabric_run_id"] != run_id
            or row["feature_version"] != FEATURE_VERSION
        ):
            raise ValueError("Prediction lineage or feature contract mismatch")
        if not row["model_version"] or not 0 <= row["lower"] <= row["vessel_calls"] <= row["upper"]:
            raise ValueError("Invalid prediction model or interval")
    count = delta_write(spark, rows, "fact_predictions", run_id)
    from pyspark.sql import functions as F

    if spark.table("fact_predictions").filter(F.col("run_id") == run_id).count() != count:
        raise ValueError("Prediction Delta readback failed")
    export_folder = Path(root) / "runs" / run_id / "evidence" / "gold" / run_id
    write_json(export_folder / "predictions.json", [{**row, "run_id": run_id} for row in rows])
    decisions = load_json(export_folder / "decisions.json")
    shipments = {r["shipment_id"]: r for r in load_json(export_folder / "scenarios.json")}
    by_port = {r["port_id"]: r for r in rows}
    for decision in decisions:
        shipment = shipments[decision["shipment_id"]]
        decision["forecast_evidence"] = [by_port[p] for p in shipment["route"] if p in by_port]
        decision["forecast_usage"] = "SUPPLEMENTAL_PORT_ACTIVITY_EVIDENCE_NOT_SLA_PROBABILITY"
    delta_write(spark, decisions, "fact_decisions", run_id)
    write_json(export_folder / "decisions.json", decisions)
    write_json(
        Path(root) / "runs" / run_id / "prediction-return.json",
        {"status": "IMPORTED_TO_FABRIC", "prediction_count": count, "run_id": run_id},
    )
    report_path = Path(root) / "runs" / run_id / "fabric-report.json"
    report = load_json(report_path)
    report["ml"].update(
        {
            "status": "AZURE_ML_PREDICTIONS_IMPORTED",
            "prediction_count": count,
            "model_versions": sorted({r["model_version"] for r in rows}),
        }
    )
    report["delta_counts"]["fact_predictions"] = count
    write_json(report_path, report)
    return count
