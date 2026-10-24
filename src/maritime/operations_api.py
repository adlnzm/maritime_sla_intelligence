"""Shared server contracts consumed by Power Apps, Automate and reporting."""

import os
from pathlib import Path

from fastapi import Depends, HTTPException, Query

from maritime.operations import Conflict, DeliveryResult, Operations, ReviewAction, configuration


def register_operations(app, store, root, reader, operator):
    def service():
        location = os.getenv("MARITIME_WORKFLOW_DIR")
        if not location:
            if os.getenv("MARITIME_STORAGE_BACKEND") == "azure_blob" and root is None:
                raise HTTPException(503, "Durable operational store is not configured")
            location = Path(root or os.getenv("MARITIME_DATA_DIR", "data")) / "operations"
        try:
            config = configuration(os.getenv("MARITIME_WORKFLOW_CONFIG", "configs/workflow.json"))
        except (ValueError, OSError):
            raise HTTPException(503, "Workflow configuration unavailable or invalid") from None
        return Operations(store, location, config)

    def invoke(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/operations/queue", dependencies=[Depends(reader)])
    def queue(
        port_id: str | None = None,
        week_start: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        review_id: str | None = None,
        country: str | None = None,
        flagged_only: bool = False,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        try:
            rows = service().queue(
                port_id=port_id,
                week_start=week_start,
                risk_level=risk_level,
                review_status=review_status,
                review_id=review_id,
                country=country,
            )
        except ValueError:
            raise HTTPException(503, "Approved weekly Gold is unavailable") from None
        if flagged_only:
            rows = [row for row in rows if row["risk_level"] in {"HIGH", "CRITICAL"}]
        return {"total": len(rows), "items": rows[offset : offset + limit]}

    @app.post("/operations/reviews/{review_id}", dependencies=[Depends(operator)])
    def review(review_id: str, body: ReviewAction, actor=Depends(operator)):
        return invoke(
            service().review, review_id, body, actor["oid"] if actor else "local-shared-operator"
        )

    @app.get("/operations/history", dependencies=[Depends(operator)])
    def history(review_id: str | None = None):
        return {"items": service().history(review_id)}

    @app.get("/operations/events", dependencies=[Depends(operator)])
    def events():
        return {"items": invoke(service().events)}

    @app.post("/operations/events/claim", dependencies=[Depends(operator)])
    def claim():
        return {"event": invoke(service().claim)}

    @app.post("/operations/events/{event_id}/result", dependencies=[Depends(operator)])
    def result(event_id: str, body: DeliveryResult):
        return invoke(service().complete, event_id, body)

    @app.get("/operations/observations/{review_id}", dependencies=[Depends(reader)])
    def observations(review_id: str, run_id: str):
        try:
            weekly = next(
                r
                for r in store.read_layer("gold", "port_weeks", run_id)
                if r["review_id"] == review_id
            )
            rows = store.read_layer("silver", "activity", run_id)
        except (ValueError, StopIteration):
            raise HTTPException(503, "Approved Silver observations unavailable") from None
        return {
            "run_id": run_id,
            "items": [
                r
                for r in rows
                if r["port_id"] == weekly["port_id"]
                and weekly["week_start"] <= r["date"] <= weekly["week_end"]
            ],
        }

    @app.get("/operations/reporting", dependencies=[Depends(operator)])
    def reporting():
        operations = service()
        queue_rows = invoke(operations.queue)
        return {
            "schema_version": "1.0",
            "fact_port_weeks": queue_rows,
            "fact_review_queue": [r for r in queue_rows if r["risk_level"] in {"HIGH", "CRITICAL"}],
            "fact_hamad_port_weeks": [
                row
                for row in queue_rows
                if row["port_id"] == operations.config.get("focus_port_id")
            ],
            "fact_review_history": operations.history(),
            "fact_escalations": invoke(operations.events),
            "relationships": {
                "fact_review_history.review_id": "fact_port_weeks.review_id",
                "fact_escalations.review_id": "fact_port_weeks.review_id",
            },
        }
