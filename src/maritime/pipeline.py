import json
import logging
import time
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from maritime import __version__
from maritime.governance import (
    Gates,
    GovernanceError,
    enrich,
    exclusive_run,
    fingerprint,
    release_manifest,
    verify_products,
)
from maritime.intelligence import (
    congestion,
    geojson,
    latest_states,
    network_state,
    propagate,
    scenario_routes,
)
from maritime.ml import experiment
from maritime.models import json_default, stable_id, utcnow
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
    path.write_text(
        json.dumps(value, indent=2, default=json_default, allow_nan=False), encoding="utf-8"
    )


def report_files(store, report):
    folder = store.root / "reports" / report["run_id"]
    write_json(folder / "report.json", report)
    sections = [
        f"# Maritime run {report['run_id']}",
        f"Status: {report['status']}",
        "Public port activity; synthetic shipments and counterfactuals. Activity deviation is not measured waiting time.",
    ]
    for key, value in report.items():
        sections.append(
            f"## {key}\n\n```json\n{json.dumps(value, indent=2, default=json_default)}\n```"
        )
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
                    "input_tables": ["predictions"]
                    if table == "decisions" and field == "forecast_evidence"
                    else dependencies.get(table, ["bronze"]),
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


def _run(
    root="data",
    config_path="configs/pipeline.json",
    registry_path="configs/sources.json",
    fixture=None,
    as_of=None,
    fetcher=None,
    run_id=None,
    ml_backend="local",
    request_fingerprint=None,
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
    report["request_fingerprint"] = request_fingerprint
    gates = Gates(store, report, config)
    store.run(report)
    fetcher = fetcher or Fetcher(root)
    started = time.perf_counter()
    checkpoint = None
    try:
        gates.start("acquisition")
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
            as_of = as_of or datetime.now(timezone.utc).date()
            ports, activity, checkpoint = ingest_portwatch(fetcher, registry, config, store, as_of)
            report["execution_mode"] = "LIVE_PUBLIC_DATA"
            supplied_routes = None
        report["as_of"] = as_of.isoformat()
        report["stage_status"]["bronze"] = "PASS"
        optional = bundle.get("optional", {}) if fixture else {}
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
        report["degraded_sources"] = sorted(
            {
                e["source_id"]
                for e in report["source_status"]
                if e["status"] in {"FAILED_OPTIONAL", "NOT_CONFIGURED"}
            }
        )
        warnings = (["REPLAY_NOT_LIVE"] if fixture else []) + (
            ["OPTIONAL_SOURCE_UNAVAILABLE"] if report["degraded_sources"] else []
        )
        gates.finish(
            "acquisition",
            {
                "nonempty_critical_sources": bool(ports and activity),
                "registry_version": registry.get("schema_version") == "1.0",
                "source_failure_policy": all(
                    s.get("failure_policy") in {"BLOCK", "DECLARED_DEGRADED"}
                    for s in registry["sources"]
                ),
            },
            {"received_ports": len(ports), "received_activity": len(activity)},
            warnings,
        )
        gates.start("bronze")
        import hashlib

        evidence = []
        for event in fetcher.events:
            if event.get("raw_path"):
                path = Path(event["raw_path"])
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != event["checksum"]:
                    raise GovernanceError("Bronze checksum mismatch")
                evidence.append(
                    {
                        "source_id": event["source_id"],
                        "checksum": actual,
                        "path": str(path.relative_to(store.root)),
                        "retrieved_at": event["retrieved_at"],
                    }
                )
        if fixture:
            evidence.append(
                {
                    "source_id": "replay_bundle",
                    "checksum": hashlib.sha256(Path(fixture).read_bytes()).hexdigest(),
                    "scope": "NORMALIZED_REPLAY_NOT_LIVE_SOURCE",
                }
            )
        report["bronze_manifest"] = evidence
        gates.finish(
            "bronze",
            {"evidence_retained": bool(evidence), "payload_hashes_verified": True},
            {"payloads": len(evidence)},
        )
        gates.start("silver")
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
        write_json(store.root / "quarantine" / run_id / "dispositions.json", dq["dispositions"])
        if dq["status"] != "PASS":
            raise ValueError(f"Critical DQ failed: {len(dq['errors'])} checks; inspect run report")
        ports, activity, routes = clean["ports"], clean["activity"], clean["routes"]
        if checkpoint:
            store.set_metadata(*checkpoint)
        for name, rows in clean.items():
            write_json(store.root / "silver" / run_id / (name + ".json"), rows)
            store.write_layer("silver", name, run_id, rows)
            if store.read_layer("silver", name, run_id, approved=False) != rows:
                raise GovernanceError("Silver persisted readback failed")
        # Analytical callers consume the persisted, validated Silver contract.
        ports, activity, routes = (
            store.read_layer("silver", name, run_id, approved=False)
            for name in ("ports", "activity", "routes")
        )
        from maritime.medallion import weekly_gold, weekly_silver

        weeks = weekly_silver(ports, activity, as_of, run_id)
        store.write_layer("silver", "port_weeks", run_id, weeks)
        write_json(store.root / "silver" / run_id / "port_weeks.json", weeks)
        persisted_weeks = store.read_layer("silver", "port_weeks", run_id, approved=False)
        if persisted_weeks != weeks:
            raise GovernanceError("Weekly Silver persisted readback failed")
        port_weeks = weekly_gold(persisted_weeks, as_of)
        report["stage_status"]["silver"] = "PASS"
        gates.finish(
            "silver",
            {
                "canonical_dq": dq["status"] == "PASS",
                "record_accounting": dq["accounting"]["balanced"],
            },
            dq["accounting"],
        )
        gates.start("metrics")
        history = congestion(activity, config["baseline_days"], config["min_history"])
        states = latest_states(history)
        graph, edges = network_state(ports, routes, states, as_of)
        exposure = propagate(
            graph, states, config["propagation_horizon_hours"], config["propagation_decay"]
        )
        from maritime.governance import verify_current_metrics

        verification = verify_current_metrics(activity, states, config)
        report["independent_metrics"] = verification
        gates.finish(
            "metrics",
            {
                "independent_current_metrics": all(v["passed"] for v in verification),
                "port_coverage": len(states) == len(ports),
            },
        )
        gates.start("scenario")
        generated = shipments(graph, config["shipments"], config["seed"], as_of)
        interventions, decisions = [], []
        for shipment in generated:
            outcomes = evaluate(
                graph, shipment, config["scenario_assumptions"], config["seed"], config["draws"]
            )
            interventions.extend(outcomes)
            decisions.append(
                {
                    **rank(outcomes),
                    "forecast_usage": "NOT_USED_FOR_RANKING",
                }
            )
        baseline = [o for o in interventions if o["action"] == "NO_ACTION"]
        gates.finish(
            "scenario",
            {
                "shipment_action_accounting": len(interventions) == len(generated) * len(ACTIONS),
                "all_outputs_simulated": all(
                    o["classification"] == "SIMULATED" for o in interventions + decisions
                ),
            },
        )
        gates.start("features_ml")
        if ml_backend == "azure_ml":
            from maritime.ml_contract import export_features

            manifest = export_features(activity, store.root / "azure_features" / run_id, run_id)
            ml_report = {
                "status": "EXPORTED_FOR_AZURE_ML",
                "feature_manifest": manifest,
                "sla_model_status": "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA",
            }
            predictions = []
        elif ml_backend == "local":
            ml_report, predictions = experiment(activity, store.root / "models")
        else:
            raise ValueError("Unsupported ML backend")
        gates.finish(
            "features_ml",
            {
                "sla_not_trained": ml_report.get("sla_model_status", "").startswith("DEFERRED"),
                "prediction_classification": all(
                    p["classification"] == "PREDICTED" for p in predictions
                ),
            },
            {"predictions": len(predictions)},
            ["LOCAL_RESEARCH_MODEL"] if predictions else [],
        )
        gates.start("gold")
        store.write_layer("gold", "port_weeks", run_id, port_weeks)
        write_json(store.root / "gold" / run_id / "operations" / "port_weeks.json", port_weeks)
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
            "sources": [dict(s) for s in registry["sources"]],
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
        # Classification follows the most uncertain computational component.
        for row in products["early_warning"]:
            if any(e["classification"] == "SIMULATED" for e in exposure):
                row["classification"] = "SIMULATED"
        enrich(products, report, config)
        verification = verify_products(products, config, as_of)
        report["product_verification"] = verification
        gates.finish(
            "gold",
            {"dataset_contracts_and_independent_checks": verification["status"] == "PASS"},
            verification["reconciliation"],
        )
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
            "forecast_affects_ranking": False,
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
        gates.start("publication")
        manifest = release_manifest(products, report)
        manifest["medallion_version"] = "1.0"
        manifest["medallion"] = {
            f"silver.{name}": {"rows": len(rows), "sha256": fingerprint(rows)}
            for name, rows in {**clean, "port_weeks": weeks}.items()
        }
        manifest["medallion"]["gold.port_weeks"] = {
            "rows": len(port_weeks),
            "sha256": fingerprint(port_weeks),
        }
        manifest["release_id"] = fingerprint([manifest["release_id"], manifest["medallion"]])
        from maritime.governance import verify_manifest

        verify_manifest({name: store.read(name, run_id) for name in products}, manifest)
        gates.finish(
            "publication",
            {"persisted_readback": True, "audit_chain": store.verify_audit()["status"] == "PASS"},
        )
        report["governance"]["status"] = manifest["status"]
        report["release"] = manifest
        report["status"] = "SUCCESS"
        report["end_time"] = utcnow()
        write_json(store.root / "releases" / (run_id + ".json"), manifest)
    except Exception as exc:
        report["status"] = "FAILED"
        gates.fail(exc)
        report["failures"].append({"type": type(exc).__name__, "message": str(exc)})
        logger.exception("pipeline_failed", extra={"run_id": run_id})
        raise
    finally:
        report["source_status"].extend(fetcher.events)
        source_definitions = {s["source_id"]: s for s in registry["sources"]}
        for event in report["source_status"]:
            definition = source_definitions.get(event["source_id"], {})
            for key in ("source_name", "source_url", "schema_version", "classification"):
                event.setdefault(key, definition.get(key))
            event.setdefault("dataset_version", definition.get("dataset_version"))
            event.setdefault("record_count", 0)
            event["run_id"] = run_id
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
        if report["status"] == "SUCCESS":
            try:
                store.publish(report, report["release"])
            except Exception as exc:
                report["status"] = "FAILED"
                report["governance"]["status"] = "BLOCKED"
                report["failures"].append({"type": type(exc).__name__, "message": str(exc)})
                store.run(report)
                report_files(store, report)
                raise
    return report


def run(*args, **kwargs):
    import inspect
    import re

    bound = inspect.signature(_run).bind(*args, **kwargs)
    bound.apply_defaults()
    root = bound.arguments["root"]
    run_id = bound.arguments["run_id"]
    if run_id and not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise GovernanceError("Invalid run identifier")
    request = {
        k: str(v)
        for k, v in bound.arguments.items()
        if k not in {"fetcher", "request_fingerprint", "root", "run_id"}
    }
    try:
        for k in ("config_path", "registry_path", "fixture"):
            path = bound.arguments[k]
            if path:
                request[k] = fingerprint(load_json(path))
    except (OSError, ValueError) as exc:
        # A configuration failure is an attempted operation, even before ingestion.
        # Use a fresh ID so invalid retries cannot overwrite an approved run.
        with exclusive_run(root):
            store = Store(root)
            failed = {
                "run_id": uuid.uuid4().hex,
                "requested_run_id": run_id,
                "status": "FAILED",
                "start_time": utcnow(),
                "end_time": utcnow(),
                "stage_status": {"preflight": "BLOCKED"},
                "failures": [{"type": type(exc).__name__, "message": str(exc)}],
                "accounting": {"input": 0, "persisted": 0, "failed": 0},
            }
            store.run(failed)
            store.audit("preflight_failure", failed)
            report_files(store, failed)
        raise
    request_id = fingerprint(request)
    with exclusive_run(root):
        store = Store(root)
        with store.connect() as con:
            if run_id:
                prior = con.execute("SELECT report FROM runs WHERE run_id=?", (run_id,)).fetchone()
                if prior:
                    prior = json.loads(prior[0])
                    if (
                        prior["status"] == "SUCCESS"
                        and prior.get("request_fingerprint") == request_id
                        and store.release(run_id)
                    ):
                        for name in store.release(run_id)["datasets"]:
                            store.read_approved(name, run_id)
                        return prior
                    raise GovernanceError("Conflicting or failed run ID; use a new retry run ID")
            abandoned = con.execute("SELECT report FROM runs WHERE status='RUNNING'").fetchall()
        for row in abandoned:
            previous = json.loads(row[0])
            previous.update(status="ABANDONED", end_time=utcnow())
            store.run(previous)
            store.audit(
                "recovery",
                {
                    "run_id": previous["run_id"],
                    "status": "ABANDONED",
                    "reason": "OS lock reacquired after interrupted execution",
                },
            )
        bound.arguments["request_fingerprint"] = request_id
        bound.arguments["run_id"] = run_id or uuid.uuid4().hex
        try:
            return _run(**bound.arguments)
        except Exception as exc:
            # Gate/contract initialization can fail before _run stores its report.
            with store.connect() as con:
                existing = con.execute(
                    "SELECT 1 FROM runs WHERE run_id=?", (bound.arguments["run_id"],)
                ).fetchone()
            if not existing:
                failed = {
                    "run_id": bound.arguments["run_id"],
                    "status": "FAILED",
                    "start_time": utcnow(),
                    "end_time": utcnow(),
                    "stage_status": {"preflight": "BLOCKED"},
                    "failures": [{"type": type(exc).__name__, "message": str(exc)}],
                }
                store.run(failed)
                store.audit("preflight_failure", failed)
                report_files(store, failed)
            raise
