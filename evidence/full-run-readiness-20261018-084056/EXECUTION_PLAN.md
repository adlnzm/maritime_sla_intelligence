# Verified execution path — DO NOT EXECUTE under this assessment

Decision: **NO-GO**, 18 October 2026. Source inspected at revision `4b50f50769b08e763015064c53d91b6bda4ae079`, dirty tree; 146 release source hashes still match. No application run or migration was performed.

## Command and target selection

`docs/operations/READY_TO_RUN.md` documents the native full live pipeline:

```powershell
.venv/Scripts/python.exe -m maritime.cli run --data-dir data/live
```

It defaults to local ML and the current UTC date. To make source/config/backend resolution explicit after repairing the environment:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m maritime.cli run --data-dir data/live --config configs/pipeline.json --registry configs/sources.json --ml-backend local
```

These are verified command syntaxes, **not approved launch instructions**. `data/live` is currently absent. Owner must choose that new root versus an existing root and accept the corresponding backfill/storage effects. The bare README command `maritime run` uses `MARITIME_DATA_DIR` or `data`, which currently contains a legacy-version database. Do not silently substitute that target.

Alternative documented Compose path: `docker compose --profile pipeline run --rm pipeline`, then `docker compose up --build -d api`. It uses the Compose project's named `maritime-data` volume at `/app/data`, not host `data/live`. Current engine/project/volume state is unavailable. Do not execute Compose until the exact project/volume and image are inspected. `--rm` removes the new one-shot container, not the named data volume. API is a separate process/service, not automatically launched by the native pipeline. Local serving requires separately supplied reader/operator keys and matching `MARITIME_DATA_DIR`; none is configured in the inspected environment.

## External calls and workload

`cli.main` → `pipeline.run` → OS-exclusive root lock → `_run` → ingestion, validation, local intelligence/scenarios/ML, persisted readback and publication.

- IMF port reference: configured `PortWatch_ports_database/FeatureServer/0/query` on `services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/`; selects the six configured names. Daily activity uses `Daily_Ports_Data/FeatureServer/0/query` on the same service root, with count reconciliation and 1,000-row pages, repeated-page rejection and a 10,000-page ceiling.
- New root: up to 240 days of activity. Existing cache: start is max(240-day lower bound, last cached date minus 14-day revision overlap). For the default cache at Oct 2 and an Oct 18 run, the overlap begins September 18. Date/port duplicates and out-of-window results fail. Requeried window replaces the cached window, including source deletions; expired rows are accounted separately. No cache reset command is invoked.
- Optional Open-Meteo `https://archive-api.open-meteo.com/v1/archive` provides reanalysis; WPI, UN/LOCODE and route downloads are unconfigured. Their absence/failure is declared degraded, not fabricated. Owner must accept this declared scope. No new source was integrated. Source rights/free-service entitlement remains separate from HTTP availability.
- Each HTTP call has a 45-second client timeout, up to four attempts, retryable transport/429/5xx handling, exponential delay or numeric Retry-After capped at 60 seconds, and per-run circuit opening on exhaustion. These bounds do not establish a total run deadline or memory ceiling for native execution.
- Local ML writes port-call model artifacts; 60 simulated shipments and 512 draws are configured. No actual carrier actions. No Fabric/Azure/AML/OpenAI request is made by this explicit `--ml-backend local` run. Selecting another backend is a different scope requiring new acceptance.

## Persistent effects

`Store.__init__` creates the root, opens SQLite, sets WAL, executes CREATE IF NOT EXISTS tables/indexes/triggers and sets `user_version=1`; versions above 1 are rejected. The current default DB is version 0, so using it would alter existing schema/settings. This assessment never constructed Store.

Tables: `runs`, `products`, `metadata`, `audit`, `releases`, `audit_chain`, SQLite sequence and indexes/triggers. Each attempted run gets a UUID. Reports/status and stage audits are persisted; business audit retries have deterministic identities. Products are replaced only within the current run/product key before approval; this is a scoped DELETE/INSERT, not whole-database truncation. Approved products/releases and audit rows have mutation-denial triggers.

Files: `.pipeline.lock`; SQLite DB/WAL/SHM; content-addressed `bronze/<source>/<sha>.raw`; `quarantine/<run>/dispositions.json`; `silver/<run>/`; `gold/<run>/` JSON and GIS; `reports/<run>/report.json`/`.md`; `releases/<run>.json`; `models/<version>/model.joblib` and `registry.json`. Existing model-version files can be written again: do not assume every file is append-only. Raw files with identical hashes are reused only after checksum verification.

Activity checkpoint metadata is committed **after DQ passes but before later stages finish**. A later failure can advance the cache without advancing the accepted publication. Successful publication verifies persisted products against the manifest and atomically inserts the release plus changes `metadata.published_run` in a SQLite transaction. Older approved products remain stored. Ordinary exceptions record FAILED and retain the prior pointer; last-successful availability still depends on data freshness and integrity, so preserving a pointer does not mean readiness stays green.

CLI reruns use a new UUID; they are not no-op invocations. They reacquire/merge the overlap, write new stage records and may publish a new release. Programmatic retries with the same approved run ID and matching request fingerprint can return the verified prior result; conflicting/failed IDs are rejected. The OS lock prevents another pipeline writer for that root, but it does not stop independent API business writes. Presence of a lock file is not proof of lock ownership.

## Stop and recovery boundary

Stop before launch on dependency incompatibility, unresolved root/volume, unknown writer, insufficient headroom, unapproved legacy DB changes, invalid source contract, any required port older than ten days, missing backup evidence or unresolved integrity findings.

For a future authorized native run: retain console output privately, record root and run UUID; use a single Ctrl+C on the owning terminal if stopping is necessary. `KeyboardInterrupt` is not caught by `except Exception`; finally may write a RUNNING report. Forced termination can leave partial files/RUNNING state. OS lock releases on process exit. Do not promise a clean cancellation receipt or interrupt an unrelated Python process. On retry, lock reacquisition marks prior RUNNING records ABANDONED and audits recovery; it does not delete their artifacts. No process was interrupted during this assessment.

Before a retry, confirm process exit, inspect DB/integrity/audit/release/checkpoint and the last publication using a genuinely read-only inspection. Do not use `maritime report` as a no-write check: it constructs Store. Never delete the checkpoint or lock file to force recovery. A completed-but-stale prior publication must remain unavailable for current serving.

Before writing an existing root, require a verified backup of that exact root and a tested fresh restore destination. Future commands, only after explicit scope/authorization:

```powershell
.venv/Scripts/python.exe -m maritime.cli backup --data-dir <chosen-root> --output <new-nonoverlapping-backup>
.venv/Scripts/python.exe -m maritime.cli restore --input <verified-backup> --data-dir <new-nonoverlapping-restore>
```

Backup acquires the pipeline lock, creates a SQLite backup and copies files; destination verification constructs Store and checkpoints the destination WAL. It is not a read-only assessment command and was not executed. Root `data` also contains environments, tools and many historical subdirectories: its recursive backup scope is much broader than one DB. Choose a narrowly scoped operational root; do not silently back up or mutate the whole directory. Quiesce writers only under separate authorization. Verify manifests, database, full audit chain and published products before switching the configured root. Preserve original and restored data; do not overwrite the original to recover.

Current historical isolated recovery tests are useful evidence, but do not prove recovery of today's chosen root. There is no approved resource budget/run deadline or current target backup/restore receipt, so unrestricted operation remains blocked.
