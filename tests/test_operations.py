import copy
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from maritime.api import create_app
from maritime.governance import fingerprint
from maritime.medallion import GoldWeek, risk_level, weekly_gold, weekly_silver
from maritime.operations import Conflict, DeliveryResult, Operations, ReviewAction
from maritime.pipeline import load_json, run
from maritime.sources import SourceError, ingest_portwatch, normalize_activity, normalize_ports
from maritime.store import Store


@pytest.mark.parametrize(
    "score,level",
    [
        (None, "INSUFFICIENT_HISTORY"),
        (0, "NORMAL"),
        (0.9999, "NORMAL"),
        (1, "ELEVATED"),
        (-2, "HIGH"),
        (2.999, "HIGH"),
        (3, "CRITICAL"),
        (-3, "CRITICAL"),
    ],
)
def test_weekly_risk_boundaries(score, level):
    assert risk_level(score) == level
    with pytest.raises(ValueError):
        risk_level(float("nan"))


def test_weekly_missing_days_and_reference_lineage(bundle):
    day = date.fromisoformat(bundle["as_of"])
    rows = weekly_silver(bundle["ports"], bundle["activity"], day, "weekly")
    gold = weekly_gold(rows, day)
    assert any(r["review_eligible"] for r in gold)
    assert all(r["classification"] == "SIMULATED" for r in gold)
    complete = next(
        r for r in rows if len(r["reference_weeks"]) >= 4 and r["quality_status"] == "PASS"
    )
    deleted_day = complete["observation_dates"][2]
    altered = [
        r
        for r in bundle["activity"]
        if not (r["port_id"] == complete["port_id"] and r["date"] == deleted_day)
    ]
    changed = next(
        r
        for r in weekly_silver(bundle["ports"], altered, day, "weekly")
        if r["port_id"] == complete["port_id"] and r["week_start"] == complete["week_start"]
    )
    assert changed["weekly_calls"] is None
    assert changed["observed_calls"] > 0 and changed["observed_days"] == 6
    assert changed["z_score"] is None and deleted_day in changed["missing_dates"]
    assert weekly_gold([changed], day)[0]["risk_level"] == "INCOMPLETE"
    assert complete["source_lineage_ids"] and complete["input_sha256"]
    assert max(complete["reference_weeks"]) < complete["week_start"]
    stale = weekly_gold(rows, day + timedelta(days=11))
    assert all(r["freshness_status"] == "STALE" and not r["review_eligible"] for r in stale)
    assert all(GoldWeek.model_validate(r) for r in stale)
    # New retrieval timestamps cannot change observation-based weekly risk revisions.
    retrieved = copy.deepcopy(bundle["activity"])
    for row in retrieved:
        row["retrieved_at"] = "2026-10-22T00:00:00Z"
    revised = weekly_gold(weekly_silver(bundle["ports"], retrieved, day, "other"), day)
    assert [r["risk_revision"] for r in gold] == [r["risk_revision"] for r in revised]


def test_canonical_hamad_reference_activity_and_id_pin(tmp_path, config):
    reference = load_json("tests/data/hamad-reference.json")["features"]
    selected = [
        f["attributes"]
        for f in reference
        if f["attributes"]["country"] == "Qatar"
        and (f["attributes"].get("LOCODE") or "").replace(" ", "") == "QAHMD"
    ]
    assert len(selected) == 1 and selected[0]["portid"] == "port2026"
    activity = [
        f["attributes"] for f in load_json("tests/data/hamad-activity-latest.json")["features"]
    ]
    assert {r["portid"] for r in activity} == {"port2026"}
    assert max(r["date"] for r in activity) == "2026-10-16"
    assert (date(2026, 10, 22) - date.fromisoformat(max(r["date"] for r in activity))).days == 6
    meta = {"retrieved_at": "2026-10-22T00:00:00Z", "checksum": fingerprint(activity)}
    for row in selected + activity:
        row["_metadata"] = meta
    assert normalize_ports(selected)[0]["unlocode"] == "QAHMD"
    assert normalize_activity(activity)[0]["date"] == activity[0]["date"]
    config["port_names"] = ["Hamad Port"]

    class Adapter:
        def arcgis(self, source, where):
            return selected if source["source_id"] == "portwatch_ports" else activity

    ports, daily, _ = ingest_portwatch(
        Adapter(), load_json("configs/sources.json"), config, Store(tmp_path), date(2026, 10, 22)
    )
    assert ports[0]["port_id"] == daily[0]["port_id"] == "port2026"
    selected[0]["portid"] = "unverified"
    with pytest.raises(SourceError, match="canonical port"):
        ingest_portwatch(
            Adapter(),
            load_json("configs/sources.json"),
            config,
            Store(tmp_path),
            date(2026, 10, 22),
        )


@pytest.fixture
def workflow(tmp_path, fixture_path):
    report = run(tmp_path / "analytical", fixture=fixture_path)
    store = Store(tmp_path / "analytical")
    config = load_json("configs/workflow.json")
    config["recipients"] = ["operations@example.test"]
    clock = [datetime(2026, 10, 7, 12, tzinfo=timezone.utc)]
    ops = Operations(store, tmp_path / "operational", config, clock=lambda: clock[0])
    return ops, store, report, clock


def action(row, key="review-request-1", verb="MONITOR", reason="Monitor next activity update"):
    return ReviewAction(
        request_id=key,
        action=verb,
        reason=reason,
        expected_version=row["review_version"],
        risk_revision=row["risk_revision"],
    )


def test_bronze_silver_gold_persistence_and_workflow_separation(workflow):
    ops, store, report, clock = workflow
    silver = store.read_layer("silver", "activity")
    gold = store.read_layer("gold", "port_weeks")
    assert silver and gold
    assert report["release"]["medallion"]["gold.port_weeks"]["sha256"] == fingerprint(gold)
    selected = next(r for r in ops.queue() if r["review_eligible"])
    result = ops.review(selected["review_id"], action(selected), "entra-test-oid")
    assert result["actor"] == "entra-test-oid" and result["previous_action"] is None
    assert ops.review(selected["review_id"], action(selected), "entra-test-oid") == result
    with pytest.raises(Conflict):
        ops.review(selected["review_id"], action(selected, key="second-request"), "another-oid")
    with pytest.raises(Conflict):
        ops.review(selected["review_id"], action(selected, verb="ESCALATE"), "entra-test-oid")
    assert len(ops.history(selected["review_id"])) == 1
    assert store.read_layer("silver", "activity") == silver
    assert store.read_layer("gold", "port_weeks") == gold
    assert ops.path != store.path
    with ops.connect() as con, pytest.raises(Exception, match="immutable"):
        con.execute("DELETE FROM actions")
    clock[0] += timedelta(days=11)
    with pytest.raises(Conflict, match="stale"):
        ops.review(selected["review_id"], action(selected, key="stale-request"), "entra-test-oid")


def test_ignore_justification_and_action_history(workflow):
    ops, _, _, _ = workflow
    row = next(r for r in ops.queue() if r["review_eligible"])
    with pytest.raises(ValueError, match="forty"):
        ops.review(row["review_id"], action(row, verb="IGNORE"), "operator")
    result = ops.review(
        row["review_id"],
        action(
            row,
            verb="IGNORE",
            reason="Reviewed supporting observations and documented an approved operational exception.",
        ),
        "operator",
    )
    row = ops.queue(review_id=row["review_id"])[0]
    assert row["review_status"] == "IGNORE" and row["owner"] == "operator"
    next_action = ops.review(
        row["review_id"], action(row, key="escalate-request", verb="ESCALATE"), "supervisor"
    )
    assert next_action["previous_action"] == result["action"]
    assert len(ops.history(row["review_id"])) == 2


def test_escalation_dedup_retry_delivery_and_lease(workflow):
    ops, _, _, clock = workflow
    events = ops.events()
    assert events and all(e["risk_level"] in {"HIGH", "CRITICAL"} for e in events)
    assert ops.events() == events
    event = ops.claim()
    assert "reason" not in event and event["recipients"] == ["operations@example.test"]
    failed = DeliveryResult(
        lease_token=event["lease_token"], outcome="FAILED", failure_reason="connector unavailable"
    )
    assert ops.complete(event["event_id"], failed)["delivery_status"] == "PENDING"
    assert ops.complete(event["event_id"], failed)["delivery_status"] == "PENDING"
    clock[0] += timedelta(seconds=60)
    retry = ops.claim()
    assert retry["event_id"] == event["event_id"] and retry["attempt"] == 2
    clock[0] += timedelta(seconds=301)
    reclaimed = ops.claim()
    assert reclaimed["event_id"] == event["event_id"] and reclaimed["attempt"] == 3
    with pytest.raises(Conflict):
        ops.complete(
            event["event_id"], DeliveryResult(lease_token=retry["lease_token"], outcome="SENT")
        )
    assert (
        ops.complete(
            event["event_id"], DeliveryResult(lease_token=reclaimed["lease_token"], outcome="SENT")
        )["delivery_status"]
        == "SENT"
    )


@pytest.mark.parametrize(
    "recipients,expected",
    [([], "RECIPIENTS_NOT_CONFIGURED"), (["ops@example.test"], "NOTIFICATION_TRANSPORT_FAILED")],
)
def test_delivery_exception_without_recipients_and_transport_failure(
    workflow, recipients, expected
):
    ops, _, _, _ = workflow
    ops.config["recipients"] = recipients
    ops.config["max_attempts"] = 1
    calls = []

    def fail(event):
        calls.append(event)
        raise TimeoutError("private response not returned to caller")

    result = ops.deliver_next(fail)
    assert result["delivery_status"] == "EXCEPTION"
    assert result["failure_reason"] == expected
    assert len(calls) == bool(recipients)
    assert any(e["unresolved_exception"] for e in ops.events())


def test_medallion_partial_write_cannot_publish(tmp_path, fixture_path, monkeypatch):
    first = run(tmp_path, fixture=fixture_path)
    original = Store.write_layer

    def partial(self, layer, dataset, run_id, rows):
        return original(self, layer, dataset, run_id, rows[:-1] if layer == "gold" else rows)

    monkeypatch.setattr(Store, "write_layer", partial)
    with pytest.raises(ValueError, match="Medallion persisted"):
        run(tmp_path, fixture=fixture_path)
    assert Store(tmp_path).metadata("published_run") == first["run_id"]


def test_operations_api_auth_filters_reporting_and_stale_state(workflow, monkeypatch):
    ops, store, _, _ = workflow
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    monkeypatch.setattr("maritime.operations_api.Operations", lambda *args: ops)
    client = TestClient(create_app(store.root))
    assert client.get("/operations/queue").status_code == 401
    reader, operator = {"X-API-Key": "reader"}, {"X-API-Key": "operator"}
    queue = client.get("/operations/queue?risk_level=CRITICAL", headers=reader)
    assert queue.status_code == 200 and queue.json()["items"]
    row = next(r for r in queue.json()["items"] if r["review_eligible"])
    body = action(row).model_dump()
    path = "/operations/reviews/" + row["review_id"]
    assert client.post(path, headers=reader, json=body).status_code == 403
    assert client.post(path, headers=operator, json={**body, "actor": "spoofed"}).status_code == 422
    response = client.post(path, headers=operator, json=body)
    assert response.status_code == 200 and response.json()["actor"] == "local-shared-operator"
    packet = client.get("/operations/reporting", headers=operator).json()
    assert packet["fact_review_history"]
    assert packet["relationships"]["fact_review_history.review_id"] == "fact_port_weeks.review_id"
    assert client.get(row["observation_link"], headers=reader).status_code == 200
    assert client.get("/operations/queue?port_id=port2026", headers=reader).json()["items"] == []
    assert client.post("/operations/events/claim", headers=reader).status_code == 403


def test_workflow_configuration_rejects_invalid_contracts(tmp_path):
    from maritime.operations import configuration

    config = load_json("configs/workflow.json")
    for field, value in [
        ("recipients", ["a@example.test;other@example.test"]),
        ("max_attempts", 0),
        ("lease_seconds", True),
        ("schema_version", "future"),
    ]:
        path = tmp_path / "config.json"
        path.write_text(__import__("json").dumps({**config, field: value}))
        with pytest.raises(ValueError):
            configuration(path)


def test_reporting_fields_and_hamad_filter(workflow, monkeypatch, tmp_path):
    import runpy

    ops, store, _, _ = workflow
    row = next(r for r in ops.queue() if r["review_eligible"])
    ops.review(row["review_id"], action(row), "report-operator")
    ops.deliver_next(lambda _: None)
    # Select an actual fixture port to test the configured focus filter without inventing Hamad data.
    ops.config["focus_port_id"] = row["port_id"]
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    monkeypatch.setenv("MARITIME_OPERATOR_KEY", "operator")
    monkeypatch.setattr("maritime.operations_api.Operations", lambda *args: ops)
    client = TestClient(create_app(store.root))
    packet = client.get("/operations/reporting", headers={"X-API-Key": "operator"}).json()
    client.headers["X-API-Key"] = "operator"
    exporter = runpy.run_path("scripts/export_operations.py")["export"]
    output = tmp_path / "operations-snapshot.json"
    exporter(client, output)
    assert load_json(output) == packet
    with pytest.raises(FileExistsError):
        exporter(client, output)
    model = load_json("power-platform/reporting/model-contract.json")
    for table, columns in model["tables"].items():
        assert packet[table], table
        for record in packet[table]:
            assert set(columns) <= set(record), (table, set(columns) - set(record))
    assert {r["port_id"] for r in packet["fact_hamad_port_weeks"]} == {row["port_id"]}
    assert all(r["risk_level"] in {"HIGH", "CRITICAL"} for r in packet["fact_review_queue"])
    assert len({r["review_id"] for r in packet["fact_port_weeks"]}) == len(
        packet["fact_port_weeks"]
    )
    for _, _, table, day, fields in runpy.run_path("scripts/build_powerbi.py")["OPERATIONS_PAGES"]:
        assert set([day, *fields, "classification", "lineage_id", "run_id"]) <= set(
            model["tables"][table]
        )
    filtered = client.get(
        "/operations/queue?flagged_only=true&limit=1", headers={"X-API-Key": "reader"}
    ).json()
    assert filtered["total"] == len(packet["fact_review_queue"]) and len(filtered["items"]) == 1


def test_event_transitions_and_stale_pending_are_audited(workflow):
    ops, store, _, clock = workflow
    original = ops.events()
    row = next(r for r in ops.queue() if r["review_eligible"])
    snapshot = copy.deepcopy(store.read_layer("gold", "port_weeks"))
    target = next(r for r in snapshot if r["review_id"] == row["review_id"])
    target["risk_level"] = "HIGH" if row["risk_level"] == "CRITICAL" else "CRITICAL"
    target["risk_revision"] = "changed-revision"

    class ApprovedSource:
        def release(self):
            return store.release()

        def read_layer(self, *args):
            return snapshot

        def metadata(self, key):
            return store.metadata(key)

    ops.source = ApprovedSource()  # Approved-Gold boundary fake, production event logic unchanged.
    assert len(ops.events()) == len(original) + 1
    assert len(ops.events()) == len(original) + 1
    clock[0] += timedelta(days=11)
    assert ops.claim() is None
    assert all(
        e["delivery_status"] == "EXCEPTION"
        and e["last_failure_reason"] == "SUPERSEDED_OR_STALE_GOLD"
        for e in ops.events()
    )


def test_power_platform_artifacts_match_real_contracts(tmp_path, monkeypatch):
    import json
    import runpy
    from pathlib import Path

    import jsonschema

    build = runpy.run_path("scripts/build_power_platform.py")["build"]
    generated = build(tmp_path / "artifacts")
    for artifact in generated.rglob("*"):
        if artifact.is_file():
            assert (
                artifact.read_bytes()
                == (Path("power-platform") / artifact.relative_to(generated)).read_bytes()
            )
    for schema, artifact in [
        ("canvas-schema.json", "canvas/OperationsReview.pa.yaml"),
        ("workflow-definition.json", "automate/GoldRiskEscalation.definition.json"),
    ]:
        jsonschema.validate(
            load_json(generated / artifact), load_json("configs/powerplatform_schemas/" + schema)
        )
    monkeypatch.setenv("MARITIME_API_KEY", "reader")
    api = create_app(tmp_path / "api").openapi()
    connector = load_json(generated / "connector/openapi.json")
    for path, methods in connector["paths"].items():
        for method, operation in methods.items():
            assert method in api["paths"][path]
            assert {p["name"] for p in operation["parameters"] if p["in"] != "body"} <= {
                p["name"] for p in api["paths"][path][method].get("parameters", [])
            }
    assert connector["definitions"]["ReviewAction"]["additionalProperties"] is False
    assert connector["definitions"]["ReviewAction"]["properties"]["action"]["enum"] == [
        "IGNORE",
        "MONITOR",
        "ESCALATE",
    ]
    flow = load_json(generated / "automate/GoldRiskEscalation.definition.json")
    actions = flow["actions"]["IfEvent"]["actions"]["HasRecipients"]["actions"]
    assert actions["RecordSuccess"]["runAfter"] == {"Send": ["Succeeded"]}
    assert actions["RecordFailure"]["runAfter"] == {"Send": ["Failed", "TimedOut"]}
    assert actions["Send"]["inputs"]["retryPolicy"] == {"type": "None"}
    assert "z_score" not in json.dumps(flow) and "reason" not in actions["Send"]["inputs"]["body"]
    report = runpy.run_path("scripts/build_powerbi.py")
    output = report["build"](tmp_path / "report", include_operations=True)
    assert report["validate"](output)["pages"] == 10
    import re

    model = load_json(generated / "reporting/model-contract.json")
    for table, columns in model["tables"].items():
        query = (generated / "reporting" / (table + ".pq")).read_text()
        assert "OperationsSnapshot[" + table + "]" in query
        assert "MissingField.UseNull" in query
        assert all(json.dumps(field) in query for field in columns)
    dax = (generated / "reporting/operations-measures.dax").read_text()
    for table, field in re.findall(r"(fact_\w+)\[(\w+)\]", dax):
        assert field in model["tables"][table]
    assert "z_score" not in dax

    for artifact in output.rglob("*"):
        if artifact.is_file():
            assert (
                artifact.read_bytes()
                == (
                    Path("fabric/powerbi/Maritime.Report") / artifact.relative_to(output)
                ).read_bytes()
            )


def test_cloud_medallion_adapter_contract(workflow):
    from test_code_integration import BlobContainer

    from maritime.azure_store import AzureStore

    ops, local, report, _ = workflow
    transport = BlobContainer()
    cloud = AzureStore(transport, BlobContainer())
    cloud.publish(local.root / "gold" / report["run_id"], report)
    assert cloud.read_layer("silver", "activity") == local.read_layer("silver", "activity")
    assert cloud.read_layer("gold", "port_weeks") == local.read_layer("gold", "port_weeks")
    ops.source = cloud
    assert ops.queue()
    blob = next(k for k in transport.blobs if "/medallion/gold.port_weeks." in k)
    transport.blobs[blob] = b"[]"
    with pytest.raises(ValueError, match="integrity"):
        ops.queue()
