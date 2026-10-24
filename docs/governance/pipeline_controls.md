# Pipeline controls

The executable authority is configs/governance.json, models.py, quality.py, governance.py, pipeline.py and store.py. See ../governance.md for detailed control definitions and retained campaign evidence.

| Boundary | Enforcement | Failure behavior |
|---|---|---|
| Acquisition | Source registry, HTTP status, bounded retries/timeouts, stable pagination/count reconciliation, checksums | Critical failure blocks downstream processing; optional failures are explicit degradation |
| Bronze | Raw payload retention and rechecked content hashes | Altered raw payload rejects; replay mode explicit |
| Silver | Strict schema/ranges/classifications, date coverage, uniqueness and FK checks | Exclusive rejected/quarantined dispositions retained, critical DQ blocks |
| Gold | Metric definitions, independent scalar recalculation, key/range/classification/lineage validation | No scenario/recommendation publication from corrupt upstream data |
| ML | Observed feature eligibility, temporal split, bundle checksum, runtime/version/registry compatibility | Synthetic labels cannot train SLA ML; incompatible prediction import fails |
| GenAI | Exact evidence spans, strict envelope, prompt/provider provenance | Unsupported evidence rejected; service failure is not fabricated content |
| Orchestration | OS writer lock, stage receipts, immutable publication, retry IDs | Failed/abandoned attempts retained, previous pointer preserved |
| API | Role boundaries, verified release/hash, live source freshness, correlations | 401/403 auth errors, 422 malformed input, 503 unavailable/unapproved release |
| Learning | Audit IDs/timestamps, checksummed snapshot, decision FK/classification checks | Synthetic decision cannot acquire OBSERVED outcome; Delta readback required |
| Operations | Audit hash chain, SQL append-only triggers, startup validation | Database-admin bypass and cloud retention remain explicit limitations |

Accounting is stage-specific and exhaustive. Canonical input = accepted + rejected + quarantined; accepted is not simultaneously counted as already persisted. Acquisition caches explicitly account for retained/replaced/expired records. Gold publication verifies actual persisted product counts and content hashes, rather than treating a successful later stage as proof of earlier success. Empty acquisition caused by invalid configuration has zero records and a retained failed preflight operation. Unknown/in-flight work is not declared persisted.

Classifications OBSERVED, DERIVED, ANTICIPATED, SIMULATED and PREDICTED are preserved. Port activity is not waiting/dwell time; reference geometry is not observed traffic. Synthetic route/shipments contaminate dependent analytics as SIMULATED. No simulated outcome authorizes SLA model promotion.

Retention is preserve-by-default locally. Automatic destructive purge is not enabled because no owner-approved duration exists. Production immutable storage, administrator separation, retention expiry and recovery must be executed and verified before production acceptance.


## Production-gap controls added 2026-10-11

- Business review/outcome audit IDs are canonical-content addressed. Concurrent identical retries produce one event; distinct decisions/reviews remain distinct events. Complete audit verification rejects orphan chain entries as well as broken hashes. Local append-only triggers remain enforced.
- Learning import uses an atomic insert-only transaction locally and Delta MERGE in Fabric. Same audit ID with different content fails. Every transfer attempt has a receipt; successful local accounting is input = persisted + duplicate, rejected/quarantined/failed = 0. A rolled-back failed transaction reports all input failed. A process death before its terminal receipt is UNKNOWN until retry/readback; a receipt-write filesystem failure is not falsely reported as success. Fabric runtime still requires tenant execution.
- Canonical checksums use governance.fingerprint: Python json.dumps with sort_keys=True, default separators (comma-space and colon-space), ensure_ascii=True, allow_nan=False and models.json_default for supported scalar types, then UTF-8 encoding; array order is significant. Export record order is fixed, per-record checksums and packet hashes are verified against destination content. Hashes alone do not authenticate a malicious privileged writer.
- Azure ML batch verifies the serialized model's SHA-256 and version before accepting it, with size/symlink checks. Deserialization is restricted to artifacts from the explicitly promoted registry version. A checksum bundled by an attacker is not a substitute for registry access control.
- AOAI uses bounded four-attempt retries for transport failures/429/502/503/504, bounded Retry-After, connection/read timeouts, capped output tokens and signal counts, and explicit input-truncation metrics. Invalid evidence still rejects. Controlled-response tests do not certify the live service.
- Backup/restore verifies SQLite integrity, publication content, complete audit chain and file hashes. Existing destinations and overlapping paths reject. Restore does not mutate the original store.
- Bicep requires an owner-supplied auditRetentionDays and creates an initially unlocked immutability policy. The API role grants audit read/write without delete. Production acceptance still requires locking the policy, eliminating inherited destructive roles, and real denied-overwrite/delete and retention-expiry evidence. Azure ML's storage-scoped role must be considered when reviewing effective permissions; locked WORM is mandatory protection against any writer.
