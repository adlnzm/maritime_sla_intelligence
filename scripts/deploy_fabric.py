"""Create/update owned Fabric items, upload package, execute and retain job evidence."""

import argparse
import base64
import json
import os
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential

API = "https://api.fabric.microsoft.com/v1"


class Fabric:
    def __init__(self, workspace):
        self.workspace = str(uuid.UUID(workspace))
        self.credential = DefaultAzureCredential()
        self.client = httpx.Client(timeout=60)

    def request(self, method, path, **kwargs):
        url = path if path.startswith(API + "/") else API + path
        for attempt in range(4):
            token = self.credential.get_token("https://api.fabric.microsoft.com/.default").token
            response = self.client.request(
                method, url, headers={"Authorization": "Bearer " + token}, **kwargs
            )
            if response.status_code not in {429, 502, 503, 504} or attempt == 3:
                response.raise_for_status()
                return response
            time.sleep(min(60, int(response.headers.get("Retry-After", 2**attempt))))
        raise RuntimeError("Retry limit reached")

    def finish(self, response):
        if response.status_code != 202:
            return response.json() if response.content else {}
        location = response.headers["Location"]
        if not location.startswith(API + "/"):
            raise ValueError("Unexpected Fabric operation polling URL")
        for _ in range(120):
            time.sleep(min(30, int(response.headers.get("Retry-After", "5"))))
            response = self.request("GET", location)
            body = response.json()
            if body.get("status") in {"Failed", "Cancelled"}:
                raise RuntimeError(json.dumps(body))
            if body.get("status") == "Succeeded":
                result = self.request("GET", location.rstrip("/") + "/result")
                return result.json() if result.content else {}
        raise TimeoutError("Fabric item operation exceeded wait budget")

    def items(self):
        url = f"/workspaces/{self.workspace}/items"
        items = []
        while url:
            body = self.request("GET", url).json()
            items.extend(body["value"])
            url = body.get("continuationUri")
        return items

    def upsert(self, name, kind, definition=None):
        matches = [i for i in self.items() if i["displayName"] == name and i["type"] == kind]
        if len(matches) > 1:
            raise ValueError("Ambiguous existing Fabric item")
        if matches:
            item = matches[0]
            if definition:
                self.finish(
                    self.request(
                        "POST",
                        f"/workspaces/{self.workspace}/items/{item['id']}/updateDefinition",
                        json={"definition": definition},
                    )
                )
            return item["id"]
        body = {"displayName": name, "type": kind}
        if definition:
            body["definition"] = definition
        result = self.finish(self.request("POST", f"/workspaces/{self.workspace}/items", json=body))
        return result["id"]

    def upload(self, lakehouse, path, content):
        token = self.credential.get_token("https://storage.azure.com/.default").token
        url = f"https://onelake.dfs.fabric.microsoft.com/{self.workspace}/{lakehouse}/Files/{path}"
        headers = {"Authorization": "Bearer " + token, "x-ms-version": "2021-06-08"}
        parent = url.rsplit("/", 1)[0]
        directory = self.client.put(parent, params={"resource": "directory"}, headers=headers)
        if directory.status_code != 409:
            directory.raise_for_status()
        # ADLS path create, append, flush. Writes only the owned maritime package paths.
        for method, params, data in [
            ("PUT", {"resource": "file"}, b""),
            ("PATCH", {"action": "append", "position": 0}, content),
            ("PATCH", {"action": "flush", "position": len(content)}, b""),
        ]:
            response = self.client.request(
                method, url, params=params, headers=headers, content=data
            )
            response.raise_for_status()


def definition(path, content, format=None):
    result = {
        "parts": [
            {
                "path": path,
                "payload": base64.b64encode(content).decode(),
                "payloadType": "InlineBase64",
            }
        ]
    }
    if format:
        result["format"] = format
    return result


def deploy(execute=False):
    workspace = os.getenv("FABRIC_WORKSPACE_ID")
    if not workspace:
        raise SystemExit(
            "ENVIRONMENT_DEPENDENT: set FABRIC_WORKSPACE_ID and Azure identity credentials; no deployment attempted"
        )
    fabric = Fabric(workspace)
    lakehouse = os.getenv("FABRIC_LAKEHOUSE_ID") or fabric.upsert(
        "MaritimeIntelligence", "Lakehouse"
    )
    lakehouse = str(uuid.UUID(lakehouse))
    wheel = Path("dist/maritime_sla_intelligence-0.1.0-py3-none-any.whl")
    if not wheel.is_file():
        raise SystemExit("Build the wheel first: python -m build")
    fabric.upload(lakehouse, "maritime/" + wheel.name, wheel.read_bytes())
    package = Path("dist/configs.zip")
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in Path("configs").glob("*.json"):
            archive.write(file, file.as_posix())
    fabric.upload(lakehouse, "maritime/configs.zip", package.read_bytes())
    notebook_ids = {}
    for stage in ("bronze", "silver", "gold", "acceptance", "import_predictions"):
        notebook = json.loads(Path(f"fabric/notebooks/{stage}.ipynb").read_text())
        notebook["metadata"]["dependencies"] = {
            "lakehouse": {
                "default_lakehouse": lakehouse,
                "default_lakehouse_name": "MaritimeIntelligence",
                "default_lakehouse_workspace_id": workspace,
            }
        }
        notebook_ids[stage] = fabric.upsert(
            "Maritime_" + stage,
            "Notebook",
            definition("notebook-content.ipynb", json.dumps(notebook).encode(), "ipynb"),
        )
    activities = []
    previous = None
    for stage, notebook_id in notebook_ids.items():
        if stage == "import_predictions":
            continue  # Runs after Azure ML batch output returns, not before it exists.
        activities.append(
            {
                "name": stage,
                "type": "TridentNotebook",
                "dependsOn": [{"activity": previous, "dependencyConditions": ["Succeeded"]}]
                if previous
                else [],
                "policy": {"timeout": "0.02:00:00", "retry": 2, "retryIntervalInSeconds": 30},
                "typeProperties": {
                    "notebookId": notebook_id,
                    "workspaceId": workspace,
                    "parameters": {
                        "run_id": {
                            "value": {"value": "@pipeline().RunId", "type": "Expression"},
                            "type": "string",
                        },
                        "as_of": {
                            "value": {
                                "value": "@formatDateTime(utcNow(),'yyyy-MM-dd')",
                                "type": "Expression",
                            },
                            "type": "string",
                        },
                    },
                },
            }
        )
        previous = stage
    pipeline_body = {"properties": {"activities": activities}}
    pipeline_id = fabric.upsert(
        "Maritime_EndToEnd",
        "DataPipeline",
        definition("pipeline-content.json", json.dumps(pipeline_body).encode()),
    )
    evidence = {
        "workspace_id": workspace,
        "lakehouse_id": lakehouse,
        "notebooks": notebook_ids,
        "pipeline_id": pipeline_id,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "validation": "DEPLOYED_NOT_EXECUTED",
    }
    Path("fabric/deployment.json").write_text(json.dumps(evidence, indent=2))
    if execute:
        response = fabric.request(
            "POST",
            f"/workspaces/{workspace}/items/{pipeline_id}/jobs/instances?jobType=Pipeline",
            json={},
        )
        location = response.headers["Location"]
        evidence["job_url"] = location
        for _ in range(240):
            time.sleep(30)
            job = fabric.request("GET", location).json()
            print(json.dumps({"job_status": job["status"]}), flush=True)
            if job["status"] in {"Completed", "Failed", "Cancelled", "Deduped"}:
                evidence["job"] = job
                evidence["validation"] = (
                    "EXECUTED_SUCCESS" if job["status"] == "Completed" else "FAILED"
                )
                break
        else:
            evidence["validation"] = "TIMED_OUT"
        Path("fabric/deployment.json").write_text(json.dumps(evidence, indent=2))
        if evidence["validation"] != "EXECUTED_SUCCESS":
            raise RuntimeError(
                "Fabric execution did not complete successfully; inspect deployment.json"
            )
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    deploy(parser.parse_args().execute)
