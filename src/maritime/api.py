import hmac
import json
import logging
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from maritime.models import Outcome, Review
from maritime.store import Store


def create_app(root=None):
    from maritime.azure_security import configure_telemetry

    if os.getenv("MARITIME_AUTH_MODE", "key") not in {"key", "entra"}:
        raise ValueError("Unknown authentication mode")
    if os.getenv("MARITIME_STORAGE_BACKEND", "sqlite") not in {"sqlite", "azure_blob"}:
        raise ValueError("Unknown storage backend")
    configure_telemetry()
    if os.getenv("MARITIME_STORAGE_BACKEND") == "azure_blob":
        from maritime.azure_store import AzureStore

        store = AzureStore()
    else:
        store = Store(root or os.getenv("MARITIME_DATA_DIR", "data"))

    def verified_read(product, run_id=None):
        try:
            manifest = store.release(run_id)
            if not manifest:
                raise ValueError("Requested run is not approved")
            if manifest["execution_mode"] == "LIVE_PUBLIC_DATA":
                from datetime import date, datetime, timezone

                from maritime.governance import contract

                if (
                    datetime.now(timezone.utc).date() - date.fromisoformat(manifest["as_of"])
                ).days > contract()["freshness_days"]:
                    raise ValueError("Published live snapshot is stale")
            return store.read_approved(product, run_id)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc

    def published_report():
        if hasattr(store, "published_report"):
            return store.published_report()
        return store.latest_report()

    app = FastAPI(title="Maritime Congestion & SLA Intelligence", version="0.1.0")
    counters = {"requests": 0, "errors": 0, "duration_seconds": 0.0}

    def authenticate(x_api_key: str = Header(default=""), authorization: str = Header(default="")):
        if os.getenv("MARITIME_AUTH_MODE") == "entra":
            from maritime.azure_security import verify_entra

            return verify_entra(authorization, "reader")
        expected = os.getenv("MARITIME_API_KEY")
        operator = os.getenv("MARITIME_OPERATOR_KEY")
        if not expected:
            raise HTTPException(503, "API authentication is not configured")
        if not any(
            hmac.compare_digest(x_api_key, value) for value in (expected, operator) if value
        ):
            raise HTTPException(401, "Invalid API key")

    def authorize_operator(
        x_api_key: str = Header(default=""), authorization: str = Header(default="")
    ):
        if os.getenv("MARITIME_AUTH_MODE") == "entra":
            from maritime.azure_security import verify_entra

            return verify_entra(authorization, "operator")
        expected = os.getenv("MARITIME_OPERATOR_KEY")
        if not expected or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(403, "Operator role required")

    @app.middleware("http")
    async def measure(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        counters["requests"] += 1
        counters["errors"] += response.status_code >= 400
        counters["duration_seconds"] += elapsed
        logging.getLogger("maritime.api").info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_seconds": elapsed,
                }
            )
        )
        return response

    @app.get("/health")
    def health():
        return {"status": "alive", "version": "0.1.0"}

    @app.get("/ready", dependencies=[Depends(authenticate)])
    def ready():
        run_id = store.metadata("published_run")
        if not run_id:
            raise HTTPException(503, "No successfully published pipeline run")
        verified_read("ports", run_id)
        return {"status": "ready", "run_id": run_id, "release": store.release(run_id)}

    def register(path, product):
        def endpoint(
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0),
            run_id: str | None = None,
        ):
            if not (run_id or store.metadata("published_run")):
                raise HTTPException(503, "No published data")
            rows = verified_read(product, run_id)
            if product == "decisions":
                selected_run = run_id or store.metadata("published_run")
                reviews = {
                    a["decision_id"]: a
                    for a in store.audits("review")
                    if a["run_id"] == selected_run
                }
                for row in rows:
                    if row["decision_id"] in reviews:
                        review = reviews[row["decision_id"]]
                        row["review"] = review
                        row["status"] = {
                            "accept": "ACCEPTED",
                            "reject": "REJECTED",
                            "override": "OVERRIDDEN",
                        }[review["status"]]
            return {
                "run_id": run_id or store.metadata("published_run"),
                "release": store.release(run_id),
                "total": len(rows),
                "items": rows[offset : offset + limit],
            }

        endpoint.__name__ = product
        app.get(path, dependencies=[Depends(authenticate)])(endpoint)

    for path, product in {
        "/ports": "ports",
        "/congestion": "congestion",
        "/congestion/history": "congestion_history",
        "/network": "network",
        "/network/exposure": "exposure",
        "/disruptions": "disruptions",
        "/scenarios": "scenarios",
        "/sla-risk": "sla_risk",
        "/interventions": "interventions",
        "/decisions": "decisions",
        "/lineage": "lineage",
        "/data-quality": "data_quality",
        "/predictions": "predictions",
        "/early-warning": "early_warning",
    }.items():
        register(path, product)

    @app.post("/decisions/{decision_id}/review", dependencies=[Depends(authorize_operator)])
    def review(decision_id: str, body: Review, actor=Depends(authorize_operator)):
        decision = next(
            (r for r in verified_read("decisions") if r["decision_id"] == decision_id), None
        )
        if decision is None:
            raise HTTPException(404, "Decision not found")
        if body.status == "override":
            options = [
                r
                for r in verified_read("interventions")
                if r["shipment_id"] == decision["shipment_id"] and r["feasible"]
            ]
            if body.action not in {r["action"] for r in options}:
                raise HTTPException(
                    422, "Override action must be a feasible evaluated intervention"
                )
        payload = {
            **body.model_dump(),
            "decision_id": decision_id,
            "run_id": store.metadata("published_run"),
        }
        if actor:
            payload["operator"] = actor["oid"]
        return {"audit_id": store.audit("review", payload), **payload}

    @app.post("/outcomes")
    def outcome(body: Outcome, actor=Depends(authorize_operator)):
        decisions = verified_read("decisions")
        decision = next((d for d in decisions if d["decision_id"] == body.decision_id), None)
        if decision is None:
            raise HTTPException(404, "Decision not found")
        if body.classification not in {"OBSERVED", "SIMULATED"}:
            raise HTTPException(422, "Outcomes must declare OBSERVED or SIMULATED")
        if decision["classification"] == "SIMULATED" and body.classification != "SIMULATED":
            raise HTTPException(422, "Cannot attach a real outcome to a synthetic shipment")
        action = next(
            (
                o
                for o in verified_read("interventions")
                if o["shipment_id"] == decision["shipment_id"]
                and o["action"] == body.actual_action
                and o["feasible"]
            ),
            None,
        )
        if action is None:
            raise HTTPException(422, "Action not feasible")
        breach = body.actual_delay_hours > action["sla_buffer_hours"]
        payload = {
            **body.model_dump(mode="json"),
            "run_id": store.metadata("published_run"),
            "delay_error": body.actual_delay_hours - action["expected_delay_hours"],
            "loss_error": body.actual_loss - action["expected_loss"],
            "brier_score": (int(breach) - action["breach_probability"]) ** 2,
            "followed_recommendation": body.actual_action == decision["recommended_action"],
            "causal_intervention_effectiveness": None,
            "effectiveness_status": "COUNTERFACTUAL_OUTCOME_UNOBSERVABLE",
        }
        if actor:
            payload["operator"] = actor["oid"]
        return {"audit_id": store.audit("outcome", payload), **payload}

    @app.get("/audit", dependencies=[Depends(authorize_operator)])
    def audit():
        return {"reviews": store.audits("review"), "outcomes": store.audits("outcome")}

    @app.get("/run-report", dependencies=[Depends(authenticate)])
    def run_report():
        return published_report()

    @app.get("/signals", dependencies=[Depends(authenticate)])
    def signals():
        return {"items": store.audits("extraction"), "classification": "ANTICIPATED"}

    @app.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(authenticate)])
    def metrics():
        report = published_report() or {}
        reviews = store.audits("review")
        values = {
            "api_requests_total": counters["requests"],
            "api_errors_total": counters["errors"],
            "api_duration_seconds_sum": counters["duration_seconds"],
            "pipeline_duration_seconds": report.get("duration_seconds", 0),
            "dq_score": report.get("data_quality", {}).get("overall_dq_score", 0),
            "scenario_executions": report.get("scenarios", {}).get("executions", 0),
            "decision_count": report.get("decision", {}).get("count", 0),
            "decision_override_rate": sum(r["status"] == "override" for r in reviews)
            / max(1, len(reviews)),
        }
        return "\n".join(f"maritime_{key} {value}" for key, value in values.items()) + "\n"

    return app
