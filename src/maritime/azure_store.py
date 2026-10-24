"""Azure application-plane snapshots and durable append-only operator audits.

Fabric remains authoritative. Blob snapshots are a serving copy, not a second data pipeline.
"""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from maritime.models import json_default, utcnow


class AzureStore:
    def __init__(self, container=None, audit_container=None):
        if container is None:
            account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")
            endpoint = urlsplit(account_url)
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
                or endpoint.path not in {"", "/"}
            ):
                raise ValueError("AZURE_STORAGE_ACCOUNT_URL must be an HTTPS account endpoint")
            serving_name = os.getenv("AZURE_SERVING_CONTAINER", "maritime-serving")
            audit_name = os.getenv("AZURE_AUDIT_CONTAINER", "maritime-audit")
            for name in (serving_name, audit_name):
                if not re.fullmatch(r"[a-z0-9](?:[a-z0-9]|-(?!-)){1,61}[a-z0-9]", name):
                    raise ValueError("Invalid Azure storage container name")
            if serving_name == audit_name:
                raise ValueError("Serving and audit containers must differ")
            from azure.storage.blob import BlobServiceClient

            from maritime.azure_security import credential

            service = BlobServiceClient(
                account_url,
                credential=credential(),
                connection_timeout=5,
                read_timeout=15,
                retry_total=3,
            )
            container = service.get_container_client(serving_name)
            audit_container = service.get_container_client(audit_name)
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

        # Resolve once: publication may advance between manifest and product reads.
        run_id = run_id or self.metadata("published_run")
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

    def read_layer(self, layer, dataset, run_id=None, approved=True):
        from maritime.governance import fingerprint

        run_id = run_id or self.metadata("published_run")
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise ValueError("Medallion dataset unavailable")
        manifest = self._json(f"runs/{run_id}/manifest.json")
        key = f"{layer}.{dataset}"
        entry = manifest.get("medallion_products", {}).get(key)
        expected = manifest["governance_release"].get("medallion", {}).get(key)
        if not entry or not expected:
            raise ValueError("Medallion dataset unavailable")
        rows = self._json(entry["blob"])
        if expected != {"rows": len(rows), "sha256": fingerprint(rows)}:
            raise ValueError("Medallion serving integrity failure")
        return rows

    def audit(self, kind, payload):
        from azure.core.exceptions import ResourceExistsError

        from maritime.governance import fingerprint

        if kind not in {"review", "outcome", "extraction"}:
            raise ValueError("Unsupported audit kind")
        at = utcnow()
        audit_id = (
            fingerprint(["business-action-v1", kind, payload])
            if kind in {"review", "outcome"}
            else uuid.uuid4().hex
        )
        name = f"audit/{kind}/{audit_id}.json"
        try:
            self.audit_container.upload_blob(
                name,
                json.dumps(
                    {**payload, "created_at": at, "audit_id": audit_id}, default=json_default
                ),
                overwrite=False,
            )
        except ResourceExistsError:
            existing = json.loads(self.audit_container.download_blob(name).readall())
            if {
                k: v for k, v in existing.items() if k not in {"created_at", "audit_id"}
            } != payload:
                raise ValueError("Audit identity conflict") from None
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
        from maritime.governance import fingerprint

        layer_files = {}
        for key, expected in report["release"].get("medallion", {}).items():
            layer, dataset = key.split(".", 1)
            if layer == "gold":
                path = Path(folder) / "operations" / (dataset + ".json")
            elif layer == "silver":
                path = Path(folder).parent.parent / "silver" / run_id / (dataset + ".json")
            else:
                raise ValueError("Unknown medallion layer")
            rows = json.loads(path.read_bytes())
            if expected != {"rows": len(rows), "sha256": fingerprint(rows)}:
                raise ValueError("Medallion source integrity failure")
            layer_files[key] = path
        try:
            existing = self._json(f"runs/{run_id}/manifest.json")
        except ResourceNotFoundError:
            existing = None
        if existing:
            if existing.get("governance_release") != report["release"]:
                raise ValueError("Approved run is immutable; publish a new run ID")
            # An interrupted pointer upload leaves a complete, unpublished manifest.
            # Verify the actual destination before completing that publication.
            for product in report["release"]["datasets"]:
                self.read_approved(product, run_id)
            for key in layer_files:
                self.read_layer(*key.split(".", 1), run_id)
            current = self.metadata("published_run")
            if current and current != run_id:
                current_manifest = self._json(f"runs/{current}/manifest.json")
                if datetime.fromisoformat(
                    current_manifest["published_at"]
                ) > datetime.fromisoformat(existing["published_at"]):
                    # Replaying a previously completed upload must not roll back
                    # a subsequently published snapshot.
                    return existing
            self.container.upload_blob(
                "published.json", json.dumps({"run_id": run_id}), overwrite=True
            )
            return existing
        manifest = {
            "run_id": run_id,
            "products": {},
            "published_at": utcnow(),
            "governance_release": report["release"],
            "medallion_products": {},
        }
        for key, path in layer_files.items():
            raw = path.read_bytes()
            blob = f"runs/{run_id}/medallion/{key}.{hashlib.sha256(raw).hexdigest()}.json"
            self.container.upload_blob(blob, raw, overwrite=True)
            manifest["medallion_products"][key] = {"blob": blob}
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
        for product in report["release"]["datasets"]:
            self.read_approved(product, run_id)
        for key in layer_files:
            self.read_layer(*key.split(".", 1), run_id)
        # Publication occurs after every immutable content-addressed product is uploaded.
        self.container.upload_blob("published.json", json.dumps({"run_id": run_id}), overwrite=True)
        return manifest
