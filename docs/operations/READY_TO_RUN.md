# Ready-to-run local workflow

Run commands from the repository root. Use Python 3.11 (validated 3.11.9), uv 0.12.18, and Docker Desktop running Linux containers with Compose v2. Production readiness is not implied by this local replay.

## Install and validate

PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
$env:UV_LINK_MODE = "copy"
uv sync --frozen --no-editable --extra dev --extra fabric --extra azure --extra ml
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests scripts
.venv/Scripts/python.exe -m ruff format --check src tests scripts
uv build
```

Regular installation avoids Python 3.11 locale problems with editable installs in non-ASCII Windows paths. On Unix use .venv/bin/python and export environment variables. The lockfile pins dependencies; no database server or cloud credentials are needed locally.

## Clean Docker demonstration

```powershell
.venv/Scripts/python.exe scripts/docker_demo.py
```

This creates a unique Compose project and new named volume, builds the image, replays retained public activity, waits for the seed job before starting the API, checks real HTTP reads and role boundaries, records a SIMULATED outcome, rejects a fabricated OBSERVED outcome, verifies learning export, restarts the API and verifies audit persistence. It generates ephemeral independent secrets without printing them, writes evidence under evidence/ready-to-run/<project>, and stops containers while preserving their volume. Port 18081 must be free; set MARITIME_DEMO_PORT to another free port if needed. Failed attempts retain logs. This is historical public-data replay with simulated shipments, not live acquisition or a cloud test.

For an interactive persistent demo, generate secrets then use a new project name:

```powershell
$env:MARITIME_API_KEY = [guid]::NewGuid().ToString("N")
$env:MARITIME_OPERATOR_KEY = [guid]::NewGuid().ToString("N")
docker compose -f compose.demo.yml -p maritime-interactive up --build -d --wait --wait-timeout 300
Invoke-RestMethod http://127.0.0.1:18081/ready -Headers @{"X-API-Key"=$env:MARITIME_API_KEY}
```

Open http://127.0.0.1:18081/docs and authorize using the reader/operator API key. Compare /congestion, /network/exposure, /sla-risk, /interventions and /decisions. Review a decision using its decision_id, then record a SIMULATED outcome and inspect /audit and /learning/export with the operator key. These are analytical decisions, not carrier instructions.

## Live acquisition and native API

```powershell
.venv/Scripts/python.exe -m maritime.cli run --data-dir data/live
$env:MARITIME_DATA_DIR = "data/live"
.venv/Scripts/python.exe -m maritime.cli serve
```

Set the two independent keys as above first. Live acquisition needs public network access. A critical acquisition/DQ failure leaves the previous approved release untouched. Use a fresh data directory for a reset; never delete an existing data directory to repair a failed run. Replay alternative: add --fixture tests/data/portwatch_sample.json. The API rejects stale live source dates while replay is explicitly labeled historical.

## Initialization, shutdown, restart and recovery

Store initialization applies idempotent CREATE TABLE/INDEX/TRIGGER statements in src/maritime/store.py and migrates legacy schema version 0 to version 1 without dropping data. A future schema version is rejected before mutation. There is no destructive migration/reset command or PostgreSQL dependency. Back up the data directory with the application stopped, including raw files, reports, model artifacts and SQLite database. Do not copy only a live WAL database file.

Stop: docker compose -f compose.demo.yml -p maritime-interactive stop.
Resume: use start, retaining the original keys/environment and volume. Restart API: restart api, then poll authenticated /ready; Compose versions differ in support for restart --wait. The supplied validator uses an explicit bounded HTTP poll.

The pipeline permits one writer per data directory. A process crash releases its OS lock; the next run marks stranded RUNNING attempts ABANDONED. Failed retry IDs cannot overwrite a prior attempt; use a new run ID. Publication integrity is rechecked before serving. Manual volume removal is deliberately excluded from the reset path. New project names provide isolated empty volumes.

## Diagnostics and security

/health is liveness; authenticated /ready requires an approved release. Missing reader credentials or identical reader/operator keys fail application startup. An absent operator key leaves administrative routes inaccessible. Unknown auth/storage modes fail explicitly. .env.example documents variables; native Python does not automatically load .env. Compose reads .env but never commit it.

Inspect docker compose ... logs api seed, data/reports/<run_id>/report.json, /run-report, /data-quality, /lineage and /metrics. Responses carry X-Correlation-ID, and logs include the published run ID. /run-report describes the published release; maritime report describes the latest attempt, including failures.

For cloud deployment and credentials see ../azure.md and ../fabric.md. Use scripts/fabric_feedback.py --run-id <Fabric-run> --evidence <new-file.json> after redeploying notebooks and generating audited feedback. No Azure ML, Fabric, Power BI or AOAI round trip is implied until these commands execute successfully with real credentials.


## Source-bound release validation and recovery (2026-10-11)

Install the official Bicep CLI (https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/install). The current campaign used Bicep 0.48.1. Put it on PATH or supply --bicep <absolute executable>. From the installed bootstrap environment:

```powershell
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe scripts/production_release.py --output evidence/my-new-release --live --bicep data/tools/bicep.exe
```

The output directory must not already exist. This creates a separate Python environment under data/, installs the frozen lock, runs every test, lint/format/build, PBIR schema checks, Bicep compilation, dependency audit, isolated Docker build/start/restart/backup/restore, and the live acquisition/failure campaign. It seals logs and checksums into a ZIP and rejects source changes during validation. Network access, Docker Desktop and a free demo port are required. Omit --live only for an explicitly local replay campaign; it does not certify new source acquisition. The older package_readiness.py cannot certify current source using historical logs.

For native data recovery, stop the API before a coordinated snapshot, then:

```powershell
.venv/Scripts/python.exe -m maritime.cli backup --data-dir data/live --output data/backup-new
.venv/Scripts/python.exe -m maritime.cli restore --input data/backup-new --data-dir data/restored-new
```

Both destinations must be new and outside the source tree. Backup uses SQLite's online backup API, a pipeline writer lock, retained raw/product files and SHA-256 manifest. Restore verifies all checksums before creating the destination, then verifies database integrity, the audit chain and all approved releases. Switch MARITIME_DATA_DIR only after PASS_LOCAL_RESTORE. Keep the original directory for rollback. This establishes functional recovery, not an owner-approved RPO/RTO or offsite durability guarantee.

Feedback can be transferred locally with `maritime import-feedback --packet <export.json> --decisions <approved-decisions-array.json> --destination <new-or-existing.sqlite>`. Destination transactions insert missing audit IDs, verify duplicates against canonical hashes and read every incoming row back. Receipts are retained in `<destination>-receipts/`. Replaying a smaller export cannot erase earlier records. The Docker validator exercises this path; it remains separate from the unexecuted Fabric cloud bridge.

/health/ready is an anonymous minimal readiness probe (ready/unavailable only); /ready retains authenticated detail. POST bodies are limited to MARITIME_MAX_BODY_BYTES (default 65536), with HTTP 413 and correlation ID on rejection. MARITIME_MAX_CONCURRENCY defaults to 64; these are defensive bounds, not throughput promises. Demo containers have read-only root filesystems, bounded temporary space/CPU/memory/PIDs, no Linux capabilities and no privilege escalation.
