# Final acceptance — 14 October 2026

**LOCAL_RELEASE_READY = NO**
**PRODUCTION_READY = NO**

The full release is not accepted. Live acquisition returned stale PortWatch observations and correctly failed six freshness checks. All 50 automated tests and the Docker workflow passed, but those successes do not override the failed live campaign.

Git revision: `4b50f50769b08e763015064c53d91b6bda4ae079`. Dirty source preserved; 146 source/configuration/documentation files hashed. No commit or reset was performed.
Campaign: `evidence\local-release-20261014-final`. Final status: `NOT_READY`. Source equality and 74 evidence-file hashes plus ZIP contents independently verified. See `verification.json` for lock/archive hashes.

Tests: 50; failures 0; errors 0; skipped 0. One Starlette/httpx deprecation warning. Unit, local integration/E2E, concurrency/publication, security boundaries, governance, inference integrity and actual filesystem/SQLite recovery are covered; cloud contracts use test doubles and do not certify cloud execution.

## Executed command gates

| Gate | Exit | Evidence |
|---|---:|---|
| git-diff | 0 | `evidence\local-release-20261014-final\git-diff.log` |
| clean-install | 0 | `evidence\local-release-20261014-final\clean-install.log` |
| tests | 0 | `evidence\local-release-20261014-final\tests.log` |
| package-consistency | 0 | `evidence\local-release-20261014-final\package-consistency.log` |
| lint | 0 | `evidence\local-release-20261014-final\lint.log` |
| format | 0 | `evidence\local-release-20261014-final\format.log` |
| build | 0 | `evidence\local-release-20261014-final\build.log` |
| powerbi | 0 | `evidence\local-release-20261014-final\powerbi.log` |
| fabric-assets | 0 | `evidence\local-release-20261014-final\fabric-assets.log` |
| bicep-version | 0 | `evidence\local-release-20261014-final\bicep-version.log` |
| bicep | 0 | `evidence\local-release-20261014-final\bicep.log` |
| dependency-export | 0 | `evidence\local-release-20261014-final\dependency-export.log` |
| dependency-audit | 0 | `evidence\local-release-20261014-final\dependency-audit.log` |
| docker | 0 | `evidence\local-release-20261014-final\docker.log` |
| live | 1 | `evidence\local-release-20261014-final\live.log` |

Docker `maritime-demo-08571d8c19`: clean no-cache/pull build, seed completion ordering, health/readiness, real HTTP auth/roles/body boundaries, actual database outage (503) with liveness (200), dependency recovery, restart/run identity, audit persistence and backup/restore passed. Runtime UID 10001, zero effective capabilities, no-new-privileges, read-only root and 1 GiB/1 CPU/128 PID API limits verified. Containers are stopped; disposable volumes retained.

Package consistency checked 112 installed packages. Python dependency audit reported zero known vulnerabilities, with two advisory no-deps/hash warnings. Lint, format, wheel/sdist build and generated notebooks passed. Bicep compilation completed without warnings. PBIR validation covered 29 files and five pages against vendored official schemas; Desktop/model/refresh remain blocked.

Backup/restore used actual disposable data. SHA-256, SQLite integrity, approved products/publication and audit chains were validated. Tests reject existing/overlapping destinations and corrupt input before creating a restore destination. This is local functional recovery, not disaster recovery, offsite durability or production RPO/RTO.

Root cause of the 11 October failure: missing Docker Desktop Linux engine pipe; no image build occurred. Cleanup then masked the original error and omitted Docker result evidence. Engine startup and evidence-finalization handling were corrected. Health now probes readiness, and logging no longer rereads a failed database or attributes an old response to a newly published run. Three concurrent publication regression cases use real SQLite publication and verify reads/review/outcome audit identities.

Final live failure: all six ports latest 2 October versus requested 14 October, exceeding the unchanged 10-day freshness limit. Failed reports and raw responses are retained under live/failed-reports and live/failed-bronze. No stale run was published. Prior interim campaigns remain preserved and are not evidence of final-source acceptance.

## Requirement acceptance matrix

PASS below means only the stated executed local scope. BLOCKED cloud rows require target evidence before production acceptance.

| ID | Requirement | Status | Evidence and remediation/scope |
|---|---|---|---|
| SRC-01 | Registered source identity, schema, classification and acquisition provenance | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SRC-02 | PortWatch paginated, count-reconciled acquisition with timeout/retry and retained failures | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SRC-03 | Incremental overlap, source revisions and expired-row accounting | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SRC-04 | Optional WPI, UN/LOCODE and reference route adapters | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Optional approved source downloads/URLs absent; configure and execute WPI, UN/LOCODE and reference geometry. |
| SRC-05 | Public weather acquisition retained as DERIVED reanalysis | PASS | `evidence\local-release-20261014-final\live\failed-reports` — Weather acquisition succeeded; the overall live publication failed activity freshness. |
| BRZ-01 | Immutable-content raw retention, checksum verification and replay | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SLV-01 | Canonical types, ranges, coordinates, temporal validity, stable IDs and UTC | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SLV-02 | Exclusive persisted/duplicate/rejected/quarantined/failed dispositions | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SLV-03 | Completeness, duplicates, FK, freshness and consecutive coverage gates | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-01 | Five classifications preserved across all downstream products | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-02 | Queryable field lineage and product/feature/config fingerprints | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-03 | Continuous stage gates and immutable approved publication | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-04 | Single writer, replay idempotency, interrupted-run recovery | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-05 | Append-only audit, hash chain and approved-product SQL protection | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GOV-06 | Production retention enforcement and administrator separation | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Owner-approved retention/lock and effective target permissions/expiry evidence required. |
| DET-01 | 56-day historical baseline, deviation/rank, persistence and stress categories | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| DET-02 | Independent recomputation prevents corrupt metrics reaching decisions | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| NET-01 | Time-valid network state, availability, closures, stress and alternatives | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| NET-02 | Bounded temporal propagation and downstream exposure with assumptions | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SCN-01 | Seeded synthetic shipments, promised delivery, buffer, priority and cargo | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SCN-02 | Five counterfactual interventions with paired outcome distributions | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SLA-01 | Non-ML expected delay, breach probability, loss and priority exposure | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| SLA-02 | Observed shipment SLA training | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Deferred by design: representative observed shipment outcomes and label approval unavailable. |
| ML-01 | Lagged/versioned features, preprocessing and provenance | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| ML-02 | Candidate search, chronological/walk-forward selection and error evaluation | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| ML-03 | Calibration intervals, drift and port-call batch predictions | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| ML-04 | Azure ML jobs, tracking, registry/version/promotion and monitoring | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Azure ML workspace, compute/quota, runner permissions and real jobs/registration/promotion required. |
| ML-05 | Feature/model compatibility and verified predictions returned to Fabric | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Local inference contracts passed; real prediction return and Fabric Delta readback still required. |
| GEN-01 | AOAI extraction verifies exact quote/event/location/time evidence | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| GEN-02 | Authenticated Azure OpenAI service round trip | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Authorized Azure OpenAI endpoint/deployment, identity, quota and real round trip required. |
| DEC-01 | Cost/loss ranked feasible interventions and deterministic explanation | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| DEC-02 | Operator accept/reject/feasible override with reason and audit | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| LRN-01 | Actual-vs-modeled error, Brier score, recommendation adherence | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| LRN-02 | API learning audit transferred into Fabric analytical marts | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Local transfer/replay passed; actual Fabric notebook and persisted readback require target access. |
| API-01 | Authenticated paginated product endpoints and OpenAPI interface | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| API-02 | Startup configuration failure and request correlation IDs | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| API-03 | Readiness rejects missing/unapproved/stale/corrupt products | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| FAB-01 | Lakehouse Bronze/Silver/Gold PySpark and governed Delta readback | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Notebook generation/contracts passed; actual capacity, Spark and Delta execution required. |
| FAB-02 | Data Factory dependencies, parameters, retry gates and deployment | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Static orchestration contracts passed; actual deployment/job execution required. |
| BI-01 | Dimensional marts, SQL views, DAX, Power Query and GIS export | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| BI-02 | Five Power BI report pages and deployed semantic model | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — 29 PBIR files/5 pages validated; Desktop rendering, real model binding, RLS and refresh/publish required. |
| AZ-01 | Azure container application, Entra, Key Vault and Monitor | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Bicep compiled; tenant/resources/identity/secrets/network and deployed authentication tests required. |
| OPS-01 | Structured logs, health, pipeline/DQ/API operational metrics | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| OPS-02 | Actionable cloud alerts and workload-grounded SLOs | BLOCKED | `evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md` — Named owners/contacts, approved targets, deployed alert rules and received notifications required. |
| OPS-03 | Reproducible locked dependencies and documented startup | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| OPS-04 | Clean isolated demo, authenticated E2E and restart persistence | PASS | `evidence\local-release-20261014-final\docker\maritime-demo-08571d8c19\result.json` — Real clean Compose build/start, HTTP, dependency failure/recovery, restart and persistent audits passed. |
| OPS-05 | Safe shutdown/reset/recovery and retained evidence | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| OPS-06 | Dependency/security checks and reproducible quality evidence | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| OPS-07 | Configuration failures retained before acquisition | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| ARCH-01 | Fabric data plane / Azure ML / Azure OpenAI / Azure application boundary | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| ARCH-02 | PostgreSQL persistence | NOT RUN | `evidence\local-release-20261014-final\tests.xml` — PostgreSQL is not an implemented or selected backend; SQLite local and Azure Blob target remain the declared architecture. |
| PC-01 | Idempotent operator writes and complete audit chain verification | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| PC-02 | Feedback destination preserves prior events on replay | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| PC-03 | Executable backup and verified restore | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| PC-04 | Versioned safe database initialization | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| PC-05 | Bounded GenAI service failures and input/resource limits | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| PC-06 | Evidence matches source executed by release checks | PASS | `evidence\acceptance-20261014\verification.json` — Final source hashes, all manifest entries and ZIP bytes independently verified. |
| PC-07 | Authored Power BI report assets | PASS | `evidence\local-release-20261014-final\tests.xml` — Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim. |
| LIVE-FRESHNESS | Current public-data release campaign | FAIL | `evidence\local-release-20261014-final\live\failed-reports` — Latest PortWatch observations are 2026-10-02 for all six ports, 12 days old against the unchanged 10-day gate. Obtain fresher source data, then rerun the complete campaign; do not relabel replay as live. |
| LIVE-FOLLOWUP | Post-publication live replay/failure campaign | NOT RUN | `evidence\local-release-20261014-final\live\release-validation.json` — Initial live DQ blocked publication before these steps. Restore fresh source input and rerun. |
| OFFSITE-DR | Offsite backup/failover and approved production RPO/RTO | BLOCKED | `docs/operations/deployment_acceptance.md` — Owner, targets, offsite destination, recovery identity and target restore/failover execution required. |
| IMAGES | Application independence from optional image generation | PASS | `evidence\local-release-20261014-final\docker\maritime-demo-08571d8c19\result.json` — No images generated and no image-generation service/dependencies/assets added; clean build/runtime independent of such an environment. |
| OS-SCAN | Container operating-system vulnerability scan | NOT RUN | `evidence\local-release-20261014-final\dependency-audit.log` — Existing repository audit covers Python dependencies. OS-layer scanning is not configured; do not infer an OS vulnerability pass. |
| TYPECHECK | Dedicated static type checker | NOT RUN | `pyproject.toml` — No standalone type checker is configured; lint/build/runtime contracts were executed. |

## Deployment handoff and limitations

Use `docs/operations/deployment_acceptance.md` in order for required values, least-privilege roles, owner actions, commands, expected evidence and rollback. Read-only preflight exited 1: Azure CLI and all required tenant/subscription/resource/Fabric/AML/OpenAI settings were absent. Install Azure CLI and configure/authenticate the approved target before running its preflight; process-local PowerShell execution may require `-ExecutionPolicy Bypass` under the local execution policy.

All Azure deployment/Entra, Fabric, AML, Azure OpenAI, Power BI Desktop/service, locked retention/expiry, effective denial, alert delivery, offsite recovery/failover and SLO gates are BLOCKED — DEPLOYMENT ACTION REQUIRED. Network/private registry configuration and final report/model setup remain target configuration work. No retention approval, operational owner, production model approval, RPO/RTO or performance target has been invented.

Shipment-SLA ML remains deferred. Port calls are activity proxies, not measured waiting/dwell times; reference geometry is not observed vessel traffic; simulated shipment losses/labels are not commercial outcomes. Port-call forecasts do not validate shipment-SLA prediction.

To re-attempt acceptance: obtain fresh PortWatch input, keep the 10-day contract unchanged, and execute `python scripts/production_release.py --output evidence/<new-unique-directory> --live`. Require all gates, unchanged source and verified manifest before changing the local claim to YES. Production additionally requires every target gate and owner approval.
