"""Azure application-plane snapshots and durable append-only operator audits.

Fabric remains authoritative. Blob snapshots are a serving copy, not a second data pipeline.
"""

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from maritime.models import json_default, utcnow


class AzureStore:
    def __init__(self, container=None, audit_container=None):
        if container is None:
            from azure.storage.blob import BlobServiceClient

            from maritime.azure_security import credential

            service = BlobServiceClient(
                os.environ["AZURE_STORAGE_ACCOUNT_URL"], credential=credential()
            )
            container = service.get_container_client(
                os.getenv("AZURE_SERVING_CONTAINER", "maritime-serving")
            )
            audit_container = service.get_container_client(
                os.getenv("AZURE_AUDIT_CONTAINER", "maritime-audit")
            )
        self.container = container
        self.audit_container = audit_container or container

    def _json(self, name):
        return json.loads(self.container.download_blob(name).readall())

    def metadata(self, key, default=None):
        if key != "published_run":
            return default
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._json("published.json")["run_id"]
        except ResourceNotFoundError:
            return default

    def read(self, product, run_id=None):
        run_id = run_id or self.metadata("published_run")
        if not run_id:
            return []
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise ValueError("Invalid run ID")
        manifest = self._json(f"runs/{run_id}/manifest.json")
        entry = manifest["products"].get(product)
        if entry is None:
            return []
        raw = self.container.download_blob(entry["blob"]).readall()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Serving snapshot checksum mismatch")
        return json.loads(raw)

    def release(self, run_id=None):
        run_id = run_id or self.metadata("published_run")
        return (
            self._json(f"runs/{run_id}/manifest.json").get("governance_release") if run_id else None
        )

    def read_approved(self, product, run_id=None):
        from maritime.governance import contract, fingerprint

        manifest = self.release(run_id)
        if not manifest or manifest.get("status") not in contract()["allowed_release_states"]:
            raise ValueError("No approved cloud serving release")
        rows = self.read(product, run_id)
        expected = manifest["datasets"].get(product)
        if not expected or fingerprint(rows) != expected["sha256"] or len(rows) != expected["rows"]:
            raise ValueError("Cloud serving release integrity failure")
        return rows

    def latest_report(self):
        run_id = self.metadata("published_run")
        return self._json(f"runs/{run_id}/report.json") if run_id else None

    def audit(self, kind, payload):
        if kind not in {"review", "outcome", "extraction"}:
            raise ValueError("Unsupported audit kind")
        at = utcnow()
        audit_id = uuid.uuid4().hex
        self.audit_container.upload_blob(
            f"audit/{kind}/{audit_id}.json",
            json.dumps({**payload, "created_at": at, "audit_id": audit_id}, default=json_default),
            overwrite=False,
        )
        return audit_id

    def audits(self, kind):
        rows = [
            json.loads(self.audit_container.download_blob(item.name).readall())
            for item in self.audit_container.list_blobs(name_starts_with=f"audit/{kind}/")
        ]
        return sorted(rows, key=lambda r: r["created_at"])

    def publish(self, folder, report):
        from azure.core.exceptions import ResourceNotFoundError

        from maritime.governance import verify_manifest

        if report["status"] != "SUCCESS" or report["data_quality"]["status"] != "PASS":
            raise ValueError("Only validated Gold runs may be published")
        run_id = report["run_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise ValueError("Invalid run ID")
        files = list(Path(folder).glob("*.json"))
        required = {
            "ports",
            "congestion",
            "network",
            "scenarios",
            "sla_risk",
            "interventions",
            "decisions",
            "lineage",
            "data_quality",
        }
        if required - {p.stem for p in files}:
            raise ValueError("Missing required serving products")
        if "release" not in report:
            raise ValueError("Missing mandatory governance release evidence")
        verify_manifest({p.stem: json.loads(p.read_bytes()) for p in files}, report["release"])
        try:
            existing = self._json(f"runs/{run_id}/manifest.json")
        except ResourceNotFoundError:
            existing = None
        if existing:
            if existing.get("governance_release") != report["release"]:
                raise ValueError("Approved run is immutable; publish a new run ID")
            return existing
        manifest = {
            "run_id": run_id,
            "products": {},
            "published_at": utcnow(),
            "governance_release": report["release"],
        }
        for file in files:
            raw = file.read_bytes()
            rows = json.loads(raw)
            if any(r.get("run_id") != run_id for r in rows):
                raise ValueError("Serving product run ID mismatch")
            digest = hashlib.sha256(raw).hexdigest()
            blob = f"runs/{run_id}/{file.stem}.{digest}.json"
            self.container.upload_blob(blob, raw, overwrite=True)
            manifest["products"][file.stem] = {"blob": blob, "sha256": digest}
        self.container.upload_blob(
            f"runs/{run_id}/report.json", json.dumps(report, default=json_default), overwrite=True
        )
        self.container.upload_blob(
            f"runs/{run_id}/manifest.json", json.dumps(manifest), overwrite=True
        )
        # Publication occurs after every immutable content-addressed product is uploaded.
        self.container.upload_blob("published.json", json.dumps({"run_id": run_id}), overwrite=True)
        return manifest
