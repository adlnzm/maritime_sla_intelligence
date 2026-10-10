"""Collect repeatable acceptance evidence from tests, a real replay and HTTP requests."""

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from maritime.pipeline import load_json, run, write_json
from maritime.store import Store


def main():

    evidence = Path("evidence")

    evidence.mkdir(exist_ok=True)

    # A failure in any command fails validation; retain actual console output.

    commands = {
        "lint": [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        "format": [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        "tests": [sys.executable, "-m", "pytest", "-q", "--junitxml=evidence/tests.xml"],
    }

    checks = {}

    for name, command in commands.items():
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        (evidence / (name + ".log")).write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )

        checks[name] = {
            "exit_code": completed.returncode,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
        }

        if completed.returncode:
            raise RuntimeError(f"{name} failed; inspect evidence/{name}.log")

    report = run("data/acceptance", fixture="tests/data/portwatch_sample.json")

    store = Store("data/acceptance")

    # Build an actual historical stress case by truncating retained public data.

    stress = [r for r in store.read("congestion_history") if r["category"] in {"HIGH", "CRITICAL"}]

    if not stress:
        raise RuntimeError(
            "No historical observed stress state available for propagation acceptance"
        )

    day = max(r["date"] for r in stress)

    historical = load_json("tests/data/portwatch_sample.json")

    historical["as_of"] = day

    historical["activity"] = [r for r in historical["activity"] if r["date"] <= day]

    write_json("data/historical-replay.json", historical)

    historic_report = run("data/historical", fixture="data/historical-replay.json")

    if not historic_report["network"]["propagation_results"]:
        raise RuntimeError("Historical propagation acceptance failed")

    environment = {
        **os.environ,
        "MARITIME_DATA_DIR": "data/acceptance",
        "MARITIME_API_KEY": "validation-reader-only",
        "MARITIME_OPERATOR_KEY": "validation-operator-only",
        "PYTHONUTF8": "1",
    }

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "maritime.api:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "18080",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    http_checks = {}

    try:
        with httpx.Client(
            base_url="http://127.0.0.1:18080",
            timeout=5,
            headers={"X-API-Key": environment["MARITIME_API_KEY"]},
            trust_env=False,
        ) as client:
            for _ in range(60):
                try:
                    response = client.get("/ready")

                    response.raise_for_status()

                    break

                except httpx.TransportError:
                    if process.poll() is not None:
                        raise RuntimeError(process.stderr.read().decode())

                    time.sleep(0.25)

            else:
                raise TimeoutError("HTTP API startup timed out")

            for endpoint in (
                "/health",
                "/ready",
                "/ports",
                "/congestion",
                "/network",
                "/network/exposure",
                "/disruptions",
                "/scenarios",
                "/sla-risk",
                "/interventions",
                "/decisions",
                "/lineage",
                "/data-quality",
                "/metrics",
                "/signals",
            ):
                started = time.perf_counter()

                response = client.get(endpoint)

                response.raise_for_status()

                http_checks[endpoint] = {
                    "status_code": response.status_code,
                    "duration_seconds": time.perf_counter() - started,
                }

            assert client.get("/ports").json()["total"] == report["congestion"]["ports_evaluated"]

            decision = client.get("/decisions").json()["items"][0]

            reviewed = client.post(
                f"/decisions/{decision['decision_id']}/review",
                headers={"X-API-Key": environment["MARITIME_OPERATOR_KEY"]},
                json={
                    "status": "accept",
                    "reason": "Automated acceptance review of a simulated shipment",
                    "operator": "release-validation",
                },
            )

            reviewed.raise_for_status()

    finally:
        process.terminate()

        process.wait(timeout=10)

    suite = ET.parse(evidence / "tests.xml").getroot().find("testsuite")

    acceptance = {
        "status": "PASS_LOCAL_ACCEPTANCE",
        "checks": checks,
        "tests": dict(suite.attrib),
        "run_id": report["run_id"],
        "http": http_checks,
        "historical_propagation": {"as_of": day, **historic_report["network"]},
        "gates": {
            "1_data_foundation": "VALIDATED",
            "2_data_platform": "VALIDATED",
            "3_congestion": "VALIDATED",
            "4_network": "VALIDATED_WITH_REFERENCE_OR_SIMULATED_TOPOLOGY",
            "5_scenario": "VALIDATED_SIMULATED",
            "6_counterfactual": "VALIDATED_SIMULATED",
            "7_sla": "VALIDATED_SIMULATED",
            "8_ml": "VALIDATED_PORT_CALL_FORECAST_ONLY",
            "9_decision": "VALIDATED_SIMULATED_AND_OPERATOR_AUDIT",
            "10_api_bi": "HTTP_AND_MARTS_VALIDATED_POWER_BI_TENANT_UNVALIDATED",
            "11_reliability": "REGRESSION_TESTS_VALIDATED",
            "12_e2e": "LOCAL_EXECUTION_VALIDATED_FABRIC_ENVIRONMENT_DEPENDENT",
        },
        "fabric": "ENVIRONMENT_DEPENDENT_NO_WORKSPACE_ID",
        "docker": load_json(evidence / "docker.json")
        if (evidence / "docker.json").exists()
        else "NOT_EXECUTED",
        "azure_ml": "IMPLEMENTED_ENVIRONMENT_DEPENDENT_NOT_EXECUTED",
        "azure_application": "IMPLEMENTED_ENVIRONMENT_DEPENDENT_NOT_DEPLOYED",
        "genai_provider": "ENVIRONMENT_DEPENDENT_NOT_CONFIGURED",
        "sla_ml": "DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA",
    }

    write_json(evidence / "acceptance.json", acceptance)

    write_json(evidence / "replay-report.json", report)

    write_json(evidence / "historical-report.json", historic_report)

    live = Store("data").latest_report()

    if live and live["status"] == "SUCCESS":
        # Avoid publishing machine-specific absolute paths in public execution evidence.

        for event in live["source_status"]:
            event.pop("raw_path", None)

        write_json(evidence / "live-report.json", live)

    print(
        json.dumps(
            {
                "status": acceptance["status"],
                "tests": suite.attrib["tests"],
                "http_endpoints": len(http_checks),
                "run_id": report["run_id"],
            }
        )
    )


if __name__ == "__main__":
    main()
