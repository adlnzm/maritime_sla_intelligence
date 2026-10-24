"""Reconcile actual local verification outputs and package retained evidence."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", required=True, help="Completed final Compose project name")
    args = parser.parse_args()
    root = Path("evidence/ready-to-run")
    from maritime.release_evidence import verify_source

    binding = root / "validated-source.json"
    if not binding.exists():
        raise ValueError(
            "Historical campaign has no final-source binding; use scripts/production_release.py"
        )
    verify_source(read(binding))
    demo_path = root / args.demo / "result.json"
    demo = read(demo_path)
    quality = read(root / "quality-exit-codes.json")
    audit = read(root / "dependency-audit.json")
    live = read(root / "live/release-validation.json")
    staged = read(root / "aml-staged-build.json")
    suite = ET.parse(root / "verified-tests.xml").getroot().find("testsuite")
    checks = {
        "quality": all(quality.get(k) == 0 for k in ("tests", "lint", "format", "build")),
        "tests": int(suite.attrib["tests"]) > 0
        and all(int(suite.attrib[k]) == 0 for k in ("errors", "failures", "skipped")),
        "docker": demo["status"] == "PASS" and "learning_export" in demo["checks"],
        "live_recovery": live["campaign"]["status"] == "PASS",
        "security": bool(audit["dependencies"])
        and not any(d["vulns"] for d in audit["dependencies"]),
        "ml_package": staged["exit_code"] == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Cannot seal local readiness: {checks}")
    requirements_path = Path("docs/requirements/requirements.json")
    inventory = read(requirements_path)
    new_verified = {"API-02", "OPS-03", "OPS-04", "OPS-05", "OPS-06", "OPS-07"}
    for row in inventory["requirements"]:
        if row["id"] in new_verified:
            row["status"] = "VERIFIED"
            row["remaining_work_and_acceptance"] = (
                "Local acceptance passed; retain regression coverage"
            )
        if row["id"] == "LRN-02":
            row.update(
                status="BLOCKED_EXTERNAL",
                implementation=[
                    "src/maritime/feedback.py",
                    "scripts/fabric_feedback.py",
                    "fabric/notebooks/import_feedback.ipynb",
                ],
                remaining_work_and_acceptance="Export/contracts implemented and locally tested; execute Azure audit to Fabric Delta import with matching readback",
            )
        row["implementation"] = [
            str(Path("src/maritime") / p).replace("\\", "/")
            if Path("src/maritime", p).is_file()
            else p
            for p in row["implementation"]
        ]
        if row["status"] == "VERIFIED":
            row["evidence"] = [
                str(root / "verified-tests.xml").replace("\\", "/"),
                str(demo_path).replace("\\", "/"),
                str(root / "live/release-validation.json").replace("\\", "/"),
            ]
    write(requirements_path, inventory)
    md_path = Path("docs/requirements/feature_traceability.md")
    heading = md_path.read_text(encoding="utf-8").split("| ID |")[0]
    heading += "| ID | Expected behavior / stage | Implementation | Upstream → downstream | Required test/evidence | Status | Remaining acceptance |\n|---|---|---|---|---|---|---|\n"
    for row in inventory["requirements"]:
        heading += f"| {row['id']} | {row['behavior']} | {', '.join(row['implementation'])} | {row['dependencies']} | {', '.join(row['tests'])} | {row['status']} | {row['remaining_work_and_acceptance']} |\n"
    md_path.write_text(heading, encoding="utf-8")
    manifest = {
        "readiness": "LOCAL_READY",
        "scope": "Local analytical API, public replay/live acquisition, explicitly simulated shipment decisions",
        "production": "BLOCKED_EXTERNAL",
        "checks": checks,
        "test_suite": suite.attrib,
        "docker_evidence": str(demo_path).replace("\\", "/"),
        "live_run": live["run_id"],
        "audited_dependencies": len(audit["dependencies"]),
        "requirements": inventory["requirements"],
        "files": {},
    }
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "evidence-manifest.json":
            manifest["files"][path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    manifest["source_files"] = {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("src", "configs", "scripts", "docker", "docs")
        for path in sorted(Path(folder).rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    for path in ("pyproject.toml", "uv.lock", "compose.demo.yml", ".env.example"):
        manifest["source_files"][path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    write(root / "evidence-manifest.json", manifest)
    archive_path = Path("evidence/ready-to-run.zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    print(
        json.dumps(
            {
                "readiness": manifest["readiness"],
                "verified_files": len(manifest["files"]),
                "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
