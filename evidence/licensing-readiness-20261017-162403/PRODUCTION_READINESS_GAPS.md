# Production-readiness gap assessment

As of 17 October 2026 (Asia/Qatar). **PRODUCTION_READY = NO.** Existing evidence supports the completed local release acceptance, not a deployed production service. No full campaign, cloud operation or source acquisition was repeated for this documentation task. Current source hashes are checked against the saved campaign in `evidence-manifest.json`.

Baseline revision: `4b50f50769b08e763015064c53d91b6bda4ae079`, branch `codex/build-maritime-platform`, dirty working tree retained. New files are confined to this assessment directory. Old reports and ignored artifacts were not reset, cleaned or rewritten. Git inventories and source integrity have a narrower scope than a full hash of every ignored environment/database file; no blanket content-hash claim is made for those files.

Status definitions: **PASS** means a specifically bounded capability demonstrated by retained observations/assertions; **BLOCKED** means a named missing prerequisite prevents acceptance; **NOT_TESTED** means no sufficient execution evidence was found; **NOT_APPLICABLE** means outside the current declared scope, not an implicit pass. Historical local PASS is not a perpetual service guarantee.

## Evidence reference key

All paths below are repository-relative and refer to existing files, not proposed evidence.

- **R**: `evidence/local-release-20261017-freshness-01/` — `result.json`, `tests.xml`, `tests.log`, command logs, `evidence-manifest.json`.
- **D**: `evidence/local-release-20261017-freshness-01/docker/maritime-demo-4836fad43b/` — `result.json`, `backup-restore.json`, `audit.json`, command logs.
- **L**: `evidence/local-release-20261017-freshness-01/live/release-validation.json` — acquisition/replay/fault campaign and separate industrial blockers.
- **F**: `evidence/freshness-diagnosis-20261017-131acd0c/diagnosis.json`, `FINDINGS.md`, independent raw latest-port responses.
- **V**: `evidence/official-source-assessment-20261017/verification.json` and `FINAL_REPORT.md` — 146 source/111 evidence/archive checks and prior acceptance conclusion.
- **T**: `evidence/trade-qualification-20261017-160824/ASSESSMENT.md`, `verification.json`, `tests-authorized.xml`, `sample-verification.json`.
- **H**: `docs/operations/deployment_acceptance.md` — exact target commands, prerequisites, roles, expected results and rollback. **O**: `docs/operations/production_closure.md` — unassigned owners, retention and recovery obligations.
- **P**: `evidence/local-release-20261017-freshness-01/cloud-preflight.json` — saved environment lacked tenant/subscription/workspace/endpoint settings and Azure CLI. This is historical preflight, not a fresh inspection of available credentials.

The older `docs/requirements/production_acceptance.json` is dated October 11 and references a 39-test baseline. It is a requirement inventory, not the latest acceptance result. Do not present those stale counts/statuses as current verification; this assessment uses October 17 evidence without modifying historical files.

## Engineering, data and rights

| Item | Status | Actual evidence and boundary | Next action |
|---|---|---|---|
| Local automated regression | PASS | R `tests.xml`/`tests.log`: 63 tests, no failures/errors/skips; one Starlette/httpx deprecation warning. T later focused source/governance run: 28 passed, same warning. Assertions substantiate only exercised cases | Preserve exact source/lock binding; plan warning remediation separately, no dependency change here |
| Local build/lint/format/package consistency | PASS | R `build.log`, `lint.log`, `format.log`, `package-consistency.log` and recorded exits; package built and checks completed | Repeat after relevant source/dependency changes |
| Python dependency audit | PASS | R `dependency-audit.log/json`: no known vulnerabilities in scanned resolved dependencies; two `--no-deps`/hashing advisories | Refresh before deployment; do not equate with container OS/image, licence or penetration audit |
| Container OS vulnerability and public-endpoint security assessment | NOT_TESTED | R dependency audit covers Python; D security checks cover runtime configuration, not a complete image/CVE or external penetration assessment | Scan final image digest, review findings and test intended public attack surface |
| Real local Docker runtime and recovery | PASS | D result: no-cache/pull build and Compose startup, nonroot/capability/resource/read-only checks; dependency outage readiness 503 while liveness 200; recovery/restart readiness 200, persistent audit | Repeat equivalent checks on the deployed revision; local replay uses retained public data with simulated shipments |
| Local auth, roles and request boundaries | PASS | D result: no-token 401, Reader write 403, malformed review 422, oversized body 413; successful authorized review/retry | Entra target identity is separate gate below |
| API publication consistency and integrity | PASS | R full test results include publication-race/consistency coverage; D decisions/audit and L publication preservation/accounting/audit checks | Preserve same-run attribution; test deployed publisher/storage interaction |
| Live acquisition, replay and failed-run isolation | PASS | L campaign checks successful runs, expected invalid-coordinate/partial-persistence blocks, retained prior publication and recovery; `mandatory_failed_controls=[]` | Retain failures, reconciliation and run identity in real Fabric deployment |
| Six-port freshness on October 17 | PASS | F: each Singapore, Rotterdam, Shanghai, LA–LB, NY–NJ, Jebel Ali latest source date Oct 9, age 8 days; fixed limit 10. Oct 14 failure with Oct 2 observations remains valid | Refresh before serving; absent newer observations Oct 20 is age 11 and must block. Retrieval time must never replace observation date |
| Sustained source freshness / availability guarantee | NOT_TESTED | F and L are point-in-time checks, not an upstream delivery SLA or longitudinal monitoring record | Measure observation lag and source failure rates; define alert owner and sustained evidence window |
| Classification and business semantics | PASS | T assessment plus L governed outputs: national trade remains separate; no trade adapter; synthetic shipments remain scenarios, reference geometry is not observed traffic | Review public copy/visuals: activity is not measured waiting/dwell; forecasts are port-call forecasts |
| PortWatch and other existing-source public redistribution rights | BLOCKED | `evidence/official-source-assessment-20261017/international.md` / `ports.md`: public access demonstrated, complete production reuse entitlement not established | Data owner reviews source-specific licences, attribution and public raw-evidence rights before publication |
| UN Comtrade mixed/public/paid use | BLOCKED | T real annual sample; current official review in `LICENSING_DECISION.md`; applicability unresolved | Owner reviews draft and authorizes sending if desired; retain applicable written clarification, not silence |
| WTO integration access and rights | BLOCKED | T retained 401, no usable authenticated row, no qualified product entitlement | If needed, obtain authorized access and rights, then bounded sample and metadata; no substitution for PortWatch |
| Trade-context runtime adapter under option B/C | NOT_APPLICABLE | No provider integrated; recommendation is research and a source link only | If A is selected later, qualify data contract and add independent adapter/tests before use |
| Evidence integrity / source binding | PASS | V verified source, directory and archive; T preserved source; current `evidence-manifest.json` records before/after source comparison and input hashes | Public evidence needs separate secrets/rights review; a checksum proves content integrity, not truth or permission |

## Deployment, operations and reporting

| Item | Status | Evidence and precise gap | Next action / acceptance evidence |
|---|---|---|---|
| Bicep and PBIR static validation | PASS | R `bicep.log`/`azure-template.json`; `powerbi.log`: 29 JSON files, five pages, schema-only, runtime not executed, binding requires real semantic model | Keep static checks; do not call compilation a deployment or rendering success |
| Azure resources / production application | BLOCKED | P missing configuration; H requires target IDs, region, image digest, registry and network policy; no target provisioning evidence | Owner supplies tenant/subscription/RG/region and authorized deployment identity; follow H validation/what-if/deploy and health/readback; retain resource/revision IDs |
| Network/TLS/registry production configuration | BLOCKED | H says template has TLS ingress but private endpoints/firewalls/private registry access are not fully configured | Approve ingress/egress and registry policy, configure restrictions and verify effective target access before exposure |
| Entra authorization and managed identities | BLOCKED | Local role tests are not target Entra/RBAC enforcement; P/H lack target acceptance | Configure audience/Reader/Operator roles and least-privilege identities; test wrong/expired token, wrong role and real permitted actions; retain redacted effective permissions and denied results |
| Secret management / rotation | BLOCKED | H documents Key Vault/platform references; no effective target identity, rotation or leakage test evidence | Store authorized secrets outside repository, prefer managed identity, verify access denial/rotation, sanitize logs; review public archive before release |
| Fabric runtime and feedback persistence | BLOCKED | L mandatory control `fabric_runtime_and_readback` unevaluated; generated assets are not executed notebooks | Supply capacity/workspace/lakehouse/permissions; H deployment and actual terminal jobs, Delta readback/counts/hashes, replay/failure receipts |
| Azure ML lifecycle / model approval | BLOCKED | L `azure_ml_lifecycle_and_return` unevaluated; no approved production model | Run authorized train/evaluate/register/batch/return sequence; named approver reviews actual metrics and artifact hashes; retain real job/model versions |
| Shipment-SLA ML | NOT_APPLICABLE | O defers by design: no representative observed commercial outcome labels | Keep deferred; no SLA-model claims. Future lawful labels and separate qualification required |
| Azure OpenAI live request and failure handling | BLOCKED | P lacks endpoint/deployment; local transport tests are not live authorized service evidence | Configure authorized identity/quota/network; real request with grounded result and redacted receipt, controlled unavailable/quota tests and bounded retries |
| Power BI Desktop rendering and semantic model | BLOCKED | R `powerbi.log` explicitly schema-only; H reporting procedure requires real model | Reporting owner supplies model, renders all pages, verifies relationships/run filters/units/classification/measures against Gold and saves screenshots/IDs |
| Power BI refresh, service permissions and RLS | BLOCKED | H/O: no actual refresh history, publishing or RLS acceptance | Configure credentials/gateway where needed; publish and test refresh plus positive/negative users; owner determines RLS requirement, do not assume it away |
| Local backup/restore and audit consistency | PASS | D `backup-restore.json`: local restore PASS, 18 chained records, zero legacy unchained records, one approved release, matching published run; R recovery tests cover corrupt input/existing destination | Preserve originals; restore to new destination and verify manifest/database/audit/publication before switching |
| Offsite backup, failover and production RPO/RTO | BLOCKED | O explicitly unapproved targets/unassigned owners; no offsite restore measurement | Approve recovery owner, encrypted location/key access and targets; execute loss/restore/failover and measure actual data loss/time |
| Retention duration, locked immutability and expiry | BLOCKED | H/O: duration/lock approval absent; template policy unlocked; no target denied-overwrite/delete or expiry proof | Obtain explicit approval before deploy/lock; test effective identity denial and retained hashes, policy Locked/ETag, real expiry; document admin/break-glass handling |
| Monitoring configuration and alert routing | BLOCKED | O owners and notification destinations unassigned; telemetry resource is not delivery proof | Name primary/on-call/escalation contacts, configure alerts/action group; authorized isolated failure injection with fired alert, delivered notification and recovery timestamps |
| Incident response and rollback exercise | NOT_TESTED | H/O contain procedures; no recorded operator exercise for deployed system | Assign accountable incident roles; rehearse image/data/model rollback and escalation, preserving audit and failed-run evidence |
| Capacity, latency, throughput and reliability claims | NOT_TESTED | Local timing and functional results are not representative service-level measurements; L SLO control unevaluated | Agree workload/SLOs, measure sustained target workload and failure recovery; no invented uptime or performance figures |
| Image-generation runtime | NOT_APPLICABLE | No required/generated imagery or image-generation runtime added | Keep optional future image work isolated; not a release dependency |
| Public application/repository publication acceptance | BLOCKED | Local reports contain raw evidence; source rights, deployed security, secrets review and public claim review are not accepted | Review all proposed public files, history, archives and outputs for credentials, personal data and redistribution rights; publish only an explicitly scoped, reviewed artifact. Do not delete existing local work to achieve this |

## Recommended next actions and claim boundary

1. Keep Comtrade out of runtime; use research plus a plain official portal reference when preparing the public narrative. Owner can review/authorize sending the prepared licensing draft separately. No messages were sent.
2. Before public publication, define the exact artifact/audience and complete source-rights and secrets review, including retained raw samples and archives. A public source-code demo is not the same as accepting an internet-facing production service.
3. If production deployment is intended, assign owners and supply the target prerequisites in H. Execute the target gates and retain actual outcomes; do not mark them passed from templates, commands or documentation alone.

Existing `LOCAL_RELEASE_READY = YES` is the saved October 17 local campaign result for its exact source and time. This task creates no new campaign or timeless freshness guarantee. **PRODUCTION_READY = NO** remains supported by the explicit unevaluated industrial controls and missing target evidence. Tests were not rerun because only assessment files were added and no specific regression need was identified. Manifest verification checks documentary integrity only.
