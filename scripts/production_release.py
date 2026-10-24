"""Execute and seal a fresh, source-bound local release campaign. Never certifies cloud."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from maritime.release_evidence import source_snapshot, verify_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--bicep", default=shutil.which("bicep") or "data/tools/bicep.exe")
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    environment = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONPATH": str(Path("src").resolve()),
        "UV_LINK_MODE": "copy",
    }
    clean_env = Path("data") / ("release-environment-" + uuid.uuid4().hex)
    environment["UV_PROJECT_ENVIRONMENT"] = str(clean_env.resolve())
    python = str(clean_env / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    result = {
        "status": "NOT_READY",
        "production_ready": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "environment": platform.platform(),
        "source": source,
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_status": subprocess.check_output(["git", "status", "--porcelain"], text=True),
        "commands": [],
        "cloud": "BLOCKED_EXTERNAL_NO_CONFIGURED_RESOURCES",
    }

    def execute(name, command):
        started = datetime.now(timezone.utc).isoformat()
        try:
            completed = subprocess.run(command, env=environment, capture_output=True, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            (root / (name + ".log")).write_bytes((exc.stdout or b"") + (exc.stderr or b""))
            result["commands"].append(
                {
                    "name": name,
                    "command": command,
                    "exit_code": None,
                    "status": "TIMEOUT",
                    "started_at": started,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            raise
        (root / (name + ".log")).write_bytes(completed.stdout + completed.stderr)
        result["commands"].append(
            {
                "name": name,
                "command": command,
                "exit_code": completed.returncode,
                "started_at": started,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        completed.check_returncode()

    try:
        execute("git-diff", ["git", "diff", "--binary", "HEAD"])
        execute(
            "clean-install",
            [
                "uv",
                "sync",
                "--frozen",
                "--no-editable",
                "--extra",
                "dev",
                "--extra",
                "fabric",
                "--extra",
                "azure",
                "--extra",
                "ml",
            ],
        )
        execute("tests", [python, "-m", "pytest", "-q", "--junitxml=" + str(root / "tests.xml")])
        execute("package-consistency", ["uv", "pip", "check", "--python", python])
        execute("lint", [python, "-m", "ruff", "check", "src", "tests", "scripts"])
        execute("format", [python, "-m", "ruff", "format", "--check", "src", "tests", "scripts"])
        execute("build", ["uv", "build", "--out-dir", str(root / "dist")])
        execute("powerbi", [python, "scripts/build_powerbi.py"])
        execute("fabric-assets", [python, "scripts/build_fabric_assets.py"])
        execute("bicep-version", [args.bicep, "--version"])
        execute(
            "bicep",
            [
                args.bicep,
                "build",
                "azure/main.bicep",
                "--outfile",
                str(root / "azure-template.json"),
            ],
        )
        (root / "cloud-preflight.json").write_text(
            json.dumps(
                {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "configured": {
                        key: bool(os.environ.get(key))
                        for key in (
                            "FABRIC_WORKSPACE_ID",
                            "FABRIC_LAKEHOUSE_ID",
                            "AZURE_SUBSCRIPTION_ID",
                            "AZURE_RESOURCE_GROUP",
                            "AZURE_ML_WORKSPACE",
                            "AZURE_TENANT_ID",
                            "AZURE_API_AUDIENCE",
                            "AZURE_STORAGE_ACCOUNT_URL",
                            "AZURE_OPENAI_ENDPOINT",
                            "AZURE_OPENAI_DEPLOYMENT",
                        )
                    },
                    "azure_cli_available": bool(shutil.which("az")),
                    "runtime_acceptance": "NOT_EXECUTED_BY_LOCAL_RUNNER",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        execute(
            "dependency-export",
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--extra",
                "azure",
                "--extra",
                "ml",
                "--no-emit-project",
                "--output-file",
                str(root / "requirements.txt"),
            ],
        )
        execute(
            "dependency-audit",
            [
                "uv",
                "tool",
                "run",
                "--from",
                "pip-audit==2.9.0",
                "pip-audit",
                "--disable-pip",
                "--no-deps",
                "-r",
                str(root / "requirements.txt"),
                "-f",
                "json",
                "-o",
                str(root / "dependency-audit.json"),
            ],
        )
        execute("docker", [python, "scripts/docker_demo.py", "--output", str(root / "docker")])
        if args.live:
            execute(
                "live",
                [
                    python,
                    "scripts/governance_release.py",
                    "--root",
                    str(Path("data") / ("live-" + uuid.uuid4().hex)),
                    "--output",
                    str(root / "live"),
                    "--as-of",
                    datetime.now(timezone.utc).date().isoformat(),
                ],
            )
        verify_source(source)
        result["status"] = "LOCAL_READY"
    except Exception as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        try:
            verify_source(source)
            result["source_integrity"] = "PASS"
        except ValueError as exc:
            result["source_integrity"] = "FAIL"
            result["status"] = "NOT_READY"
            result["source_integrity_error"] = str(exc)
        result["ended_at"] = datetime.now(timezone.utc).isoformat()
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        manifest = {
            "release": result,
            "files": {
                p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*")
                if p.is_file() and p.name != "evidence-manifest.json"
            },
        }
        (root / "evidence-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        with zipfile.ZipFile(str(root) + ".zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        with zipfile.ZipFile(str(root) + ".zip") as archive:
            assert archive.testzip() is None
            for name, digest in manifest["files"].items():
                assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "files_verified": len(manifest["files"]),
                    "output": str(root),
                }
            )
        )


if __name__ == "__main__":
    main()
