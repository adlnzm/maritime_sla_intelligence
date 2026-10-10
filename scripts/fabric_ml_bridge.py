"""Transfer versioned feature assets and predictions between OneLake and Azure ML."""

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential

from maritime.ml_contract import load_features
from maritime.pipeline import load_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["download-features", "upload-predictions", "publish-serving"]
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--folder", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_id):
        raise ValueError("Invalid run ID")
    workspace, lakehouse = os.environ["FABRIC_WORKSPACE_ID"], os.environ["FABRIC_LAKEHOUSE_ID"]
    root = f"https://onelake.dfs.fabric.microsoft.com/{workspace}/{lakehouse}/Files/maritime/runs/{args.run_id}"
    credential = DefaultAzureCredential()
    headers = {
        "Authorization": "Bearer "
        + credential.get_token("https://storage.azure.com/.default").token,
        "x-ms-version": "2021-06-08",
    }
    client = httpx.Client(timeout=60)
    folder = Path(args.folder)
    if args.mode == "publish-serving":
        from maritime.azure_store import AzureStore

        response = client.get(root + "/fabric-report.json", headers=headers)
        response.raise_for_status()
        report = response.json()
        if (
            report["run_id"] != args.run_id
            or report["gates"]["fabric"] != "PASS_EXECUTED_DELTA_READBACK"
        ):
            raise ValueError("Only accepted Fabric runs can be served")
        folder.mkdir(parents=True, exist_ok=True)
        products = folder / args.run_id
        products.mkdir(exist_ok=True)
        for name in report["serving_products"]:
            if not re.fullmatch(r"[a-z_]+", name):
                raise ValueError("Invalid product name")
            response = client.get(
                root + f"/evidence/gold/{args.run_id}/{name}.json", headers=headers
            )
            response.raise_for_status()
            (products / (name + ".json")).write_bytes(response.content)
        manifest = AzureStore().publish(products, report)
        write_json(folder / "serving-publication.json", manifest)
    elif args.mode == "download-features":
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("manifest.json", "features.csv", "activity.json"):
            response = client.get(
                root + f"/evidence/azure_features/{args.run_id}/{name}", headers=headers
            )
            response.raise_for_status()
            (folder / name).write_bytes(response.content)
        load_features(folder)
    else:
        rows = load_json(folder / "predictions.json")
        if not rows or any(
            r["fabric_run_id"] != args.run_id or r["classification"] != "PREDICTED" for r in rows
        ):
            raise ValueError("Azure ML prediction run/classification mismatch")
        data = (folder / "predictions.json").read_bytes()
        url = root + "/azure-ml-predictions.json"
        for method, params, content in [
            ("PUT", {"resource": "file"}, b""),
            ("PATCH", {"action": "append", "position": 0}, data),
            ("PATCH", {"action": "flush", "position": len(data)}, b""),
        ]:
            response = client.request(method, url, params=params, headers=headers, content=content)
            response.raise_for_status()
        # The deployed prediction-import notebook validates and materializes Delta predictions.
        from deploy_fabric import Fabric

        notebook_id = os.getenv("FABRIC_PREDICTION_NOTEBOOK_ID")
        if not notebook_id:
            notebook_id = load_json("fabric/deployment.json")["notebooks"]["import_predictions"]
        fabric = Fabric(workspace)
        response = fabric.request(
            "POST",
            f"/workspaces/{workspace}/items/{notebook_id}/jobs/instances?jobType=RunNotebook",
            json={
                "executionData": {
                    "parameters": {"run_id": {"value": args.run_id, "type": "string"}}
                }
            },
        )
        job_url = response.headers["Location"]
        evidence = {"status": "SUBMITTED", "job_url": job_url, "run_id": args.run_id}
        write_json(folder / "fabric-import-job.json", evidence)
        for _ in range(120):
            time.sleep(30)
            job = fabric.request("GET", job_url).json()
            if job["status"] in {"Completed", "Failed", "Cancelled", "Deduped"}:
                evidence["job"] = job
                evidence["status"] = job["status"]
                write_json(folder / "fabric-import-job.json", evidence)
                if job["status"] != "Completed":
                    raise RuntimeError("Fabric prediction import failed")
                break
        else:
            raise TimeoutError("Fabric prediction import exceeded one hour")
        response = client.get(root + "/prediction-return.json", headers=headers)
        response.raise_for_status()
        readback = response.json()
        if readback["run_id"] != args.run_id or readback["prediction_count"] != len(rows):
            raise ValueError("Fabric prediction import readback mismatch")
        write_json(folder / "fabric-import-readback.json", readback)
    print(json.dumps({"status": "TRANSFER_COMPLETED", "mode": args.mode, "run_id": args.run_id}))


if __name__ == "__main__":
    main()
