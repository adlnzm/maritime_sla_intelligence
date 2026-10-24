"""Non-destructive local backups with SQLite snapshot and verified fresh restore."""

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from maritime.governance import exclusive_run
from maritime.models import utcnow
from maritime.store import Store


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_store(root):
    store = Store(root)
    with store.connect() as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        manifests = [json.loads(r[0]) for r in con.execute("SELECT manifest FROM releases")]
    audit = store.verify_audit()
    if audit["status"] != "PASS":
        raise ValueError("Incomplete audit chain")
    for manifest in manifests:
        for product in manifest["datasets"]:
            store.read_approved(product, manifest["run_id"])
        for key in manifest.get("medallion", {}):
            store.read_layer(*key.split(".", 1), manifest["run_id"])
    return {
        "audit": audit,
        "approved_releases": len(manifests),
        "published_run": store.metadata("published_run"),
    }


def fresh_destination(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if (
        destination.exists()
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("Backup/restore requires a new, non-overlapping destination")
    return source, destination


def backup(source, destination):
    source, destination = fresh_destination(source, destination)
    if not (source / "maritime.db").is_file():
        raise ValueError("No source database")
    with exclusive_run(source):
        destination.mkdir(parents=True)
        # Database snapshot first; immutable source files are copied afterwards.
        with sqlite3.connect(source / "maritime.db") as src:
            with sqlite3.connect(destination / "maritime.db") as dst:
                src.backup(dst)
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError("Symlinks are not permitted in a backup")
            if path.is_file() and path.name not in {
                "maritime.db",
                "maritime.db-wal",
                "maritime.db-shm",
                ".pipeline.lock",
            }:
                target = destination / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        verification = validate_store(destination)
        with sqlite3.connect(destination / "maritime.db") as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        files = {
            p.relative_to(destination).as_posix(): digest(p)
            for p in destination.rglob("*")
            if p.is_file() and p.name not in {"maritime.db-wal", "maritime.db-shm"}
        }
        manifest = {
            "version": 1,
            "created_at": utcnow(),
            "files": files,
            "verification": verification,
            "status": "VERIFIED_LOCAL_BACKUP",
        }
        (destination / "backup-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    return manifest


def restore(source, destination):
    source, destination = fresh_destination(source, destination)
    manifest = json.loads((source / "backup-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or "maritime.db" not in manifest["files"]:
        raise ValueError("Unsupported or incomplete backup")
    for name, expected in manifest["files"].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or Path(name).is_absolute() or path.is_symlink():
            raise ValueError("Unsafe backup path")
        if digest(path) != expected:
            raise ValueError("Backup checksum mismatch")
    destination.mkdir(parents=True)
    for name in manifest["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    verification = validate_store(destination)
    if verification != manifest["verification"]:
        raise ValueError("Restored state does not match snapshot")
    return {"status": "PASS_LOCAL_RESTORE", **verification}
