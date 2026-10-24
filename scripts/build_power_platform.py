"""Generate tenant-unbound Power Platform source from the existing operations contracts."""

import argparse
import json
from pathlib import Path

from maritime.medallion import GoldWeek, SilverWeek
from maritime.operations import DeliveryResult, ReviewAction


def save(root, name, value):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def swagger_schema(value):
    if isinstance(value, list):
        return [swagger_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if "anyOf" in value:
        alternatives = value.pop("anyOf")
        nullable = any(a.get("type") == "null" for a in alternatives)
        value.update(next(a for a in alternatives if a.get("type") != "null"))
        if nullable:
            value["x-nullable"] = True
    if "const" in value:
        value["enum"] = [value.pop("const")]
    return {k: swagger_schema(v) for k, v in value.items() if k not in {"title"}}


def reporting_assets(root):
    """Power Query reads the authenticated API export; no thresholds in client assets."""
    columns = {}
    for name, schema in GoldWeek.model_json_schema()["properties"].items():
        kind = schema.get("type")
        if not kind:
            kind = next(
                (v.get("type") for v in schema.get("anyOf", []) if v.get("type") != "null"),
                "string",
            )
        if kind != "array":
            columns[name] = {
                "integer": "Int64.Type",
                "number": "type number",
                "boolean": "type logical",
            }.get(kind, "type text")
    columns.update(
        review_status="type text",
        review_version="Int64.Type",
        owner="type text",
        risk_drivers_text="type text",
    )
    history = dict.fromkeys(
        [
            "request_id",
            "review_id",
            "action",
            "previous_action",
            "reason",
            "actor",
            "owner",
            "created_at",
            "port_id",
            "week_start",
            "risk_level",
            "run_id",
            "classification",
            "lineage_id",
            "risk_revision",
        ],
        "type text",
    )
    history["version"] = "Int64.Type"
    events = dict.fromkeys(
        [
            "event_id",
            "review_id",
            "port_id",
            "port_name",
            "week_start",
            "risk_level",
            "previous_risk",
            "risk_revision",
            "source_latest_observation",
            "freshness_status",
            "created_at",
            "review_reference",
            "run_id",
            "classification",
            "lineage_id",
            "delivery_status",
            "last_attempt_at",
            "last_failure_reason",
        ],
        "type text",
    )
    events.update(
        attempts="Int64.Type", unresolved_exception="type logical", simulated="type logical"
    )
    tables = {
        "fact_port_weeks": columns,
        "fact_review_queue": columns,
        "fact_hamad_port_weeks": columns,
        "fact_review_history": history,
        "fact_escalations": events,
    }
    relationships = [
        {
            "from": t + ".review_id",
            "to": "fact_port_weeks.review_id",
            "cardinality": "manyToOne",
            "crossFilteringBehavior": "oneDirection",
        }
        for t in ("fact_review_history", "fact_escalations")
    ]
    save(
        root,
        "reporting/model-contract.json",
        {
            "schema_version": "1.0",
            "endpoint": "/operations/reporting",
            "tables": tables,
            "relationships": relationships,
            "hamad_port_id": "port2026",
            "binding": "REQUIRES_REAL_SEMANTIC_MODEL",
            "queue_filter": "risk_level IN (HIGH, CRITICAL) applied on server",
        },
    )
    directory = Path(root) / "reporting"
    (directory / "OperationsSnapshot.pq").write_text(
        "let\n    Source = Json.Document(File.Contents(OperationsSnapshotPath))\nin\n    Source\n",
        encoding="utf-8",
    )
    for table, fields in tables.items():
        names = ", ".join(json.dumps(k) for k in fields)
        types = ", ".join("{" + json.dumps(k) + ", " + v + "}" for k, v in fields.items())
        query = (
            "let\n    Rows = OperationsSnapshot["
            + table
            + "],\n    Data = Table.FromRecords(Rows, {"
            + names
            + "}, MissingField.UseNull),\n    Typed = Table.TransformColumnTypes(Data, {"
            + types
            + "})\nin\n    Typed\n"
        )
        (directory / (table + ".pq")).write_text(query, encoding="utf-8")
    (directory / "operations-measures.dax").write_text(
        'Flagged Port Weeks = COUNTROWS(fact_review_queue)\nUnreviewed Flags = CALCULATE(COUNTROWS(fact_review_queue), fact_review_queue[review_status] = "UNREVIEWED")\nReview Actions = COUNTROWS(fact_review_history)\nUnresolved Escalation Exceptions = CALCULATE(COUNTROWS(fact_escalations), fact_escalations[unresolved_exception] = TRUE())\n',
        encoding="utf-8",
    )


def build(root="power-platform"):
    root = Path(root)
    schemas = {
        "SilverWeek": SilverWeek.model_json_schema(),
        "GoldWeek": GoldWeek.model_json_schema(),
        "ReviewAction": ReviewAction.model_json_schema(),
        "DeliveryResult": DeliveryResult.model_json_schema(),
    }
    for name, schema in schemas.items():
        save(root, "schemas/" + name + ".json", schema)
    queue = swagger_schema(schemas["GoldWeek"])
    queue["properties"].update(
        {
            "review_status": {"type": "string"},
            "review_version": {"type": "integer"},
            "owner": {"type": "string", "x-nullable": True},
            "risk_drivers_text": {"type": "string"},
        }
    )
    definitions = {name: swagger_schema(schema) for name, schema in schemas.items()}
    definitions["QueueItem"] = queue
    paths = {}

    def operation(path, method, operation_id, parameters, response):
        paths.setdefault(path, {})[method] = {
            "operationId": operation_id,
            "summary": operation_id,
            "parameters": parameters,
            "responses": {
                "200": {"description": "Success", "schema": response},
                "401": {"description": "Authentication required"},
                "403": {"description": "Role not authorized"},
                "409": {"description": "Conflicting review or delivery lease; refresh"},
                "422": {"description": "Invalid action or justification"},
                "503": {"description": "Approved data or dependency unavailable"},
            },
        }

    def collection(item):
        return {
            "type": "object",
            "properties": {"total": {"type": "integer"}, "items": {"type": "array", "items": item}},
        }

    operation(
        "/operations/queue",
        "get",
        "ListPortWeeks",
        [
            {"name": key, "in": "query", "required": False, "type": "string"}
            for key in (
                "port_id",
                "week_start",
                "risk_level",
                "review_status",
                "review_id",
                "country",
            )
        ]
        + [
            {"name": key, "in": "query", "required": False, "type": "integer"}
            for key in ("offset", "limit")
        ]
        + [{"name": "flagged_only", "in": "query", "required": False, "type": "boolean"}],
        collection({"$ref": "#/definitions/QueueItem"}),
    )
    operation(
        "/operations/reviews/{review_id}",
        "post",
        "SubmitReview",
        [
            {"name": "review_id", "in": "path", "required": True, "type": "string"},
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/ReviewAction"},
            },
        ],
        {"type": "object"},
    )
    history_schema = {
        "type": "object",
        "properties": {
            name: {"type": "string", "x-nullable": name == "previous_action"}
            for name in (
                "review_id",
                "action",
                "previous_action",
                "reason",
                "actor",
                "owner",
                "created_at",
            )
        },
    }
    operation(
        "/operations/history",
        "get",
        "ListHistory",
        [{"name": "review_id", "in": "query", "type": "string"}],
        collection(history_schema),
    )
    operation("/operations/events", "get", "ListEvents", [], collection({"type": "object"}))
    operation("/operations/events/claim", "post", "ClaimEvent", [], {"type": "object"})
    operation(
        "/operations/events/{event_id}/result",
        "post",
        "RecordDelivery",
        [
            {"name": "event_id", "in": "path", "required": True, "type": "string"},
            {
                "name": "body",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/DeliveryResult"},
            },
        ],
        {"type": "object"},
    )
    connector = {
        "swagger": "2.0",
        "info": {"title": "MaritimeOperations", "version": "1.0"},
        "host": "configure-api-host.example.invalid",
        "basePath": "/",
        "schemes": ["https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "securityDefinitions": {
            "entra": {
                "type": "oauth2",
                "flow": "accessCode",
                "authorizationUrl": "https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/authorize",
                "tokenUrl": "https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/token",
                "scopes": {
                    "api://API_APP_ID/access_as_user": "Access maritime operations as the signed-in user"
                },
            }
        },
        "security": [{"entra": ["api://API_APP_ID/access_as_user"]}],
        "definitions": definitions,
        "paths": paths,
    }
    save(root, "connector/openapi.json", connector)
    save(
        root,
        "connection-requirements.json",
        {
            "status": "TENANT_CONFIGURATION_REQUIRED",
            "api_host": connector["host"],
            "auth_mode": "entra",
            "roles": ["Maritime.Reader", "Maritime.Operator"],
            "identity_source": "Verified Entra oid; never client-supplied actor",
            "required": [
                "TENANT_ID",
                "API_APP_ID",
                "connector OAuth registration/secret in tenant",
                "API HTTPS endpoint",
                "durable MARITIME_WORKFLOW_DIR",
                "approved recipient list",
                "Office 365 Outlook connection",
                "Power BI semantic model/refresh identity",
            ],
            "limitations": [
                "Local shared keys are development identities, not named production users",
                "No tenant connection, deployment, notification or refresh has been executed",
            ],
        },
    )
    # JSON is valid YAML. This is control source, not a fabricated .msapp binary.
    refresh = (
        "=Set(varBusy,true); IfError(ClearCollect(colQueue,MaritimeOperations.ListPortWeeks("
        "{port_id:If(IsBlank(PortFilter.Text),Blank(),PortFilter.Text),"
        "week_start:If(IsBlank(WeekFilter.Text),Blank(),WeekFilter.Text),"
        'risk_level:If(RiskFilter.Selected.Value="ALL",Blank(),RiskFilter.Selected.Value),'
        'review_status:If(StatusFilter.Selected.Value="ALL",Blank(),StatusFilter.Selected.Value),'
        "offset:varOffset,limit:100,flagged_only:true}).items); Set(varUnavailable,false),"
        "Set(varUnavailable,true); Clear(colQueue)); Set(varBusy,false)"
    )
    controls = []

    def control(name, kind, properties, children=None):
        item = {"Control": kind, "Properties": properties}
        if children:
            item["Children"] = children
        return {name: item}

    controls.extend(
        [
            control(
                "Title",
                "Label",
                {
                    "Text": '="Maritime operations — weekly activity stress"',
                    "X": "=20",
                    "Y": "=10",
                    "Width": "=1300",
                    "Size": "=24",
                },
            ),
            control(
                "PortFilter",
                "Classic/TextInput",
                {
                    "Default": '=""',
                    "HintText": '="Port identifier (blank = portfolio; Hamad: port2026)"',
                    "X": "=20",
                    "Y": "=65",
                    "Width": "=410",
                },
            ),
            control(
                "WeekFilter",
                "Classic/TextInput",
                {
                    "Default": '=""',
                    "HintText": '="Week start YYYY-MM-DD (blank = all)"',
                    "X": "=450",
                    "Y": "=65",
                    "Width": "=330",
                },
            ),
            control(
                "RiskFilter",
                "Classic/DropDown",
                {
                    "Items": '=["ALL","HIGH","CRITICAL","ELEVATED","NORMAL","INCOMPLETE","INSUFFICIENT_HISTORY"]',
                    "Default": '="ALL"',
                    "X": "=800",
                    "Y": "=65",
                    "Width": "=240",
                },
            ),
            control(
                "StatusFilter",
                "Classic/DropDown",
                {
                    "Items": '=["ALL","UNREVIEWED","IGNORE","MONITOR","ESCALATE"]',
                    "Default": '="ALL"',
                    "X": "=1060",
                    "Y": "=65",
                    "Width": "=240",
                },
            ),
            control(
                "RefreshQueue",
                "Classic/Button",
                {
                    "Text": '="Refresh"',
                    "OnSelect": refresh,
                    "X": "=1320",
                    "Y": "=65",
                    "Width": "=180",
                },
            ),
            control(
                "State",
                "Label",
                {
                    "Text": '=If(varUnavailable,"Data unavailable — retry; no review can be saved",If(varBusy,"Loading…",If(IsEmpty(colQueue),"No matching weekly records","Select a record to review. Activity stress is not measured dwell time.")))',
                    "X": "=20",
                    "Y": "=120",
                    "Width": "=1480",
                },
            ),
            control(
                "PreviousPage",
                "Classic/Button",
                {
                    "Text": '="Previous"',
                    "OnSelect": "=Set(varOffset,Max(0,varOffset-100)); Select(RefreshQueue)",
                    "X": "=20",
                    "Y": "=800",
                },
            ),
            control(
                "NextPage",
                "Classic/Button",
                {
                    "Text": '="Next"',
                    "OnSelect": "=Set(varOffset,varOffset+100); Select(RefreshQueue)",
                    "X": "=220",
                    "Y": "=800",
                },
            ),
        ]
    )
    controls.append(
        control(
            "Queue",
            "Gallery",
            {
                "Items": "=colQueue",
                "X": "=20",
                "Y": "=170",
                "Width": "=760",
                "Height": "=600",
                "TemplateSize": "=110",
                "OnSelect": "=Set(varSelected,ThisItem); Set(varRequestId,Text(GUID())); Reset(Reason); IfError(ClearCollect(colHistory,MaritimeOperations.ListHistory({review_id:ThisItem.review_id}).items),Clear(colHistory))",
            },
            [
                control(
                    "QueueRow",
                    "Label",
                    {
                        "Text": '=ThisItem.port_name & " | " & ThisItem.week_start & " | " & ThisItem.risk_level & Char(10) & ThisItem.freshness_status & " | " & ThisItem.quality_status & " | " & ThisItem.review_status & If(ThisItem.simulated," | SIMULATED","")',
                        "Width": "=740",
                        "Height": "=100",
                        "OnSelect": "=Select(Parent)",
                    },
                )
            ],
        )
    )
    controls.extend(
        [
            control(
                "Evidence",
                "Label",
                {
                    "Text": '=If(IsBlank(varSelected),"Select a port-week",varSelected.port_name & " — " & varSelected.risk_level & Char(10) & "Weekly calls: " & Text(varSelected.weekly_calls) & " | Reference: " & Text(varSelected.reference_mean) & " | z: " & Text(varSelected.z_score) & Char(10) & Concat(varSelected.risk_drivers,Value,", ") & Char(10) & "Freshness: " & varSelected.freshness_status & " | Completeness: " & Text(varSelected.completeness,"0%") & Char(10) & "Source latest: " & varSelected.source_latest_observation & " | " & varSelected.methodology_version)',
                    "X": "=820",
                    "Y": "=170",
                    "Width": "=660",
                    "Height": "=170",
                },
            ),
            control(
                "Action",
                "Classic/DropDown",
                {
                    "Items": '=["MONITOR","ESCALATE","IGNORE"]',
                    "X": "=820",
                    "Y": "=350",
                    "Width": "=240",
                },
            ),
            control(
                "Reason",
                "Classic/TextInput",
                {
                    "Default": '=""',
                    "HintText": '="Reason required; ignoring HIGH/CRITICAL requires at least 40 characters"',
                    "Mode": "=TextMode.MultiLine",
                    "X": "=820",
                    "Y": "=410",
                    "Width": "=660",
                    "Height": "=110",
                },
            ),
            control(
                "SaveReview",
                "Classic/Button",
                {
                    "Text": '="Save decision"',
                    "DisplayMode": '=If(varBusy || varUnavailable || IsBlank(varSelected) || !varSelected.review_eligible || Len(Trim(Reason.Text)) < If(Action.Selected.Value="IGNORE",40,10),DisplayMode.Disabled,DisplayMode.Edit)',
                    "OnSelect": '=Set(varBusy,true); IfError(MaritimeOperations.SubmitReview(varSelected.review_id,{request_id:varRequestId,action:Action.Selected.Value,reason:Trim(Reason.Text),expected_version:varSelected.review_version,risk_revision:varSelected.risk_revision}); Notify("Decision recorded",NotificationType.Success); Set(varSelected,Blank()); Select(RefreshQueue),Notify("Save failed or record changed. Refresh before retrying.",NotificationType.Error)); Set(varBusy,false)',
                    "X": "=820",
                    "Y": "=540",
                    "Width": "=240",
                },
            ),
            control(
                "History",
                "Gallery",
                {
                    "Items": "=colHistory",
                    "X": "=820",
                    "Y": "=610",
                    "Width": "=660",
                    "Height": "=170",
                    "TemplateSize": "=80",
                },
                [
                    control(
                        "HistoryRow",
                        "Label",
                        {
                            "Text": '=ThisItem.action & " — " & ThisItem.reason & Char(10) & ThisItem.owner & " | " & ThisItem.created_at',
                            "Width": "=640",
                            "Height": "=80",
                        },
                    )
                ],
            ),
        ]
    )
    screen = {
        "Screens": {
            "OperationsReview": {
                "Properties": {
                    "OnVisible": "=Set(varOffset,0); Set(varBusy,false); Set(varUnavailable,false); Select(RefreshQueue)",
                    "Fill": "=RGBA(245,247,250,1)",
                },
                "Children": controls,
            }
        }
    }
    save(root, "canvas/OperationsReview.pa.yaml", screen)
    save(root, "canvas/Screen.properties.json", screen["Screens"]["OperationsReview"]["Properties"])
    save(root, "canvas/controls.fx.yaml", controls)
    save(
        root,
        "canvas/App.properties.json",
        {
            "StartScreen": "=OperationsReview",
            "MinScreenWidth": "=1600",
            "MinScreenHeight": "=900",
            "data_source_name": "MaritimeOperations",
            "import_note": "Create the screen and authenticated custom-connector data source in Studio; paste generated controls using code view. Set App.properties.json and Screen.properties.json formulas in Studio. No .msapp or deployed app is claimed.",
        },
    )
    claim_event = "body('Claim')?['event']"

    def api(path, body):
        return {
            "type": "ApiConnection",
            "inputs": {
                "host": {
                    "connection": {
                        "name": "@parameters('$connections')['maritimeoperations']['connectionId']"
                    }
                },
                "method": "post",
                "path": path,
                "body": body,
                "retryPolicy": {"type": "Fixed", "count": 3, "interval": "PT10S"},
            },
        }

    def ack(outcome, reason=None):
        return api(
            "@concat('/operations/events/'," + claim_event + "?['event_id'],'/result')",
            {
                "lease_token": "@" + claim_event + "?['lease_token']",
                "outcome": outcome,
                "failure_reason": reason,
            },
        )

    delivered, failed = ack("SENT"), ack("FAILED", "NOTIFICATION_CONNECTOR_FAILED")
    delivered["runAfter"] = {"Send": ["Succeeded"]}
    failed["runAfter"] = {"Send": ["Failed", "TimedOut"]}
    flow = {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {"$connections": {"type": "Object", "defaultValue": {}}},
        "triggers": {
            "PollGoldTransitions": {
                "type": "Recurrence",
                "recurrence": {"frequency": "Minute", "interval": 5},
                "runtimeConfiguration": {"concurrency": {"runs": 1}},
            }
        },
        "actions": {
            "Claim": api("/operations/events/claim", {}),
            "IfEvent": {
                "type": "If",
                "expression": "@not(equals(" + claim_event + ",null))",
                "runAfter": {"Claim": ["Succeeded"]},
                "actions": {
                    "HasRecipients": {
                        "type": "If",
                        "expression": "@greater(length(" + claim_event + "?['recipients']),0)",
                        "actions": {
                            "Send": {
                                "type": "ApiConnection",
                                "inputs": {
                                    "host": {
                                        "connection": {
                                            "name": "@parameters('$connections')['office365']['connectionId']"
                                        }
                                    },
                                    "method": "post",
                                    "path": "/v2/Mail",
                                    "body": {
                                        "To": "@join(" + claim_event + "?['recipients'],';')",
                                        "Subject": "@concat('Maritime ', "
                                        + claim_event
                                        + "?['risk_level'],' — ', "
                                        + claim_event
                                        + "?['port_name'],' — event ', "
                                        + claim_event
                                        + "?['event_id'])",
                                        "Body": "@concat('Week: ', "
                                        + claim_event
                                        + "?['week_start'], '<br>Drivers: ', join("
                                        + claim_event
                                        + "?['risk_drivers'], ', '), '<br>Source latest: ', "
                                        + claim_event
                                        + "?['source_latest_observation'], '<br>Freshness: ', "
                                        + claim_event
                                        + "?['freshness_status'], '<br>Review reference: ', "
                                        + claim_event
                                        + "?['review_reference'], '<br>Classification: ', "
                                        + claim_event
                                        + "?['classification'])",
                                    },
                                    "retryPolicy": {"type": "None"},
                                },
                            },
                            "RecordSuccess": delivered,
                            "RecordFailure": failed,
                        },
                        "else": {
                            "actions": {
                                "RecordException": ack("EXCEPTION", "RECIPIENTS_NOT_CONFIGURED")
                            }
                        },
                    }
                },
                "else": {"actions": {}},
            },
        },
        "outputs": {},
    }
    save(root, "automate/GoldRiskEscalation.definition.json", flow)
    save(
        root,
        "automate/connection-references.json",
        {
            "maritimeoperations": {
                "connectionId": "CONFIGURE_TENANT_CONNECTION",
                "api": "MaritimeOperations",
            },
            "office365": {
                "connectionId": "CONFIGURE_APPROVED_MAILBOX_CONNECTION",
                "api": "office365",
            },
            "status": "GENERATED_UNBOUND_NOT_DEPLOYED",
        },
    )
    reporting_assets(root)
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="power-platform")
    print(build(parser.parse_args().output))
