# Governance gap analysis — baseline 0fb0836

Inspection covered src, configs, tests, scripts, Fabric notebooks, Azure deployment, SQL/Power BI,
CI, docs and retained evidence. Earlier 24-test/local/Docker results are baseline evidence only.
This analysis precedes the governance changes. Architecture and existing algorithms are retained.

| Boundary | Reused controls | Demonstrated gap | Required change / verification |
|---|---|---|---|
| Acquisition | Source registry, HTTP retries/timeouts, raw hashes, pagination | Duplicate rows collapse during cache merge; no query count reconciliation or explicit degradation contract | Count reconciliation, reject duplicate/conflicting pages, bounded pagination/circuit state, acquisition ledger |
| Bronze | Content-addressed raw files, replay bundles | Existing payload not reverified; lifecycle/concurrent writers unguarded | Reverify hash, run lock, terminal recovery evidence; storage authorization remains cloud-unverified |
| Silver | Pydantic, coordinates, foreign keys, freshness | One record may count multiple rejections; invalid relational rows retained in clean lists; missing dates unchecked | Exclusive per-record dispositions, continuous date coverage, quarantine references and reconciliation |
| Gold | Named methods, history coverage, classifications, field lineage | No executable per-product release contract; no independent recomputation; missing lineage for metadata rows | Versioned contracts, dataset fingerprints, classification policy, source-to-output manifest and independent metrics |
| ML features | Observed-only export, file hashes, chronological folds | Loaded features lack duplicate/recomputed feature checks; manifest provenance incomplete | Recompute signature, reject skew/duplicates, record code/config/dependencies, versioned contracts |
| Models | Holdout policy, explicit promotion, pinned batch version | Registration alone not approval (already correct); no cloud evidence | Preserve controls, adverse tests; actual AML jobs remain NOT_EVALUATED until tenant execution |
| Prediction return | Classification/version checks, Delta count readback | Missing checksum, expected port/date set, duplicate outputs, model allowlist | Signed-by-trusted-runner manifest contract (hash evidence, not cryptographic signature), exact keys and full readback verification |
| GenAI | Exact spans, structured fields, ANTICIPATED | Provider/prompt metadata absent; confidence meaning unstated | Record returned model/deployment/prompt/time, reject malformed envelope, uncalibrated confidence label |
| Orchestration | Run reports, failed exceptions, published pointer | Pointer advances before terminal report; reused run IDs and overlap possible | Stage ledger, atomic release transaction, idempotent release, explicit interrupted-run reconciliation |
| Serving | Auth, roles, Azure checksums | Local explicit run ID can expose failed products; import trusts SUCCESS alone | Require approved manifest on every read/import; verify stored fingerprints; block stale live serving |
| Audit/security | JWT tests, managed identity template, separate audit container | Local SQL permits audit update/delete; Azure contributor permits delete | SQL append-only triggers, hash-chain verification; Azure immutable retention/RBAC verification remains blocking for industrial certification |
| Reliability | Regression suite, one live run, Docker smoke | No repeated-run/failure campaign or agreed production SLO | Predeclared invariant-based campaign, failure/recovery metrics; latency/resource SLOs require owner decision |
| Publication | Gold files and reports | No scoped release evidence pack or output separation | Operational OBSERVED/DERIVED, simulated, predicted outputs separated; overall industrial gate blocked for missing mandatory cloud/security evidence |

Acceptance policy is declared before measurement: zero accounting discrepancies, zero unauthorized
classification transitions, zero missing mandatory lineage, zero duplicate publications, unchanged
approved pointer after injected failure, recovery only through a new passing run. Existing 10-day
freshness/56-day baseline/28-observation minimum are retained as analytical contract settings;
they are not agreed production SLOs. No latency/availability business targets are invented.

The executable local contract can approve a scoped analytical release. It cannot approve live
Fabric/Azure behavior, immutable cloud storage, organizational retention or sustained production
reliability. The final industrial release gate must enumerate these unevaluated controls and stay
BLOCKED. An output failing that gate is diagnostic/local analytical evidence, not industrially
validated operational data.
