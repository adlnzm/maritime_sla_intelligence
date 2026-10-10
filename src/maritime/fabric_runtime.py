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


def fabric_gate(stage):
    """Stage receipts supplement Data Factory status; failed data gates stop dependencies."""
    import functools
    import inspect
    import uuid

    from maritime.governance import contract, fingerprint

    def decorate(function):
        @functools.wraps(function)
        def guarded(*args, **kwargs):
            parameters = inspect.signature(function).bind(*args, **kwargs).arguments
            folder = Path(parameters["root"]) / "runs" / parameters["run_id"] / "stage-evidence"
            folder.mkdir(parents=True, exist_ok=True)
            dependency = {
                "silver": "bronze",
                "gold": "silver",
                "acceptance": "gold",
                "import_predictions": "acceptance",
            }.get(stage)
            if dependency:
                previous = sorted(folder.glob(dependency + "-*-completed.json"))
                if not previous or load_json(previous[-1])["status"] not in {
                    "PASS",
                    "PASS_WITH_WARNINGS",
                }:
                    raise ValueError(f"Fabric dependency not approved: {dependency}")
            execution = utcnow().replace(":", "-") + "-" + uuid.uuid4().hex
            receipt = {
                "run_id": parameters["run_id"],
                "stage": stage,
                "execution_id": execution,
                "status": "NOT_EVALUATED",
                "start_time": utcnow(),
                "contract_fingerprint": fingerprint(contract()),
            }
            write_json(folder / f"{stage}-{execution}-started.json", receipt)
            try:
                result = function(*args, **kwargs)
                receipt["status"] = "PASS"
                return result
            except Exception as exc:
                receipt.update(
                    status="BLOCKED", failure_type=type(exc).__name__, failure_reason=str(exc)
                )
                raise
            finally:
                receipt["end_time"] = utcnow()
                write_json(folder / f"{stage}-{execution}-completed.json", receipt)

        return guarded

    return decorate


def delta_write(spark, rows, table, run_id):
    from pyspark.sql import functions as F

    if not rows:
        if (
            spark.catalog.tableExists(table)
            and spark.table(table).filter(F.col("run_id") == run_id).count()
        ):
            raise ValueError("Empty output conflicts with existing partition")
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
    readback = spark.table(table).filter(F.col("run_id") == run_id).select(*frame.columns)
    if frame.exceptAll(readback).count() or readback.exceptAll(frame).count():
        raise ValueError(f"Delta content readback failed: {table}")
    return readback.count()


@fabric_gate("bronze")
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


@fabric_gate("silver")
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


@fabric_gate("gold")
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


@fabric_gate("acceptance")
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


@fabric_gate("import_predictions")
def import_predictions(spark, root, run_id):
    from maritime.governance import fingerprint, verify_manifest
    from maritime.ml_contract import load_features, validate_predictions

    root = Path(root)
    rows = load_json(root / "runs" / run_id / "azure-ml-predictions.json")
    manifest = load_json(root / "runs" / run_id / "azure-ml-prediction-manifest.json")
    activity, _ = load_features(root / "runs" / run_id / "evidence" / "azure_features" / run_id)
    validate_predictions(rows, manifest, activity, run_id)
    original_report = load_json(root / "runs" / run_id / "fabric-report.json")
    for row in rows:
        row.update(
            contract_version="1.0",
            processed_at=utcnow(),
            configuration_fingerprint=original_report["release"]["configuration_fingerprint"],
            component_classifications=["OBSERVED"],
            input_fingerprints={"activity": fingerprint(activity)},
            degraded_sources=original_report.get("degraded_sources", []),
            execution_mode="FABRIC_AZURE_ML",
        )
    count = delta_write(spark, rows, "fact_predictions", run_id)
    from pyspark.sql import functions as F

    if spark.table("fact_predictions").filter(F.col("run_id") == run_id).count() != count:
        raise ValueError("Prediction Delta readback failed")
    returned = [
        r.asDict(recursive=True)
        for r in spark.table("fact_predictions").filter(F.col("run_id") == run_id).collect()
    ]
    expected = [{**r, "run_id": run_id} for r in rows]
    if fingerprint(sorted(returned, key=lambda r: r["port_id"])) != fingerprint(
        sorted(expected, key=lambda r: r["port_id"])
    ):
        raise ValueError("Prediction Delta content readback failed")
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
    products = {p.stem: load_json(p) for p in export_folder.glob("*.json")}
    # A new release identity preserves the parent release and the AML import evidence.
    report["release"]["parent_release_id"] = report["release"]["release_id"]
    report["release"]["release_id"] = fingerprint(
        [report["release"]["parent_release_id"], manifest]
    )
    report["release"]["prediction_return"] = manifest
    for name in ("predictions", "decisions"):
        report["release"]["datasets"][name] = {
            "rows": len(products[name]),
            "sha256": fingerprint(products[name]),
            "classifications": sorted({r["classification"] for r in products[name]}),
        }
    verify_manifest(products, report["release"])
    write_json(report_path, report)
    return count
