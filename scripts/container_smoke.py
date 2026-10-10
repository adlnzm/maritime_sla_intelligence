"""Run pipeline plus a real HTTP server in the container; save measured evidence."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from maritime.pipeline import run

report = run("/app/data", fixture="/app/samples/portwatch_sample.json")
os.environ["MARITIME_API_KEY"] = "container-validation-only"
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
        "8080",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
)
try:
    client = httpx.Client(
        base_url="http://127.0.0.1:8080",
        headers={"X-API-Key": os.environ["MARITIME_API_KEY"]},
        timeout=5,
    )
    for _ in range(40):
        try:
            response = client.get("/ready")
            response.raise_for_status()
            break
        except httpx.TransportError:
            time.sleep(0.25)
    else:
        raise RuntimeError("API failed to start")
    statuses = {}
    for endpoint in (
        "/health",
        "/ready",
        "/ports",
        "/congestion",
        "/network/exposure",
        "/scenarios",
        "/sla-risk",
        "/interventions",
        "/decisions",
        "/lineage",
        "/data-quality",
        "/metrics",
    ):
        response = client.get(endpoint)
        response.raise_for_status()
        statuses[endpoint] = response.status_code
    assert client.get("/scenarios").json()["total"] == report["scenarios"]["shipments"]
    evidence = {
        "status": "PASS",
        "run_id": report["run_id"],
        "http_checks": statuses,
        "environment": "docker",
    }
    Path("/app/data/container-evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))
finally:
    process.terminate()
    process.wait(timeout=10)
