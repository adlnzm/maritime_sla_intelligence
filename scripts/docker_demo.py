"""Validate a fresh Compose volume, real HTTP workflow, and persistent restart.

Retains the stopped containers and volume for investigation; never deletes user data.
"""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/ready-to-run")
    args = parser.parse_args()
    project = "maritime-demo-" + uuid.uuid4().hex[:10]
    output = Path(args.output) / project
    output.mkdir(parents=True, exist_ok=False)
    environment = {
        **os.environ,
        "MARITIME_API_KEY": secrets.token_hex(32),
        "MARITIME_OPERATOR_KEY": secrets.token_hex(32),
    }
    prefix = ["docker", "compose", "-f", "compose.demo.yml", "-p", project]
    evidence = {
        "status": "FAIL",
        "project": project,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "RETAINED_PUBLIC_DATA_REPLAY_WITH_SIMULATED_SHIPMENTS",
        "cloud": "NOT_EXECUTED",
        "commands": [],
        "checks": {},
    }

    def command(args, required=True, engine=False):
        started = time.perf_counter()
        invocation = (["docker"] if engine else prefix) + args
        result = subprocess.run(invocation, env=environment, capture_output=True, timeout=900)
        index = len(evidence["commands"])
        (output / f"command-{index}.log").write_bytes(result.stdout + result.stderr)
        evidence["commands"].append(
            {
                "command": invocation,
                "exit_code": result.returncode,
                "duration_seconds": time.perf_counter() - started,
            }
        )
        if required:
            result.check_returncode()
        return result

    try:
        command(["build", "--no-cache", "--pull"])
        command(["up", "-d", "--wait", "--wait-timeout", "300"])
        state = command(["ps", "--format", "json"])
        (output / "service-state.json").write_bytes(state.stdout)
        security = command(
            [
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import os; print(os.getuid()); print(open('/proc/self/status').read())",
            ]
        )
        assert security.stdout.decode().splitlines()[0] == "10001"
        assert "CapEff:\t0000000000000000" in security.stdout.decode()
        assert "NoNewPrivs:\t1" in security.stdout.decode()
        container_id = command(["ps", "-q", "api"]).stdout.decode().strip()
        controls = (
            command(
                [
                    "inspect",
                    "--format",
                    "{{json .HostConfig.Memory}} {{json .HostConfig.NanoCpus}} "
                    "{{json .HostConfig.PidsLimit}} {{json .HostConfig.ReadonlyRootfs}}",
                    container_id,
                ],
                engine=True,
            )
            .stdout.decode()
            .strip()
        )
        assert controls == "1073741824 1000000000 128 true", controls
        evidence["checks"]["runtime_security"] = "PASS_UID_CAPABILITIES_LIMITS_READONLY"
        port = environment.get("MARITIME_DEMO_PORT", "18081")
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=15, trust_env=False
        ) as client:
            reader = {"X-API-Key": environment["MARITIME_API_KEY"]}
            operator = {"X-API-Key": environment["MARITIME_OPERATOR_KEY"]}

            def check(name, method, path, expected=200, **kwargs):
                response = client.request(method, path, **kwargs)
                assert response.status_code == expected, (name, response.status_code, response.text)
                assert len(response.headers["X-Correlation-ID"]) == 32
                evidence["checks"][name] = response.status_code
                return response

            check("unauthenticated", "GET", "/ports", 401)
            for path in (
                "ready",
                "ports",
                "congestion",
                "network/exposure",
                "scenarios",
                "sla-risk",
                "interventions",
                "decisions",
                "lineage",
                "data-quality",
                "predictions",
                "metrics",
                "signals",
                "run-report",
            ):
                response = check(path, "GET", "/" + path, headers=reader)
                (output / (path.replace("/", "-") + ".json")).write_text(
                    response.text, encoding="utf-8"
                )
            run_id = client.get("/ready", headers=reader).json()["run_id"]
            # Remove the actual required database briefly in this disposable volume.
            command(
                [
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-c",
                    "import os; os.rename('/app/data/maritime.db','/app/data/maritime.db.unavailable')",
                ]
            )
            try:
                check("dependency_unavailable", "GET", "/health/ready", 503)
                check("liveness_during_outage", "GET", "/health")
            finally:
                command(
                    [
                        "exec",
                        "-T",
                        "api",
                        "python",
                        "-c",
                        "import os; os.replace('/app/data/maritime.db.unavailable','/app/data/maritime.db')",
                    ]
                )
            check("dependency_recovered", "GET", "/ready", headers=reader)
            decision = client.get("/decisions", headers=reader).json()["items"][0]
            path = f"/decisions/{decision['decision_id']}/review"
            review = {
                "status": "accept",
                "reason": "Demo simulated decision review",
                "operator": "demo-validation",
            }
            check("reader_cannot_write", "POST", path, 403, headers=reader, json=review)
            check("review", "POST", path, headers=operator, json=review)
            check("review_retry", "POST", path, headers=operator, json=review)
            check("malformed_review", "POST", path, 422, headers=operator, json={})
            outcome = {
                "decision_id": decision["decision_id"],
                "actual_action": decision["recommended_action"],
                "actual_delay_hours": 5,
                "actual_loss": 10,
                "classification": "SIMULATED",
                "evidence": "Explicit demo scenario",
            }
            check("simulated_outcome", "POST", "/outcomes", headers=operator, json=outcome)
            check("outcome_retry", "POST", "/outcomes", headers=operator, json=outcome)
            check("body_limit", "POST", "/outcomes", 413, content=b"x" * 65537)
            check(
                "fabricated_observed_outcome_rejected",
                "POST",
                "/outcomes",
                422,
                headers=operator,
                json={**outcome, "classification": "OBSERVED"},
            )
            command(["restart", "api"])
            for _ in range(60):
                try:
                    if client.get("/ready", headers=reader).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            else:
                raise TimeoutError("API did not recover after restart")
            assert (
                check("restart_readiness", "GET", "/ready", headers=reader).json()["run_id"]
                == run_id
            )
            audit = check("persistent_audit", "GET", "/audit", headers=operator).json()
            assert len(audit["reviews"]) == len(audit["outcomes"]) == 1
            feedback = check("learning_export", "GET", "/learning/export", headers=operator).json()
            assert feedback["record_count"] == 2
            assert all(r["classification"] == "SIMULATED" for r in feedback["records"])
            from maritime.feedback import persist_feedback

            decisions = client.get("/decisions", headers=reader).json()["items"]
            receipt = persist_feedback(feedback, decisions, output / "learning-destination.db")
            replay = persist_feedback(feedback, decisions, output / "learning-destination.db")
            assert receipt["accounting"]["persisted"] == replay["accounting"]["duplicate"] == 2
            (output / "learning-transfer.json").write_text(
                json.dumps({"first": receipt, "replay": replay}, indent=2), encoding="utf-8"
            )
            (output / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
            evidence.update(status="PASS", run_id=run_id)
        restored = command(
            [
                "run",
                "--rm",
                "--no-deps",
                "api",
                "python",
                "-c",
                "import json; from maritime.recovery import backup,restore; backup('/app/data','/tmp/snapshot'); print(json.dumps(restore('/tmp/snapshot','/tmp/restored')))",
            ]
        )
        receipt = json.loads(restored.stdout.decode().strip().splitlines()[-1])
        assert receipt["status"] == "PASS_LOCAL_RESTORE" and receipt["published_run"] == run_id
        (output / "backup-restore.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except Exception:
        evidence["status"] = "FAIL"
        raise
    finally:
        try:
            command(["logs", "--no-color"], required=False)
            stopped = command(["stop"], required=False)
            if stopped.returncode:
                evidence["status"] = "FAIL"
        except Exception as exc:
            evidence["cleanup_error"] = str(exc)
            evidence["status"] = "FAIL"
        evidence["files"] = {
            str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.iterdir()
            if p.is_file()
        }
        (output / "result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({"status": evidence["status"], "evidence": str(output)}))
    if evidence["status"] != "PASS":
        raise RuntimeError("Docker validation or cleanup failed; inspect result.json")


if __name__ == "__main__":
    main()
