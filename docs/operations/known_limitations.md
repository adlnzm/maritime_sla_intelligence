# Known limitations and external prerequisites

- Fabric runtime: requires licensed capacity, workspace/lakehouse IDs, authorized identity, deployed package/notebooks/pipeline and real Delta readback. Static/contract tests are not runtime evidence.
- Azure ML: requires subscription/resource group/workspace/compute, registered environments and authorized job submission. Training, evaluation, promotion, batch and monitoring cloud jobs remain unexecuted.
- Azure application: requires deployment, Entra application roles/audience/tenant, least-privilege storage and secret permissions, real telemetry and recovery tests.
- Azure OpenAI: requires endpoint, model deployment and authorized identity/key. Local tests use controlled responses and verify grounding; no live generation is claimed.
- Power BI: SQL/DAX/Power Query assets and five authored PBIR pages exist. All 29 PBIR files pass Microsoft JSON schemas and governed-column checks; deployed semantic model/PBIX, rendering, filter behavior, tenant refresh and additional intended network/review visuals remain unverified. This prevents production completion, not API-only local research execution.
- Reference data: WPI, UN/LOCODE and route sources require configured legitimate downloads and actual adapter execution. Missing sources are explicit; default connectivity is SIMULATED.
- SLA ML: **DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA**. No legitimate commercial shipment labels exist. Simulation probabilities and local feedback cannot establish real predictive accuracy or causal intervention effectiveness.
- Audit/retention: local SQL triggers/hash chain do not protect against a privileged database administrator. Cloud immutability, retention duration, destructive-permission tests and retention-expiry evidence are outstanding.
- Scale/SLO: no production availability/latency/throughput/recovery guarantee exists. Fabric graph execution is driver-bounded; API counters are process-local. Workload assumptions and sustained metrics/alerts require owner agreement and an actual deployment.
- Feedback bridge: implemented with local export, transactional destination persistence and genuine SQLite readback/replay verification; live Azure audit → Fabric Delta round trip requires tenant execution. Serialize imports for a given source run.
- Local execution uses SQLite; PostgreSQL was not established as an implementation dependency. A migration would require a separate explicit architectural decision.
- Security advisory scan and current quality checks are recorded in ../testing/verification_report.md. Do not infer a clean scan when the advisory service or installer failed.



The exact closure procedures, operational-owner decisions, minimum SLA-label contract and evidence required are in [production closure runbook](production_closure.md). All cloud resource/configuration names were absent in the 2026-10-11 preflight and Azure CLI was unavailable; there was no configured authorized target on which to execute a meaningful service request. This is not a failed cloud authentication claim. Azure syntax and local adapter tests do not change that status.
