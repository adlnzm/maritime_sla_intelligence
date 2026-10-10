# Executable governance and release scope

The baseline is `0fb0836`; see [the gap analysis](governance-gap-analysis.md). The authoritative
versioned contract is `configs/governance.json`, also packaged inside the wheel for Fabric.
Unknown versions, product names, top-level field/type changes and mandatory stage omissions fail
closed. Contract changes require code review, regression tests and a new evidence run.

## Boundaries

Acquisition reconciles ArcGIS count queries with pagination, rejects repeated pages, unexpected
empty critical extracts, duplicates and conflicting checkpoint entities. HTTP retries are bounded;
exhaustion opens a circuit for that source for the rest of the run. Raw payload hashes are checked
on reuse. Incremental acquisition explicitly accounts for revision-window replacement and expired
history. Optional sources have an explicit declared-degraded policy, carried into every output.

Silver uses canonical models and disjoint per-record dispositions. A record with multiple failed
checks is rejected once and has all its reasons retained. Referentially invalid records cannot
enter clean collections. The invariant is received = accepted + rejected + quarantined; this
implementation rejects invalid canonical records and uses zero for quarantined, while retaining
their original input evidence and a disposition index. Missing dates within each observed span,
inconsistent latest dates, future records and stale datasets block the stage.

Current metric baselines and z-scores are independently recomputed using scalar statistics before
scenario execution. Gold checks product keys, types, classes, dependency fingerprints, coverage,
scenario accounting, expected-loss formulas and rankings. Source activity is a call-count estimate;
the indicator is an activity-deviation proxy, never a waiting-time or dwell-time observation.
Network calculations involving synthetic topology remain SIMULATED, with component classes and
fingerprints preserved. Local forecasts are PREDICTED research results, not approved SLA models.

Acquisition, Bronze, Silver, metrics, scenarios, features/ML, Gold and publication each expose
PASS, PASS_WITH_WARNINGS, BLOCKED or NOT_EVALUATED. Only named warnings in the contract are
permitted. A mandatory failed or missing check blocks dependent execution. Each stage records a
stable execution ID, timestamps, attempt, checks, counts and terminal outcome in the audit ledger.
SQLite publication verifies persisted content and atomically inserts the release, terminal run
report and published pointer. SQL triggers prevent ordinary update/delete of released products,
release records and audit records. Hash-chain checks detect altered audit content. A database/file
administrator can defeat these local controls; they are not tamper-proof storage or certification.

An OS file lock prevents concurrent local writers. A successful same-ID retry with identical
request fingerprint returns the same approved release; conflicting reuse fails. Reacquiring the
lock reconciles stranded RUNNING records as ABANDONED before a new run. Failed attempts remain
inspectable. Read APIs require an approved manifest and verify the product hash; explicit run IDs
cannot expose unapproved data. Live snapshots age out for serving; historical replays retain their
declared historical semantics. Existing pre-governance snapshots are not silently grandfathered.

## ML, GenAI and cloud

Feature assets require observed input, unique entity/date keys, known feature contract and hashes;
the CSV is recomputed before use to detect feature computation skew. Chronological folds and
holdout logic are retained. Azure ML candidates require explicit eligible-version promotion.
Prediction imports require the exact expected port/date set, one model version, schema,
classification, finite intervals, timestamps, input/output hashes and approved registry/job
lineage. Import manifests are trusted-runner attestations, not cryptographic signatures or proof
that cloud execution happened locally. Restricted cloud write identities must be independently
verified. Fabric imports verify Delta content, then create a child release identity.

Fabric stage receipts supplement Data Factory task status; dependency failure blocks downstream
notebooks. Delta writes verify content with bidirectional differences, not row counts alone.
These adapters remain environment-dependent until executed with actual Spark/Delta and tenant
permissions. Publish predictions before serving a run: Azure serving refuses to change an already
approved run ID. Use a new Fabric run for a changed serving release.

GenAI enforces a strict response envelope and exact source spans. Evidence records deployment,
returned model identifier when available, prompt version, time and source hash. Self-reported
confidence is explicitly uncalibrated. Signals remain ANTICIPATED/UNCONFIRMED; no automatic
promotion to OBSERVED is implemented. Synthetic outcomes remain SIMULATED, and SLA ML remains
DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA.

## Reproduce the evidence

Run from the repository root after creating the environment; on Windows set `PYTHONPATH=src`
and `PYTHONUTF8=1`. The clean campaign refuses existing data/output directories.

```powershell
uv sync --frozen --no-editable --extra dev --extra azure --extra fabric --extra ml
$env:PYTHONPATH='src'
$env:PYTHONUTF8='1'
python -m pytest -q --junitxml=evidence/governance-tests.xml
python scripts/governance_release.py --root data/governance-clean --output evidence/governance-release --as-of 2026-10-10
python scripts/validate_release.py
docker build -f docker/Dockerfile -t maritime-sla:governance .
docker run --name maritime-governance-check maritime-sla:governance python scripts/container_smoke.py
docker cp maritime-governance-check:/app/data/container-evidence.json evidence/docker-governance.json
```

The campaign declares thresholds before running: three successful runs, two injected failures,
balanced accounting, unchanged prior publication after failure, audit verification and independent
metric agreement. Failure injection is test evidence, not source observation. This bounded campaign
does not establish sustained production reliability. Latency/availability/resource SLOs and
retention decisions require agreement with the operational owner; no business targets are invented.

## Final industrial gate

The local evidence pack separates operational OBSERVED/DERIVED data, SIMULATED data, PREDICTED
data, metadata and raw evidence. It includes contracts, fingerprints, acquisition-to-output lineage,
reconciliation, stage receipts, failed attempts and reproduction details. Its top-level industrial
release remains BLOCKED while any mandatory external control is NOT_EVALUATED. Local analytical
PASS_WITH_WARNINGS must never be displayed as industrial production approval.

Outstanding tenant verification follows [Azure deployment](azure.md) and [Fabric deployment](fabric.md):
execute Fabric ingestion/Delta acceptance; train/evaluate/register/promote an actual Azure ML job;
return a complete prediction bundle and preserve readback; publish the serving copy; test Entra
reader/operator denial cases, managed identities, Key Vault, telemetry and Power BI refresh.
Retain actual job IDs, token-free permission evidence, immutable-retention configuration and
unauthorized mutation/delete tests. Agree source usage/retention and production SLOs, then run
a representative sustained campaign. Local tests, Docker or Bicep compilation do not satisfy these
controls. Until then, deliver diagnostics and scoped analytical evidence only.
