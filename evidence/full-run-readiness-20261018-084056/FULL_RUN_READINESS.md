# Full local operational run readiness — NO-GO

Assessed 18 October 2026 (Asia/Qatar). **No unrestricted run launched.** Only read-only inventories, dependency consistency, bounded DB reads and source/evidence inspection were performed. No application behavior, dependencies, configurations, databases or checkpoints were modified. See `GATE_RESULTS.json` for commands, timestamps, limits and remediation per gate, and `EXECUTION_PLAN.md` for the verified path and side effects.

## Critical current findings

- **Environment broken:** `uv pip check --python .venv/Scripts/python.exe` exited 1: duplicate installed `pytz` distributions (2025.2 and 2026.5) and incomplete `aiohappyeyeballs` metadata. The previous passing campaign used a separate release environment, not proof that this `.venv` is runnable now. Preserve it; a separate locked environment and focused validation is the smallest safe repair, requiring a later authorized change/install step.
- **Docker unavailable:** version, Compose-project, container and volume inventory commands each exited 1 because the Linux-engine named pipe was absent. This does not prove there are no retained projects/volumes. Starting Docker was not authorized/executed. Docker is unnecessary for the native route but mandatory for assessing the Compose route and its persistent volume.
- **Operational destination unresolved:** current environment has no `MARITIME_DATA_DIR`; bare run would use `data`. Documented `data/live` does not exist. Default DB is schema version 0 and would be initialized/migrated to version 1. It has 1,410 cache rows through Oct 2, zero duplicate cache keys and a prior published run. Owner must choose a target and approve the persistent effects; no migration was run.
- **Target recovery and concurrency not established:** no verified backup/restore receipt for the chosen current target; full current audit-chain/product-manifest verification is not established by SQLite quick_check. Writer absence is not proven by an empty process snapshot. No capacity budget, total-run timeout, real-time observer or stop authority has been assigned for an unrestricted native backfill/ML run.

## Gate summary

| Gate | Status | Evidence and scope |
|---|---|---|
| A. Repository/environment identity | PASS | `preflight.json`: 146 source hashes match Oct 17 release, current Python/version inventory and dirty Git baseline. This does not pass dependency or runtime gates |
| B. Dependencies/configuration/runtime | BLOCKED | Current package inconsistency; Docker unavailable; no API credentials configured if serving is included. Config/registry/10-day contract inspected without changes |
| C. Database/schema/storage | BLOCKED | `database-readonly.json`: current files quick-checked read-only; default version 0, target unselected, Docker volume unavailable. About 89 GB free on C is observed, not an approved peak-run/backup budget |
| D. Source availability/contracts/freshness | NOT_TESTED | Current-day bounded six-port freshness subcheck passes, but full reference/activity contract and complete run-window reconciliation/weather path not freshly exercised; no large acquisition authorized |
| E. Data quality/lineage/accounting | NOT_TESTED | Source unchanged and historical campaign/assertions retained; current complete candidate input not acquired or validated. Do not infer current runtime pass from tests |
| F. Checkpoint/idempotency/publication safety | BLOCKED | Static path established; cache duplicates inspected. Target/writer/recovery scope unresolved; checkpoint advances after DQ even on later failure; CLI rerun creates a new attempt |
| G. Monitoring/resource readiness | BLOCKED | `host.json`: bounded process/listener snapshot, free disk; logs/run IDs implemented. No current managed run observer, memory budget, run deadline or verified current API readiness |
| H. Isolated failure/recovery evidence | PASS | Prior Oct 17 Docker outage 503/recovery 200/restart and local backup restore, plus injected invalid-coordinate/partial-persistence blocks. PASS is for availability of those isolated historical results, not recovery of current target |
| I. Exact command/effects/stop plan | PASS | Source-traced `EXECUTION_PLAN.md`; startup writes, cache timing, publication transaction and interruption limits explicitly identified. Owner execution authorization still absent |

Mandatory BLOCKED and NOT_TESTED gates compel NO-GO. Freshness alone is not the blocker and cannot clear the other gates.

## Source evidence boundary

Reused the actual bounded official requests executed minutes before this audit at 2026-10-18T05:35:19–05:35:29Z, not yesterday's pass: `../portfolio-release-20261018-083345/freshness.json` and six raw responses. Singapore, Rotterdam, Shanghai, LA–LB, NY–NJ and Jebel Ali each returned **2026-10-09**, age **9 days** as of Oct 18, within the unchanged 10-day limit. Request dates are not observation dates. Raw hashes are included in this manifest's verification. No repeat request was necessary. At age 11 on Oct 20 the same dates must fail unless new source observations arrive. Local default cache remains Oct 2, age 16; the check did not update it or establish application readiness.

## Database inspection method and limits

An initial in-memory deserialize could not query WAL-format images and recorded OperationalError; that is an inspection-method limitation, not proof of database corruption. Follow-up `database_readonly.py` used SQLite URI `mode=ro&immutable=1` only for absent/empty WAL, query_only, main-file hashes before/after and an empty-WAL recheck. No Store constructor, migration, WAL checkpoint or write connection was used. Results include versions, tables, status counts, cache key/count/latest date/duplicates and orphan/unchained counts when tables exist. This cannot establish full cryptographic audit integrity, all release hashes or exclusive ownership; immutable reads are unsuitable for a live writer or nonempty WAL. All inspected source main hashes stayed stable and WAL remained empty; consult each row for scope.

The host inventory showed no selected Python/Docker processes or listeners on 8000/18081/5432/6379. Its visibility is not proof of global writer absence. Optional-source failures are declared degraded; owner must decide whether this counts as the desired full operational scope. Cloud execution is NOT_APPLICABLE for the explicit local backend, not silently passed.

## What is needed next

1. Owner selects native versus Compose and the exact data root/project/volume; prefer a new dedicated operational root over the broad legacy `data` tree. Authorize the intended backfill and any schema changes separately.
2. Create a separate lockfile-based environment without deleting the existing one; clear dependency checks and verify the selected source/interpreter. For Compose, owner starts Linux Docker and permits fresh read-only project/volume inspection before any run.
3. Establish a verified backup/restore for an existing target, current publication/audit/checkpoint checks, writer exclusion, disk/memory/run-time budget and stop/recovery ownership. Do not stop existing services or copy mutable databases without approval.
4. Authorize a bounded isolated preflight of complete required source contracts/window/counts and DQ, then reassess. If that requires persistent writes or broader acquisition, it is a separate action; it was not smuggled into this audit. Recheck freshness at launch time.

No full test/release campaign was repeated. One shell read command had a PowerShell syntax error (exit 1, no execution), then succeeded after correction. The first new helper had a syntax error (exit 1, no checks); `preflight-02.log` preserves the successful capture run (exit 0) with internal Docker/dependency failures. `database-readonly` exited 0. A helper exit 0 means evidence captured, not all gates passed. No credentials were printed; environment checks record presence only. Reports/logs include local paths and should remain private pending publication review.
