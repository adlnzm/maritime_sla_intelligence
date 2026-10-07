import json
import logging
import time
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

from maritime import __version__
from maritime.intelligence import (
    congestion,
    geojson,
    latest_states,
    network_state,
    propagate,
    scenario_routes,
)
from maritime.ml import experiment
from maritime.models import stable_id, utcnow
from maritime.quality import validate
from maritime.scenarios import ACTIONS, evaluate, rank, shipments
from maritime.sources import Fetcher, ingest_optional, ingest_portwatch
from maritime.store import Store

logger = logging.getLogger(__name__)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False), encoding="utf-8")


def report_files(store, report):
    folder = store.root / "reports" / report["run_id"]
    write_json(folder / "report.json", report)
    sections = [
        f"# Maritime run {report['run_id']}",
        f"Status: {report['status']}",
        "Public port activity; synthetic shipments and counterfactuals. Activity deviation is not measured waiting time.",
    ]
    for key, value in report.items():
        sections.append(f"## {key}\n\n```json\n{json.dumps(value, indent=2, default=str)}\n```")
    (folder / "report.md").write_text("\n\n".join(sections), encoding="utf-8")


def field_lineage(products, run_id):
    dependencies = {
        "congestion": ["activity"],
        "congestion_history": ["activity"],
        "network": ["routes", "ports", "congestion"],
        "exposure": ["network", "congestion"],
        "scenarios": ["network"],
        "interventions": ["scenarios", "network", "congestion"],
        "sla_risk": ["interventions"],
        "decisions": ["interventions", "sla_risk"],
        "predictions": ["activity"],
        "early_warning": ["congestion", "exposure"],
        "disruptions": ["congestion"],
    }
    result = []
    for table, rows in products.items():
        for field in sorted({k for r in rows for k in r}):
            result.append(
                {
                    "lineage_id": stable_id(run_id, table, field),
                    "run_id": run_id,
                    "resulting_field": f"{table}.{field}",
                    "input_tables": dependencies.get(table, ["bronze"]),
                    "source_ids": sorted({r.get("source_id", "pipeline") for r in rows}),
                    "input_lineage_ids": sorted(
                        {str(r["lineage_id"]) for r in rows if "lineage_id" in r}
                    ),
                    "transformation": table,
                    "methodology_version": "v1",
                    "classification": "DERIVED",
                    "downstream_product": "API / reporting marts / GIS",
                }
            )
    return result


def run(
    root="data",
    config_path="configs/pipeline.json",
    registry_path="configs/sources.json",
    fixture=None,
    as_of=None,
    fetcher=None,
    run_id=None,
):
    config, registry = load_json(config_path), load_json(registry_path)
    store = Store(root)
    run_id = run_id or uuid.uuid4().hex
    report = {
        "run_id": run_id,
        "environment": "local",
        "version": __version__,
        "start_time": utcnow(),
        "status": "RUNNING",
        "stage_status": {},
        "source_status": [],
        "failures": [],
    }
    store.run(report)
    fetcher = fetcher or Fetcher(root)
    started = time.perf_counter()
    checkpoint = None
    try:
        if fixture:
            bundle = load_json(fixture)
            as_of = as_of or date.fromisoformat(bundle["as_of"])
            ports, activity = bundle["ports"], bundle["activity"]
            write_json(store.root / "bronze" / "replay" / (stable_id(bundle) + ".json"), bundle)
            report["source_status"] = bundle.get(
                "source_status", [{"source_id": "fixture", "status": "REPLAY"}]
            )
            report["execution_mode"] = "REPLAY"
            supplied_routes = bundle.get("routes")
        else:
            as_of = as_of or date.today()
            ports, activity, checkpoint = ingest_portwatch(fetcher, registry, config, store, as_of)
            report["execution_mode"] = "LIVE_PUBLIC_DATA"
            supplied_routes = None
        report["as_of"] = as_of.isoformat()
        report["stage_status"]["bronze"] = "PASS"
        optional = {}
        if not fixture:
            for source in registry["sources"]:
                if source["critical"]:
                    continue
                try:
                    rows = ingest_optional(fetcher, source, ports, as_of)
                    optional[source["source_id"]] = rows
                    report["source_status"].append(
                        {
                            "source_id": source["source_id"],
                            "status": "SUCCESS" if rows is not None else "NOT_CONFIGURED",
                            "record_count": len(rows or []),
                        }
                    )
                except (ValueError, KeyError, RuntimeError, OSError) as exc:
                    report["source_status"].append(
                        {
                            "source_id": source["source_id"],
                            "status": "FAILED_OPTIONAL",
                            "error": str(exc),
                        }
                    )
            supplied_routes = optional.get("routes")
        routes = (
            supplied_routes
            if supplied_routes is not None
            else scenario_routes(ports, as_of, config["scenario_assumptions"])
        )
        clean, dq = validate(
            ports, activity, routes, as_of, config["freshness_days"], optional.get("unlocode")
        )
        report["data_quality"] = dq
        store.write(run_id, "data_quality", [dq])
        if dq["status"] != "PASS":
            raise ValueError(f"Critical DQ failed: {len(dq['errors'])} checks; inspect run report")
        ports, activity, routes = clean["ports"], clean["activity"], clean["routes"]
        if checkpoint:
            store.set_metadata(*checkpoint)
        for name, rows in clean.items():
            write_json(store.root / "silver" / run_id / (name + ".json"), rows)
        report["stage_status"]["silver"] = "PASS"
        history = congestion(activity, config["baseline_days"], config["min_history"])
        states = latest_states(history)
        graph, edges = network_state(ports, routes, states, as_of)
        exposure = propagate(
            graph, states, config["propagation_horizon_hours"], config["propagation_decay"]
        )
        generated = shipments(graph, config["shipments"], config["seed"], as_of)
        interventions, decisions = [], []
        for shipment in generated:
            outcomes = evaluate(
                graph, shipment, config["scenario_assumptions"], config["seed"], config["draws"]
            )
            interventions.extend(outcomes)
            decisions.append(rank(outcomes))
        baseline = [o for o in interventions if o["action"] == "NO_ACTION"]
        ml_report, predictions = experiment(activity, store.root / "models")
        disruptions = [
            {**s, "signal_type": "ACTIVITY_DEVIATION_PROXY", "confirmed_disruption": False}
            for s in states
            if s["category"] in {"HIGH", "CRITICAL"}
        ]
        products = {
            "ports": ports,
            "activity": activity,
            "routes": routes,
            "congestion_history": history,
            "congestion": states,
            "network": edges,
            "exposure": exposure,
            "scenarios": generated,
            "interventions": interventions,
            "sla_risk": baseline,
            "decisions": decisions,
            "predictions": predictions,
            "disruptions": disruptions,
            "early_warning": [
                {
                    **s,
                    "warning_id": stable_id(s["state_id"], "warning"),
                    "downstream_ports": len(
                        {e["port_id"] for e in exposure if e["origin"] == s["port_id"]}
                    ),
                }
                for s in disruptions
            ],
            "sources": registry["sources"],
            "data_quality": [dq],
        }
        for name, rows in optional.items():
            if rows is not None:
                products["reference_" + name] = rows
        products["lineage"] = field_lineage(products, run_id)
        # Dimensional marts are materialized with explicit fact keys and UTC dates.
        products["dim_location"] = [
            {
                k: p[k]
                for k in (
                    "port_id",
                    "country",
                    "latitude",
                    "longitude",
                    "unlocode",
                    "classification",
                    "lineage_id",
                )
            }
            for p in ports
        ]
        products["dim_time"] = [
            {
                "date": d,
                "year": int(d[:4]),
                "month": int(d[5:7]),
                "classification": "DERIVED",
                "lineage_id": stable_id(d),
            }
            for d in sorted({r["date"] for r in activity})
        ]
        products["dim_intervention"] = [
            {
                "action": a,
                "classification": "SIMULATED",
                "lineage_id": stable_id(a, config["scenario_assumptions"]),
            }
            for a in ACTIONS
        ]
        for name, rows in products.items():
            for row in rows:
                row.setdefault("run_id", run_id)
            store.write(run_id, name, rows)
            write_json(store.root / "gold" / run_id / (name + ".json"), rows)
        write_json(
            store.root / "gold" / run_id / "operational.geojson", geojson(ports, states, edges)
        )
        report["stage_status"].update(
            {"gold": "PASS", "intelligence": "PASS", "scenario": "PASS", "decision": "PASS"}
        )
        report["data"] = {
            "records_ingested": len(ports) + len(activity),
            "records_rejected": dq["records_rejected"],
            "dq_score": dq["overall_dq_score"],
            "freshness": dq["freshness_status"],
        }
        report["congestion"] = {
            "ports_evaluated": len(states),
            "categories": dict(Counter(s["category"] for s in states)),
            "persistence_days": {s["port_id"]: s["persistence_days"] for s in states},
        }
        report["network"] = {
            "nodes": len(graph),
            "edges": len(edges),
            "affected_nodes": len({e["port_id"] for e in exposure}),
            "affected_edges": sum(e["stress_score"] >= 2 / 3 for e in edges),
            "propagation_depth": max((e["depth"] for e in exposure), default=0),
            "propagation_results": len(exposure),
            "topology": "PUBLIC_REFERENCE"
            if supplied_routes is not None
            else "SIMULATED_CONNECTIVITY",
            "alternative_routes": sum(
                o["feasible"] for o in interventions if o["action"] == "REROUTE"
            ),
        }
        report["scenarios"] = {
            "shipments": len(generated),
            "executions": len(interventions),
            "success": len(interventions),
            "failures": 0,
            "infeasible": sum(not o["feasible"] for o in interventions),
            "seed": config["seed"],
        }
        report["sla"] = {
            "at_risk_shipments": sum(o["breach_probability"] >= 0.5 for o in baseline),
            "expected_delay_hours": sum(o["expected_delay_hours"] for o in baseline)
            / len(baseline),
            "expected_breaches": sum(o["breach_probability"] for o in baseline),
            "expected_loss": sum(o["expected_loss"] for o in baseline),
            "classification": "SIMULATED",
        }
        report["counterfactual"] = {
            a: {
                "evaluated": sum(o["action"] == a for o in interventions),
                "feasible": sum(o["action"] == a and o["feasible"] for o in interventions),
            }
            for a in ACTIONS
        }
        report["decision"] = {
            "recommendations": dict(Counter(d["recommended_action"] for d in decisions)),
            "count": len(decisions),
            "expected_benefit": sum(d["expected_benefit"] for d in decisions),
            "expected_delay_avoided": sum(d["expected_delay_avoided"] for d in decisions),
            "decision_confidence": "NOT_CALIBRATED",
            "operator_overrides": len(
                [a for a in store.audits("review") if a["status"] == "override"]
            ),
        }
        report["ml"] = ml_report
        report["genai"] = {
            "status": "NOT_CONFIGURED_OR_EXECUTED",
            "signals_processed": 0,
            "verified": 0,
            "rejected": 0,
            "grounding_rate": None,
        }
        report["gates"] = {
            "data_foundation": "PASS_EXECUTION",
            "data_platform": "PASS_EXECUTION",
            "congestion": "PASS_EXECUTION",
            "network": "PASS_EXECUTION",
            "scenario": "PASS_EXECUTION",
            "counterfactual": "PASS_EXECUTION",
            "sla": "PASS_EXECUTION",
            "ml": ml_report["status"],
            "decision": "PASS_EXECUTION_HUMAN_REVIEW_PENDING",
            "api_bi": "MARTS_EXPORTED_API_TEST_REQUIRED",
            "reliability": "TEST_EVIDENCE_REQUIRED",
            "e2e": "PASS_LOCAL_PIPELINE",
            "fabric": "ENVIRONMENT_DEPENDENT_NOT_VALIDATED",
        }
        report["status"] = "SUCCESS"
        store.set_metadata("published_run", run_id)
    except Exception as exc:
        report["status"] = "FAILED"
        report["failures"].append({"type": type(exc).__name__, "message": str(exc)})
        logger.exception("pipeline_failed", extra={"run_id": run_id})
        raise
    finally:
        report["source_status"].extend(fetcher.events)
        report["reliability"] = {
            "failures": len(report["failures"]),
            "retries": fetcher.retries,
            "timeouts": fetcher.timeouts,
            "recoveries": sum(
                e.get("retries", 0) > 0 and e["status"] == "SUCCESS" for e in fetcher.events
            ),
        }
        report["end_time"] = utcnow()
        report["duration_seconds"] = time.perf_counter() - started
        store.run(report)
        report_files(store, report)
    return report
