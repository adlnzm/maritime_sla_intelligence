# Code integration report

**CODE-INTEGRATED AND VALIDATED** — implemented local analytical scope, with the offline cloud adapter contract coverage explicitly bounded below. This is not live runtime, cloud-service, Power BI engine, or production verification.

Assessment time: 2026-10-22T10:30:40.174145+03:00 (Asia/Qatar). Branch `codex/build-maritime-platform`, commit `4b50f50769b08e763015064c53d91b6bda4ae079` remain unchanged. The existing audit's 49 components were traced using actual source, contracts and callers; see COMPONENT_INTEGRATION_MATRIX.json for every classification and test link.

## Project preservation

Branch, SHA and complete tracked/untracked/ignored Git status were recorded before source edits in `branch-before.txt`, `commit-before.txt`, and `git-status-before.txt`. The workspace was already dirty. Existing unrelated modifications, data, checkpoints, environments, ignored files and historical evidence were retained. No reset, clean, checkout, branch switch, commit, push, tag or Git release occurred. No application services, deployment, unrestricted pipeline, existing persistent database or external system were operated. Test pipelines and backup/restore ran only on disposable roots. External HTTP/SDK responses were mocked; the runner blocked outbound sockets and removed cloud/telemetry settings from its own process.

Windows' sandbox stalled asyncio's internal loopback socket-pair setup. Those test processes were stopped; bounded test runs succeeded with loopback available outside that sandbox, retaining the runner's external-network guard. No application server was started.

## Changes made in this task

- `src/maritime/api.py` — Map SQLite/OS/Azure dependency exceptions to redacted 503 responses while retaining correlation IDs and liveness.
- `src/maritime/azure_store.py` — Validate account/container configuration before identity access; pin approved reads; verify destination content before publication; complete interrupted pointer updates without rolling back newer snapshots.
- `src/maritime/fabric_runtime.py` — Validate task run/contract/stage/latest-attempt dependencies; generate, persist and include returned prediction/decision-evidence field lineage in the release.
- `src/maritime/pipeline.py` — Declare forecasts unused for recommendation ranking using the existing decision field contract; trace supplemental forecast evidence to predictions.
- `scripts/deploy_fabric.py` — Inject real HTTP/identity interfaces for testing, reject unexpected request URLs, bound malformed Retry-After handling, retry safe reads on transport failure, propagate ambiguous mutating-call failures.
- `scripts/azure_ml.py` — Validate required cloud configuration before optional SDK import or credential construction.
- `pyproject.toml` — Explicit source-distribution inputs prevent retained evidence/environments from entering package builds.
- `tests/test_code_integration.py` — 22 parameterized integration/regression cases across acquisition, cloud serving, API failure, Fabric tasks/REST/forecast return, ML configuration, freshness and forecast isolation.
- `tests/test_fabric_assets.py` — Generate all six notebooks in a temporary directory and compare with retained assets.

These are task-specific descriptions, not a claim that the entire Git diff belongs to this task. Several edited files already contained user changes. The existing governance JSON is byte-identical to Git HEAD; no freshness/schema-fingerprint migration was introduced. Existing historical release contracts therefore remain unchanged.

## Connected and exercised paths

1. Mocked ArcGIS HTTP acquisition -> production Fetcher/count reconciliation -> normalization -> DQ/quarantine -> incremental checkpoint -> analytics/scenarios -> verified SQLite/Gold publication -> authenticated API/report/freshness responses. Replay paths separately exercise successful API reads and observed-history model training.
2. Revised/deleted source records, duplicate inputs, exhausted timeouts, invalid configuration, stale observations and interrupted persistence -> retained failed report -> previous publication preserved.
3. Graph/scenario outcomes -> recommendations, with forecasts explicitly separate from ranking. Changed forecast values leave actions and benefits unchanged; forecast failure prevents new publication. Simulated shipments remain simulated and observed commercial SLA training remains deferred.
4. Fabric task dependency/attempt receipts -> guarded task invocation/result/error. Real prediction import -> validated manifest -> mocked Delta boundary -> supplemental decision evidence -> newly connected field lineage -> release hashes -> real AzureStore code over fake Blob clients.
5. Blob endpoint/container configuration -> real credential injection point -> timeouts -> verified destination readback -> published pointer -> pinned approved reads. Interrupted pointer publication is recoverable; corrupt destinations cannot publish; replay of an older completed run cannot roll back a newer snapshot.
6. API -> local/cloud data-access failure -> redacted 503 plus correlation ID; health remains available. Review/outcome/audit/export, request limits, simultaneous publication and recovery retain existing regression coverage.
7. Gold mart contracts -> generated reporting assets, and parameterized notebook generators -> six retained notebook definitions. Source distribution and wheel build from the final source without sweeping retained evidence into the package.

## Validation

- **85 passed, 0 failed, 0 errors, 0 skipped** in the final full suite (`verified-tests.xml`, `verified-tests.log`).
- Ruff lint and configured formatting checks pass for `src tests scripts`.
- All 22 application modules import; 51 Python files parse.
- Clean frozen/offline validation environment: 85 installed packages compatible. Existing `.venv` was not repaired or replaced.
- Source distribution and wheel build pass; archive inspection verifies the wheel's source/governance bytes and excludes evidence/environment content from the source distribution.
- Six generated notebooks match retained assets; reporting test checks 29 PBIR files and governed field bindings.
- No static type checker is configured. One existing Starlette/httpx deprecation warning remains; it is not suppressed.

See END_TO_END_TEST_RESULTS.md for commands, intermediate attempts and actual outcomes. `source-hashes.json` binds final validation to source/config/assets. Final build outputs are validation artifacts, not a release.

## Scope decisions and limits

Required local data, analytical, persistence, orchestration, API, audit, recovery, model-research and reporting-asset paths are connected. Optional reference URLs, trade context, recurring scheduling and a custom UI remain optional/deferred. Forecast-to-ranking coupling and observed commercial shipment-SLA ML were not added.

Cloud interfaces remain conditional on the existing optional deployments. Mock contract tests do not certify Spark/Delta semantics, Azure SDK/service operation, IAM, OneLake transfer, managed identities, concurrent Blob publication, reporting-engine evaluation, model approval, alerts or production operation. The matrix states where a cloud portion was inspected rather than executed. All deployment/operational gaps remain explicit in UNRESOLVED_INTEGRATION_GAPS.md.
