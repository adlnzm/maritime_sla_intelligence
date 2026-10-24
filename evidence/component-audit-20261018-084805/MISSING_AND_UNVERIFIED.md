# Missing and unverified components

**The evidence does not support “all intended components are present and attached.”** The local analytical chain has substantial implementation and historical execution evidence. Target cloud, reporting and operational chains remain incomplete. A missing optional feature is not automatically a required project defect; scope decisions below distinguish them.

## Priority 1 — establish a usable selected local runtime

- Current source identity: 146 source hashes match the October 17 campaign; dirty tree preserved. This does not validate the current installed environment.
- Latest read-only runtime audit (`evidence/full-run-readiness-20261018-084056/preflight.json`) found duplicate `pytz` distributions, incomplete `aiohappyeyeballs` package metadata and unavailable Docker Linux engine. No environment repair or Docker restart occurred here. Its NO-GO remains relevant until superseded by actual passing target checks.
- Current inspected process environment lacks local API keys/data-root selection and all checked cloud endpoint/identity/workspace/telemetry variables. `configs/azure.json` has no subscription/RG/workspace values. This does not prove that no credentials exist elsewhere.
- Minimum follow-up: select native/Compose and exact root/volume; authorize a separate intact locked environment; verify dependencies, writer exclusion, actual readiness and target backup without resetting existing data. No unrestricted run or repeated suite in this inventory.

## Priority 2 — confirm product scope and claims

- Forecasts are published, but not consumed by local scenario ranking. Decide whether forecast-to-decision coupling is a requirement; otherwise correct that claim rather than adding a feature.
- Shipment-SLA ML is intentionally absent, blocked on real observed labels; keep simulation separate. No production model is approved.
- Optional WPI, UN/LOCODE and reference-route URLs are missing. Decide whether to configure legitimate feeds or retain explicit degraded scope. Default connectivity is simulated.
- WTO/Comtrade ingestion is absent by deliberate rights/data-contract decision; source research does not imply integration. No new provider is needed to describe the existing platform honestly.
- No recurring schedule or dedicated custom web UI was found. Confirm whether either is intended; manual execution and OpenAPI are existing interfaces. PostgreSQL/message broker/image generation are not established requirements.

## Priority 3 — target integration evidence, only if deployment is desired

- Fabric: actual capacity/workspace/lakehouse, six deployed notebooks, terminal pipeline jobs, accepted Delta counts/hashes and failure/replay readback.
- Azure ML: workspace/compute/identity and real train/evaluate/register/approve/batch results; artifact/version integrity and return to Fabric. Local job-function tests are not cloud execution.
- Entra/managed identities/Blob/Key Vault/Container Apps: actual target audience/roles, scoped permissions, current image/configuration, authorized and denied requests, dependency failure and restart persistence. Templates do not establish effective grants.
- Azure OpenAI: real authorized endpoint/deployment request with grounding receipt, timeout/quota/failure evidence. No live response exists in examined acceptance evidence.
- Feedback and serving bridges: execute Azure audit ↔ Fabric and Fabric ↔ AML/serving transfers with actual destination readback and replay/conflict checks. Local SQLite transfer proof covers only the local portion.

## Priority 4 — reporting and operation

- Power BI: bind/create the real semantic model, run SQL/DAX/Power Query, render five pages, validate relationships/measures/filters and run isolation, refresh credentials, service publish and approved RLS. Static schemas currently pass; binding/refresh do not.
- Alerts: implement/configure rules/action group and name owners, then execute an authorized failure with a received notification and resolution receipt. No actual delivery path is established.
- Retention: obtain duration/lock approval; deploy and verify effective immutable policy, denied overwrite/delete and actual expiry. An unlocked template policy is not enforced immutability.
- Recovery/SLO: select target, verify its backup/restore, define offsite and incident owners/targets, measure real restore/failover/performance. Current local historical restore does not establish production RPO/RTO.

## Evidence/documentation inconsistencies

The old feature matrix still describes a missing five-page report and a `fabric/pipelines` location. Current files show five PBIR pages and deployment-generated pipeline JSON. The current deployment script handles six notebooks; the README's older five-notebook wording is stale. Older 39-test summaries are historical; October 17 XML contains 63 tests. These files were not edited; use component-status.json and direct evidence paths for this inventory.

No secrets were emitted. The audit checked presence only and did not enumerate credential stores or remote tenant/repository settings. Remote runtime integration therefore remains UNKNOWN where local artifacts cannot establish it. No public or production readiness approval is made.
