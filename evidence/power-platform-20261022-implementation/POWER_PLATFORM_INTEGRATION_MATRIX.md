# Integration matrix

| Component | Implemented connection | Automated evidence | Boundary/status |
|---|---|---|---|
| Canonical Hamad | Verified port2026 reference -> daily ID join -> pinned ingestion/config | Genuine public fixture join and mismatch rejection | Read-only source verified 2026-10-22; no full live pipeline |
| Bronze/DQ | Existing Fetcher -> acquisition manifest -> canonical validation/quarantine/reconciliation | Existing source/E2E regressions; new weekly input tests | Local and mocked acquisition tested; replay distinguished |
| Persisted Silver | Validated ports/activity/routes -> SQLite/files -> analytical readback | Real temporary pipeline, integrity and weekly lineage tests | Connected locally |
| Weekly Gold | Persisted weekly Silver -> shared versioned classification -> release hashes | Boundary, missing, stale, retrieval invariance, partial-publication tests | Connected locally; derived proxy |
| Publication/recovery/cloud export | Supplemental manifest -> Store/AzureStore/Fabric/CLI/recovery | Full regression; real AzureStore with fake transport and tamper rejection | No live Azure/Spark claim |
| Operational decisions | Approved Gold -> separate workflow.db -> immutable action history | Authorization, reasons, conflicts, idempotency, stale rejection, separation | Connected locally |
| API/custom connector | Existing auth -> operations routes -> service -> analytical/workflow stores | In-process API, field/parameter parity, role checks | OAuth endpoints/registrations require tenant |
| Canvas review source | Shared queue/review/history connector -> generated controls/properties | Generation equality and corrected official schema | Source generated; Studio compilation/rendering unverified |
| Escalation flow | Gold transitions -> durable events -> lease/send/ack | Duplicate/retry/expiry/stale/missing-recipient and schema/runAfter contracts | Flow generated; transport mocked; live delivery unverified |
| Power BI | Reporting API -> authenticated snapshot export -> typed M queries -> existing PBIR extension | Actual packet field maps, export, relationship key checks, DAX field references, 54 JSON assets/10 pages | Binding/M-DAX engine/rendering/refresh unverified |
| Hamad/portfolio views | Configured focus port + shared Gold definitions -> dedicated and portfolio tables/pages | Exact config pin, server focus filtering and report field mapping | No fabricated current Hamad weekly risk |
| Forecast/SLA | Existing forecast eligibility and supplemental output retained | Full existing regression suite | Forecasts do not rank; simulated SLA remains simulated |

No required local path is intentionally deferred. Live tenant, licensing, security, delivery, refresh and production-operational acceptance are external prerequisites. Notification transport fakes are contract tests, not live-service evidence.
