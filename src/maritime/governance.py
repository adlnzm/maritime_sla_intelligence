"""Stage gates and content manifests. Local verification never certifies a cloud runtime."""

import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import time
from contextlib import contextmanager
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

from maritime.models import json_default, utcnow


class GovernanceError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=json_default, allow_nan=False).encode()
    ).hexdigest()


def contract(path="configs/governance.json"):
    selected = Path(path)
    if not selected.exists() and path == "configs/governance.json":
        selected = Path(__file__).with_name("governance_contract.json")
    value = json.loads(selected.read_text(encoding="utf-8"))
    if value.get("version") != "1.0" or any(
        d.get("version") != "1.0" for d in value["datasets"].values()
    ):
        raise GovernanceError("Unknown governance contract version")
    return value


def code_identity():
    files = {}
    for folder in ("src", "configs", "scripts"):
        for p in sorted(Path(folder).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files[p.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "src",
                    "configs",
                    "scripts",
                    "pyproject.toml",
                    "uv.lock",
                    "docker",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except (OSError, subprocess.SubprocessError):
        commit, dirty = os.getenv("BUILD_COMMIT", "UNAVAILABLE"), None
    return {
        "git_commit": commit,
        "working_tree_dirty": dirty,
        "code_fingerprint": fingerprint(files),
        "python": platform.python_version(),
        "dependencies": {p: version(p) for p in ("numpy", "pandas", "scikit-learn", "pydantic")},
    }


@contextmanager
def exclusive_run(root):
    """OS lock is released on process exit; no guessed PID/TTL can steal a live run."""
    path = Path(root) / ".pipeline.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise GovernanceError("Overlapping pipeline execution blocked") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Gates:
    def __init__(self, store, report, config):
        self.store, self.report, self.config = store, report, config
        self.policy = contract()
        for name in ("freshness_days", "baseline_days", "min_history"):
            if config[name] != self.policy[name]:
                raise GovernanceError(
                    f"Configuration incompatible with governance contract: {name}"
                )
        self.started = {}
        self.report["governance"] = {
            "contract_version": self.policy["version"],
            "contract_fingerprint": fingerprint(self.policy),
            "configuration_fingerprint": fingerprint(config),
            "code": code_identity(),
            "status": "NOT_EVALUATED",
            "scope": "LOCAL_ANALYTICAL",
            "stages": {s: {"status": "NOT_EVALUATED"} for s in self.policy["stages"]},
            "industrial_release": {
                "status": "BLOCKED",
                "unevaluated_mandatory_controls": self.policy[
                    "industrial_mandatory_external_controls"
                ],
            },
        }

    def start(self, stage):
        stages = self.report["governance"]["stages"]
        index = self.policy["stages"].index(stage)
        if any(
            stages[s]["status"] not in self.policy["allowed_release_states"]
            for s in self.policy["stages"][:index]
        ):
            raise GovernanceError(f"Dependency gate not approved: {stage}")
        self.started[stage] = time.perf_counter()
        stages[stage] = {
            "status": "NOT_EVALUATED",
            "execution_id": fingerprint([self.report["run_id"], stage])[:24],
            "started_at": utcnow(),
            "attempt": 1,
        }
        self.store.audit(
            "stage", {"run_id": self.report["run_id"], "stage": stage, "transition": "STARTED"}
        )

    def finish(self, stage, checks, counts=None, warnings=()):
        failed = [k for k, passed in checks.items() if passed is not True]
        unauthorized = set(warnings) - set(self.policy["permitted_warnings"])
        failed.extend(sorted(unauthorized))
        status = "BLOCKED" if failed else "PASS_WITH_WARNINGS" if warnings else "PASS"
        value = self.report["governance"]["stages"][stage]
        value.update(
            status=status,
            checks=checks,
            failed_rules=failed,
            warnings=list(warnings),
            counts=counts or {},
            completed_at=utcnow(),
            duration_seconds=time.perf_counter() - self.started[stage],
        )
        self.store.audit("stage", {"run_id": self.report["run_id"], "stage": stage, **value})
        if failed:
            raise GovernanceError(f"Stage {stage} BLOCKED: {failed}")

    def fail(self, error):
        governance = self.report["governance"]
        governance["status"] = "BLOCKED"
        for name in self.started:
            if governance["stages"][name]["status"] == "NOT_EVALUATED":
                value = governance["stages"][name]
                value.update(
                    status="BLOCKED",
                    failed_rules=["execution_completed"],
                    failure_type=type(error).__name__,
                    completed_at=utcnow(),
                    duration_seconds=time.perf_counter() - self.started[name],
                )
                self.store.audit("stage", {"run_id": self.report["run_id"], "stage": name, **value})


def verify_current_metrics(activity, states, config):
    results = []
    for state in states:
        day = date.fromisoformat(state["date"])
        prior = [
            r["vessel_calls"]
            for r in activity
            if r["port_id"] == state["port_id"]
            and (day - timedelta(days=config["baseline_days"])).isoformat()
            <= r["date"]
            < state["date"]
        ]
        if len(prior) < config["min_history"]:
            results.append(
                {"port_id": state["port_id"], "passed": False, "reason": "insufficient_history"}
            )
            continue
        current = next(
            r["vessel_calls"]
            for r in activity
            if r["port_id"] == state["port_id"] and r["date"] == state["date"]
        )
        mean, std = statistics.mean(prior), statistics.pstdev(prior)
        z = (current - mean) / max(1, std)
        category = (
            "CRITICAL"
            if abs(z) >= 3
            else "HIGH"
            if abs(z) >= 2
            else "ELEVATED"
            if abs(z) >= 1
            else "NORMAL"
        )
        passed = (
            math.isclose(state["baseline"], mean, rel_tol=1e-10, abs_tol=1e-10)
            and math.isclose(state["z_score"], z, rel_tol=1e-9, abs_tol=1e-9)
            and state["category"] == category
        )
        results.append(
            {
                "port_id": state["port_id"],
                "date": state["date"],
                "independent_baseline": mean,
                "independent_z_score": z,
                "passed": passed,
            }
        )
    return results


def enrich(products, report, config):
    policy = contract()
    for name, rows in products.items():
        if name not in policy["datasets"]:
            raise GovernanceError(f"Unknown dataset contract: {name}")
        spec = policy["datasets"][name]
        input_manifest = {d: fingerprint(products[d]) for d in spec["dependencies"]}
        components = sorted(
            {r["classification"] for d in spec["dependencies"] for r in products[d]}
        )
        for row in rows:
            if name == "sources":
                row["source_classification"] = row["classification"]
                row["classification"] = "DERIVED"
            row.setdefault("classification", "DERIVED")
            row.setdefault("lineage_id", fingerprint([name, row, input_manifest]))
            row.update(
                run_id=report["run_id"],
                contract_version="1.0",
                processed_at=report["start_time"],
                configuration_fingerprint=fingerprint(config),
            )
            row["component_classifications"] = components
            row["input_fingerprints"] = input_manifest
            row["degraded_sources"] = report.get("degraded_sources", [])
            row["execution_mode"] = report["execution_mode"]


def verify_products(products, config, as_of):
    """Independent scalar metric checks, contracts, keys and relationships before persistence."""
    policy = contract()
    errors, reconciliations = [], {}
    mandatory = {n for n in policy["datasets"] if not n.startswith("reference_")}
    errors.extend("missing_dataset:" + n for n in sorted(mandatory - products.keys()))
    for name, rows in products.items():
        spec = policy["datasets"].get(name)
        if spec is None:
            errors.append("unknown_dataset:" + name)
            continue
        seen = set()
        if not rows and not spec["empty_allowed"]:
            errors.append("empty:" + name)
        for i, row in enumerate(rows):
            for field, value in row.items():
                kind = (
                    "null"
                    if value is None
                    else "boolean"
                    if isinstance(value, bool)
                    else "number"
                    if isinstance(value, (int, float))
                    else "string"
                    if isinstance(value, str)
                    else "array"
                    if isinstance(value, list)
                    else "object"
                )
                if field not in spec["field_types"] or kind not in spec["field_types"][field]:
                    errors.append(f"field_schema:{name}:{i}:{field}")
            for field in (
                "stress_score",
                "exposure_score",
                "breach_probability",
                "evidence_coverage",
            ):
                if row.get(field) is not None and not 0 <= row[field] <= 1:
                    errors.append(f"range:{name}:{i}:{field}")
            for field in (
                "vessel_calls",
                "expected_loss",
                "expected_delay_hours",
                "operational_cost",
                "transit_hours",
                "distance_nm",
            ):
                if row.get(field) is not None and row[field] < 0:
                    errors.append(f"range:{name}:{i}:{field}")
            if any(k not in row or row[k] is None for k in spec["required_fields"]):
                errors.append(f"required:{name}:{i}")
                continue
            key = fingerprint([row[k] for k in spec["keys"]])
            if key in seen:
                errors.append(f"duplicate:{name}:{i}")
            seen.add(key)
            if row["classification"] not in spec["classifications"]:
                errors.append(f"classification:{name}:{i}")
            if row["contract_version"] != "1.0" or row["configuration_fingerprint"] != fingerprint(
                config
            ):
                errors.append(f"contract:{name}:{i}")
            if (
                name not in {"lineage", "sources", "data_quality", "dim_time"}
                and "SIMULATED" in row.get("component_classifications", [])
                and row["classification"] not in {"SIMULATED"}
            ):
                errors.append(f"mixed_classification:{name}:{i}")
            fingerprint(row)  # Nonfinite values fail JSON serialization.
        reconciliations[name] = {
            "input": len(rows),
            "persisted_expected": len(rows),
            "invalid": 0 if not errors else None,
        }
    ports = {p["port_id"] for p in products.get("ports", [])}
    activity = products.get("activity", [])
    for r in activity:
        if r["port_id"] not in ports or r["date"] > as_of.isoformat():
            errors.append("activity_reference_or_time")
    by_port = {
        p: sorted([r for r in activity if r["port_id"] == p], key=lambda r: r["date"])
        for p in ports
    }
    comparisons = []
    for state in products.get("congestion", []):
        day = date.fromisoformat(state["date"])
        prior = [
            r["vessel_calls"]
            for r in by_port[state["port_id"]]
            if (day - timedelta(days=config["baseline_days"])).isoformat()
            <= r["date"]
            < state["date"]
        ]
        if len(prior) < config["min_history"]:
            errors.append("insufficient_metric_history")
            continue
        current = next(
            r["vessel_calls"] for r in by_port[state["port_id"]] if r["date"] == state["date"]
        )
        mean, std = statistics.mean(prior), statistics.pstdev(prior)
        z = (current - mean) / max(1, std)
        category = (
            "CRITICAL"
            if abs(z) >= 3
            else "HIGH"
            if abs(z) >= 2
            else "ELEVATED"
            if abs(z) >= 1
            else "NORMAL"
        )
        passed = (
            math.isclose(state["baseline"], mean, rel_tol=1e-10, abs_tol=1e-10)
            and math.isclose(state["z_score"], z, rel_tol=1e-9, abs_tol=1e-9)
            and state["category"] == category
        )
        comparisons.append(
            {
                "port_id": state["port_id"],
                "date": state["date"],
                "independent_baseline": mean,
                "independent_z_score": z,
                "published_baseline": state["baseline"],
                "passed": passed,
            }
        )
        if not passed:
            errors.append("independent_metric_mismatch")
    shipments = {r["shipment_id"]: r for r in products.get("scenarios", [])}
    outcomes = products.get("interventions", [])
    for o in outcomes:
        if o["shipment_id"] not in shipments:
            errors.append("scenario_fk")
        if o["feasible"]:
            expected = (
                o["breach_probability"]
                * o["cargo_exposure"]
                * config["scenario_assumptions"]["late_penalty_fraction"]
                * o["priority"]
            )
            if (
                not 0 <= o["breach_probability"] <= 1
                or not math.isclose(expected, o["expected_loss"], rel_tol=1e-10, abs_tol=1e-8)
                or not math.isclose(
                    o["total_expected_cost"], expected + o["operational_cost"], abs_tol=1e-8
                )
            ):
                errors.append("scenario_expected_loss_formula")
    for d in products.get("decisions", []):
        choices = sorted(
            [o for o in outcomes if o["shipment_id"] == d["shipment_id"] and o["feasible"]],
            key=lambda o: (o["total_expected_cost"], o["action"]),
        )
        if not choices or d["scenario_id"] != choices[0]["scenario_id"]:
            errors.append("decision_ranking")
    if len(outcomes) != len(shipments) * 5 or len(products.get("decisions", [])) != len(shipments):
        errors.append("scenario_accounting")
    return {
        "status": "BLOCKED" if errors else "PASS",
        "errors": errors,
        "independent_metrics": comparisons,
        "reconciliation": reconciliations,
    }


def release_manifest(products, report):
    governance = report["governance"]
    required = contract()["stages"][:-1]
    if any(
        governance["stages"][s]["status"] not in contract()["allowed_release_states"]
        for s in required
    ):
        raise GovernanceError("Mandatory stage missing or not accepted")
    return {
        "contract_version": "1.0",
        "run_id": report["run_id"],
        "release_id": fingerprint([report["run_id"], products]),
        "status": "PASS_WITH_WARNINGS"
        if any(s["status"] == "PASS_WITH_WARNINGS" for s in governance["stages"].values())
        else "PASS",
        "scope": "LOCAL_ANALYTICAL",
        "execution_mode": report["execution_mode"],
        "as_of": report["as_of"],
        "approved_at": utcnow(),
        "code": governance["code"],
        "contract_fingerprint": governance["contract_fingerprint"],
        "stage_evidence": {s: governance["stages"][s] for s in required},
        "configuration_fingerprint": governance["configuration_fingerprint"],
        "datasets": {
            name: {
                "rows": len(rows),
                "sha256": fingerprint(rows),
                "classifications": sorted({r["classification"] for r in rows}),
            }
            for name, rows in products.items()
        },
        "industrial_release": governance["industrial_release"],
    }


def verify_manifest(products, manifest):
    if (
        manifest.get("contract_version") != "1.0"
        or manifest.get("status") not in contract()["allowed_release_states"]
    ):
        raise GovernanceError("Release is not approved by the current contract")
    policy = contract()
    if manifest.get("contract_fingerprint") != fingerprint(policy):
        raise GovernanceError("Release contract fingerprint mismatch")
    stages = manifest.get("stage_evidence", {})
    for name in policy["stages"][:-1]:
        stage = stages.get(name, {})
        if (
            stage.get("status") not in policy["allowed_release_states"]
            or not stage.get("checks")
            or not all(v is True for v in stage["checks"].values())
        ):
            raise GovernanceError(f"Missing or failed mandatory release stage: {name}")
    if set(products) != set(manifest["datasets"]):
        raise GovernanceError("Release dataset set mismatch")
    for name, rows in products.items():
        expected = manifest["datasets"][name]
        if (
            len(rows) != expected["rows"]
            or fingerprint(rows) != expected["sha256"]
            or any(r["run_id"] != manifest["run_id"] for r in rows)
        ):
            raise GovernanceError(f"Release content mismatch: {name}")
