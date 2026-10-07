from collections import Counter
from datetime import date

from pydantic import ValidationError

from maritime.models import Activity, Port, Route


def validate(ports, activity, routes, as_of, freshness_days=10, reference=None):
    errors = []
    total = len(ports) + len(activity) + len(routes)
    valid = {}
    duplicates = 0
    missing = 0
    for name, rows, model, keys in [
        ("ports", ports, Port, ("port_id",)),
        ("activity", activity, Activity, ("port_id", "date")),
        ("routes", routes, Route, ("route_id",)),
    ]:
        valid[name] = []
        seen = set()
        for i, row in enumerate(rows):
            try:
                parsed = model.model_validate(row).model_dump(mode="json")
                key = tuple(parsed[k] for k in keys)
                if key in seen:
                    duplicates += 1
                    errors.append({"table": name, "row": i, "check": "uniqueness"})
                    continue
                seen.add(key)
                valid[name].append(parsed)
            except ValidationError as exc:
                missing += sum(e["type"] == "missing" for e in exc.errors())
                errors.append({"table": name, "row": i, "check": "schema", "details": str(exc)})
    ids = {p["port_id"] for p in valid["ports"]}
    orphan_count = 0
    for name, rows in valid.items():
        for row in rows:
            refs = (
                [row["port_id"]]
                if name == "activity"
                else ([row["origin"], row["destination"]] if name == "routes" else [])
            )
            if any(ref not in ids for ref in refs):
                orphan_count += 1
                errors.append({"table": name, "check": "referential_integrity", "record": row})
            if name == "activity" and row["date"] > as_of.isoformat():
                errors.append({"table": name, "check": "future_observation"})
            if name == "routes" and (
                row["origin"] == row["destination"]
                or (row["valid_to"] and row["valid_to"] < row["valid_from"])
            ):
                errors.append({"table": name, "check": "temporal_or_self_route"})
    latest = {
        p: max((r["date"] for r in valid["activity"] if r["port_id"] == p), default=None)
        for p in ids
    }
    stale = [
        p
        for p, day in latest.items()
        if day is None or (as_of - date.fromisoformat(day)).days > freshness_days
    ]
    for p in stale:
        errors.append({"table": "activity", "check": "freshness", "port_id": p})
    counts = Counter(r["port_id"] for r in valid["activity"])
    if not ports or not activity or not routes:
        errors.append({"check": "empty_critical_dataset"})
    reconciliation = "NOT_CONFIGURED"
    if reference is not None:
        codes = {r["unlocode"].replace(" ", "") for r in reference}
        unmatched = [
            p["port_id"]
            for p in ports
            if p.get("unlocode") and p["unlocode"].replace(" ", "") not in codes
        ]
        reconciliation = "FAIL" if unmatched else "PASS"
        errors.extend({"check": "cross_source_reconciliation", "port_id": p} for p in unmatched)
    rejected = sum(
        e["check"] in {"schema", "uniqueness", "referential_integrity", "future_observation"}
        for e in errors
    )
    report = {
        "status": "FAIL" if errors else "PASS",
        "records_processed": total,
        "records_rejected": rejected,
        "completeness_rate": max(0, 1 - missing / max(total, 1)),
        "duplicate_rate": duplicates / max(total, 1),
        "referential_integrity_rate": 1 - orphan_count / max(len(activity) + len(routes), 1),
        "freshness_status": "FAIL" if stale else "PASS",
        "schema_status": "FAIL" if any(e["check"] == "schema" for e in errors) else "PASS",
        "cross_source_reconciliation": reconciliation,
        "overall_dq_score": max(0, 1 - len(errors) / max(total, 1)),
        "latest_by_port": latest,
        "history_counts": dict(counts),
        "errors": errors,
    }
    return valid, report
