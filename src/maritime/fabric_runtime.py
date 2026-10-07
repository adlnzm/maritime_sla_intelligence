"""Fabric adapters: Delta medallion tables and run-isolated core execution.

PySpark imports are intentionally lazy so local business logic remains portable.
"""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from maritime.intelligence import scenario_routes
from maritime.pipeline import load_json, run, write_json
from maritime.quality import validate
from maritime.sources import Fetcher, ingest_portwatch
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
        fetcher = Fetcher(root)
        try:
            ports, activity, _ = ingest_portwatch(
                fetcher, registry, config, store, date.fromisoformat(as_of)
            )
            bundle = {
                "ports": ports,
                "activity": activity,
                "as_of": as_of,
                "source_status": fetcher.events,
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
    routes = scenario_routes(
        bundle["ports"], date.fromisoformat(bundle["as_of"]), config["scenario_assumptions"]
    )
    clean, dq = validate(
        bundle["ports"],
        bundle["activity"],
        routes,
        date.fromisoformat(bundle["as_of"]),
        config["freshness_days"],
    )
    write_json(Path(root) / "runs" / run_id / "dq.json", dq)
    if dq["status"] != "PASS":
        raise ValueError("Silver contract and freshness validation failed")
    for name, rows in clean.items():
        delta_write(spark, rows, "silver_" + name, run_id)
    write_json(
        Path(root) / "runs" / run_id / "silver.json",
        {**clean, "as_of": bundle["as_of"], "source_status": bundle["source_status"]},
    )


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
            temp, config_path, registry_path, root / "runs" / run_id / "silver.json", run_id=run_id
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
            root / "runs" / run_id / "fabric-report.json", {**report, "delta_counts": counts}
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
        [{"status": "SUCCESS", "report_path": str(root / "runs" / run_id / "fabric-report.json")}],
        "maritime_published_runs",
        run_id,
    )
    return report
