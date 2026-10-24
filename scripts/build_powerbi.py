"""Author five PBIR pages; bind only when a real semantic model ID is supplied."""

import argparse
import json
import uuid
from pathlib import Path

BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report/"
PAGES = [
    (
        "executive",
        "Control tower — activity proxy",
        "fact_congestion",
        "date",
        [
            "port_id",
            "category",
            "current_activity",
            "baseline",
            "stress_score",
            "evidence_coverage",
        ],
    ),
    (
        "congestion",
        "Congestion history — DERIVED activity proxy",
        "fact_congestion_history",
        "date",
        [
            "port_id",
            "date",
            "current_activity",
            "baseline",
            "deviation_fraction",
            "persistence_days",
            "category",
        ],
    ),
    (
        "network",
        "Network impact — assumptions, not observed cargo",
        "fact_exposure",
        "as_of",
        [
            "origin",
            "port_id",
            "depth",
            "arrival_hours",
            "exposure_score",
            "propagation_confidence",
            "confidence_type",
        ],
    ),
    (
        "sla",
        "SLA risk — SIMULATED, not shipment ML",
        "fact_sla_risk",
        "processed_at",
        [
            "shipment_id",
            "expected_delay_hours",
            "delay_p10",
            "delay_p90",
            "breach_probability",
            "expected_loss",
            "sla_buffer_hours",
        ],
    ),
    (
        "intervention",
        "Interventions — SIMULATED comparison, human decision",
        "fact_interventions",
        "processed_at",
        [
            "shipment_id",
            "action",
            "feasible",
            "expected_delay_hours",
            "breach_probability",
            "operational_cost",
            "expected_loss",
            "total_expected_cost",
            "explanation",
        ],
    ),
]

OPERATIONS_PAGES = [
    (
        "review_queue",
        "Operations review queue",
        "fact_review_queue",
        "week_start",
        [
            "port_name",
            "week_start",
            "risk_level",
            "freshness_status",
            "quality_status",
            "review_status",
            "owner",
        ],
    ),
    (
        "decision_history",
        "Operations decision history",
        "fact_review_history",
        "created_at",
        ["port_id", "week_start", "action", "previous_action", "reason", "owner", "created_at"],
    ),
    (
        "escalations",
        "Escalation delivery and exceptions",
        "fact_escalations",
        "created_at",
        [
            "port_name",
            "week_start",
            "risk_level",
            "delivery_status",
            "attempts",
            "last_attempt_at",
            "last_failure_reason",
            "unresolved_exception",
            "review_reference",
        ],
    ),
    (
        "hamad",
        "Qatar / Hamad Port",
        "fact_hamad_port_weeks",
        "week_start",
        [
            "port_name",
            "week_start",
            "weekly_calls",
            "reference_mean",
            "risk_level",
            "freshness_status",
            "completeness",
            "risk_drivers_text",
            "review_status",
        ],
    ),
    (
        "portfolio",
        "Portfolio weekly activity stress",
        "fact_port_weeks",
        "week_start",
        [
            "port_name",
            "country",
            "week_start",
            "weekly_calls",
            "reference_mean",
            "z_score",
            "risk_level",
            "quality_status",
        ],
    ),
]


def projection(table, field):
    return {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": field}},
        "queryRef": f"{table}.{field}",
    }


def build(output, semantic_model_id=None, include_operations=False):
    output = Path(output)
    pages = PAGES + OPERATIONS_PAGES if include_operations else PAGES

    def save(name, value):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    model = str(uuid.UUID(semantic_model_id)) if semantic_model_id else "REQUIRES_SEMANTIC_MODEL_ID"
    save(
        "definition.pbir" if semantic_model_id else "definition.pbir.template",
        {
            "$schema": BASE + "definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byConnection": {"connectionString": "semanticmodelid=" + model}},
        },
    )
    save(
        "definition/version.json",
        {"$schema": BASE + "definition/versionMetadata/1.0.0/schema.json", "version": "4.0.0"},
    )
    save(
        "definition/report.json",
        {"$schema": BASE + "definition/report/3.1.0/schema.json", "themeCollection": {}},
    )
    save(
        "definition/pages/pages.json",
        {
            "$schema": BASE + "definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": [p[0] for p in pages],
            "activePageName": "executive",
        },
    )
    for name, title, table, date_field, columns in pages:
        prefix = f"definition/pages/{name}"
        save(
            prefix + "/page.json",
            {
                "$schema": BASE + "definition/page/2.0.0/schema.json",
                "name": name,
                "displayName": title,
                "displayOption": "FitToPage",
                "width": 1600,
                "height": 900,
            },
        )
        for visual_name, kind, fields, x, y, width, height in [
            (
                "details",
                "tableEx",
                columns + ["classification", "lineage_id", "run_id"],
                20,
                180,
                1560,
                690,
            ),
            ("run_filter", "slicer", ["run_id"], 20, 20, 500, 140),
            ("time_filter", "slicer", [date_field], 550, 20, 500, 140),
            ("class_filter", "slicer", ["classification"], 1080, 20, 500, 140),
        ]:
            save(
                prefix + f"/visuals/{visual_name}/visual.json",
                {
                    "$schema": BASE + "definition/visualContainer/2.0.0/schema.json",
                    "name": visual_name,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": 0,
                        "width": width,
                        "height": height,
                        "tabOrder": y + x,
                    },
                    "visual": {
                        "visualType": kind,
                        "query": {
                            "queryState": {
                                "Values": {"projections": [projection(table, c) for c in fields]}
                            }
                        },
                        "drillFilterOtherVisuals": True,
                    },
                },
            )
    return output


def validate(output):
    import jsonschema
    from referencing import Registry, Resource

    folder = Path("configs/powerbi_schemas")
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    schemas = {url: json.loads((folder / file).read_bytes()) for url, file in index.items()}
    registry = Registry().with_resources(
        (url, Resource.from_contents(doc)) for url, doc in schemas.items()
    )
    count = 0
    for path in Path(output).rglob("*"):
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            schema = schemas[doc["$schema"]]
            jsonschema.validators.validator_for(schema)(schema, registry=registry).validate(doc)
            count += 1
    return {
        "status": "PASS_JSON_SCHEMA_ONLY",
        "files": count,
        "pages": len(
            json.loads((Path(output) / "definition/pages/pages.json").read_text())["pageOrder"]
        ),
        "runtime": "NOT_EXECUTED",
        "binding": "REQUIRES_REAL_SEMANTIC_MODEL",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="fabric/powerbi/Maritime.Report")
    parser.add_argument("--semantic-model-id")
    parser.add_argument("--operations", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(build(args.output, args.semantic_model_id, args.operations))))
