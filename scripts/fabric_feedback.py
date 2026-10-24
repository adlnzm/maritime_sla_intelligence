"""Transfer audited Azure API feedback to Fabric and require Delta readback."""

import argparse
import json
import os
import re
import time

from deploy_fabric import Fabric

from maritime.azure_store import AzureStore
from maritime.feedback import export_feedback
from maritime.pipeline import load_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        raise ValueError("Invalid run ID")
    packet = export_feedback(AzureStore(), args.run_id)
    workspace = os.environ["FABRIC_WORKSPACE_ID"]
    lakehouse = os.environ["FABRIC_LAKEHOUSE_ID"]
    fabric = Fabric(workspace)
    path = f"maritime/runs/{args.run_id}"
    fabric.upload(lakehouse, path + "/feedback.json", json.dumps(packet).encode())
    notebook = load_json("fabric/deployment.json")["notebooks"]["import_feedback"]
    response = fabric.request(
        "POST",
        f"/workspaces/{workspace}/items/{notebook}/jobs/instances?jobType=RunNotebook",
        json={
            "executionData": {"parameters": {"run_id": {"value": args.run_id, "type": "string"}}}
        },
    )
    job_url = response.headers["Location"]
    evidence = {
        "run_id": args.run_id,
        "status": "SUBMITTED",
        "job_url": job_url,
        "source_sha256": packet["sha256"],
        "records": packet["record_count"],
    }
    write_json(args.evidence, evidence)
    try:
        for _ in range(120):
            time.sleep(30)
            job = fabric.request("GET", job_url).json()
            if job["status"] == "Completed":
                break
            if job["status"] in {"Failed", "Cancelled", "Deduped"}:
                raise RuntimeError(f"Feedback import job status: {job['status']}")
        else:
            raise TimeoutError("Feedback import exceeded one hour")
        token = fabric.credential.get_token("https://storage.azure.com/.default").token
        response = fabric.client.get(
            f"https://onelake.dfs.fabric.microsoft.com/{workspace}/{lakehouse}/Files/{path}/feedback-return.json",
            headers={"Authorization": "Bearer " + token},
        )
        response.raise_for_status()
        receipt = response.json()
        if (
            receipt["run_id"] != args.run_id
            or receipt["sha256"] != packet["sha256"]
            or receipt["records"] != packet["record_count"]
            or receipt["status"] != "PASS_DELTA_READBACK"
        ):
            raise ValueError("Feedback readback mismatch")
        evidence.update(status="PASS", receipt=receipt)
    except Exception as exc:
        evidence.update(status="FAILED", failure=str(exc))
        raise
    finally:
        write_json(args.evidence, evidence)


if __name__ == "__main__":
    main()
