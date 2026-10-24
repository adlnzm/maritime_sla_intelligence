"""Clean local evidence campaign. Industrial release remains blocked without external controls."""

import argparse
import copy
import json
import shutil
import time
from datetime import date
from pathlib import Path
from unittest.mock import patch

from maritime.governance import contract, fingerprint, verify_manifest
from maritime.models import Activity, Port
from maritime.pipeline import run, write_json
from maritime.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--fixture")
    args = parser.parse_args()
    root, output = Path(args.root), Path(args.output)
    if root.exists() or output.exists():
        raise ValueError("Clean campaign requires new data and evidence directories")
    output.mkdir(parents=True)
    policy = {
        "version": "1.0",
        "successful_runs_required": 3,
        "injected_failures_required": 2,
        "maximum_reconciliation_discrepancies": 0,
        "maximum_duplicate_publications": 0,
        "maximum_data_loss_incidents": 0,
        "failed_run_pointer_changes_allowed": 0,
        "latency_slo": "REQUIRES_OWNER_AGREEMENT",
        "production_reliability_claim": "NOT_ESTABLISHED_BY_BOUNDED_LOCAL_CAMPAIGN",
    }
    write_json(output / "predeclared-campaign-policy.json", policy)
    attempts = []
    started = time.perf_counter()
    try:
        first = run(root, as_of=args.as_of, fixture=args.fixture)
        store = Store(root)
        attempts.append(
            {
                "run_id": first["run_id"],
                "outcome": "PASS",
                "mode": first["execution_mode"],
                "duration_seconds": first["duration_seconds"],
            }
        )
        bundle = {"as_of": first["as_of"], "source_status": first["source_status"]}
        for name, model in (("ports", Port), ("activity", Activity)):
            bundle[name] = [
                {k: v for k, v in r.items() if k in model.model_fields}
                for r in store.read_approved(name)
            ]
        replay = root / "campaign-replay.json"
        write_json(replay, bundle)
        repeat = run(root, fixture=replay)
        attempts.append(
            {
                "run_id": repeat["run_id"],
                "outcome": "PASS",
                "mode": "REPLAY",
                "duration_seconds": repeat["duration_seconds"],
            }
        )
        previous = store.metadata("published_run")
        bad = copy.deepcopy(bundle)
        bad["fault_injection"] = "INVALID_COORDINATE_TEST_ONLY_NOT_SOURCE_OBSERVATION"
        for name in ("ports", "activity"):
            for row in bad[name]:
                row.update(classification="SIMULATED", source_id="failure-injection")
        bad["ports"][0]["latitude"] = 1000
        write_json(root / "injected-invalid.json", bad)
        try:
            run(root, fixture=root / "injected-invalid.json")
        except ValueError:
            failed = store.latest_report()
            attempts.append(
                {
                    "run_id": failed["run_id"],
                    "outcome": "EXPECTED_BLOCK",
                    "injection": "invalid_coordinate",
                    "pointer_preserved": store.metadata("published_run") == previous,
                    "duration_seconds": failed["duration_seconds"],
                }
            )
        else:
            raise AssertionError("Invalid data unexpectedly published")
        original = Store.write

        def partial(self, run_id, product, records):
            original(self, run_id, product, records[:-1] if product == "decisions" else records)

        with patch.object(Store, "write", partial):
            try:
                run(root, fixture=replay)
            except ValueError:
                failed = store.latest_report()
                attempts.append(
                    {
                        "run_id": failed["run_id"],
                        "outcome": "EXPECTED_BLOCK",
                        "injection": "partial_persistence",
                        "pointer_preserved": store.metadata("published_run") == previous,
                        "duration_seconds": failed["duration_seconds"],
                    }
                )
            else:
                raise AssertionError("Partial persistence unexpectedly published")
        recovered = run(root, fixture=replay)
        attempts.append(
            {
                "run_id": recovered["run_id"],
                "outcome": "PASS",
                "mode": "RECOVERY_REPLAY",
                "duration_seconds": recovered["duration_seconds"],
            }
        )
        # Deliver the first actual live snapshot. Replay outcomes demonstrate recovery separately.
        manifest = store.release(first["run_id"])
        products = {n: store.read_approved(n, first["run_id"]) for n in manifest["datasets"]}
        verify_manifest(products, manifest)
        checks = {
            "successful_runs": sum(a["outcome"] == "PASS" for a in attempts) == 3,
            "expected_failures": sum(a["outcome"] == "EXPECTED_BLOCK" for a in attempts) == 2,
            "prior_snapshot_preserved": all(a.get("pointer_preserved", True) for a in attempts),
            "accounting": all(
                store.read("data_quality", a["run_id"])[0]["accounting"]["balanced"]
                for a in attempts
            ),
            "audit_chain": store.verify_audit()["status"] == "PASS",
            "independent_metrics": all(r["passed"] for r in first["independent_metrics"]),
        }
        if not all(checks.values()):
            raise AssertionError(f"Campaign failed: {checks}")
        for name, rows in products.items():
            if name in {"lineage", "data_quality", "sources"}:
                write_json(output / "metadata" / (name + ".json"), rows)
                continue
            for group, classes in (
                ("operational", {"OBSERVED", "DERIVED"}),
                ("simulated", {"SIMULATED"}),
                ("predicted", {"PREDICTED"}),
                ("anticipated", {"ANTICIPATED"}),
            ):
                selected = [r for r in rows if r["classification"] in classes]
                if selected:
                    write_json(output / "datasets" / group / (name + ".json"), selected)
        write_json(output / "release-manifest.json", manifest)
        write_json(output / "contract.json", contract())
        write_json(
            output / "source-to-output-lineage.json",
            {
                "bronze": first["bronze_manifest"],
                "source_acquisitions": first["source_status"],
                "release": manifest,
                "field_lineage": products["lineage"],
            },
        )
        write_json(
            output / "reconciliation.json",
            {
                "canonical": first["data_quality"]["accounting"],
                "products": first["product_verification"]["reconciliation"],
                "independent_metrics": first["independent_metrics"],
            },
        )
        shutil.copytree(root / "reports", output / "runs")
        shutil.copytree(root / "quarantine", output / "quarantine")
        shutil.copytree(root / "bronze", output / "bronze")
        external = first["governance"]["industrial_release"]["unevaluated_mandatory_controls"]
        report = {
            "status": "BLOCKED",
            "scope": "INDUSTRIAL_OPERATIONAL_RELEASE",
            "local_analytical_status": manifest["status"],
            "live_acquisition": first["execution_mode"],
            "release_id": manifest["release_id"],
            "run_id": first["run_id"],
            "code": manifest["code"],
            "mandatory_failed_controls": [],
            "mandatory_unevaluated_controls": [
                {"control": n, "status": "NOT_EVALUATED"} for n in external
            ],
            "campaign": {
                "status": "PASS",
                "checks": checks,
                "attempts": attempts,
                "elapsed_seconds": time.perf_counter() - started,
                "sustained_production_reliability": "NOT_ESTABLISHED",
            },
            "dataset_label": "LOCAL_ANALYTICAL_EVIDENCE_NOT_INDUSTRIALLY_VALIDATED",
            "sla_ml": "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA",
        }
        write_json(output / "release-validation.json", report)
        files = {
            str(p.relative_to(output)).replace("\\", "/"): __import__("hashlib")
            .sha256(p.read_bytes())
            .hexdigest()
            for p in output.rglob("*")
            if p.is_file()
        }
        write_json(output / "evidence-checksums.json", files)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "local_campaign": "PASS",
                    "release_id": manifest["release_id"],
                    "output": str(output),
                    "checksums": fingerprint(files),
                }
            )
        )
    except Exception as exc:
        # Failed acquisition/DQ is release evidence too, not merely a traceback.
        for folder in ("reports", "quarantine", "bronze"):
            if (root / folder).exists():
                shutil.copytree(root / folder, output / ("failed-" + folder), dirs_exist_ok=True)
        write_json(
            output / "release-validation.json",
            {
                "status": "BLOCKED",
                "mandatory_failed_controls": [
                    {"control": "local_campaign", "reason": str(exc), "type": type(exc).__name__}
                ],
                "attempts": attempts,
            },
        )
        raise


if __name__ == "__main__":
    main()
