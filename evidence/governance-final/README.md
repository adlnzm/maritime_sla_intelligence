# Governance evidence — 2026-10-10

Industrial release: **BLOCKED**. Local analytical release: **PASS_WITH_WARNINGS**.
This pack is diagnostic evidence and scoped analytical data, not an industrial production release.

- Source commit: `2d02285b61c2b86fbebdcc8aa1b397bdcb92e3d0` (clean code tree during execution).
- Live run: `1e30c60049c448ca8335ea1d54b7a869`.
- Release: `160ee6df39288465961e550ccf4717731bcbfcb471112914e36a3bba27aafd79`.
- Live inputs: 6 ports and 1,398 activity observations; 1,434 canonical records including 30 explicitly simulated routes. All accounted for; zero rejected.
- 36 tests; 15 local HTTP endpoints; 12 Docker HTTP endpoints; lint, format and package build passed.
- Recovery campaign: three successful runs and two intentionally blocked failures; prior snapshot preserved.

`datasets/operational`, `datasets/simulated` and `datasets/predicted` are separated by classification.
`configuration`, `source-to-output-lineage.json`, `reconciliation.json`, `audit-ledger.json`,
`runs`, `quarantine`, `bronze`, `models-local-research` and `validation` provide the evidence.
Model artifacts are trusted local research outputs and are not Azure ML production approvals.
Reproduction commands and actual exit codes are in `validation/command-results.json`.

Outstanding mandatory controls: actual Fabric/Azure ML execution and return, cloud identity/access
verification, raw/audit retention enforcement, and agreed production SLOs with sustained evidence.
Cloud IDs/resources are unconfigured; see `validation/cloud-preflight.json` and `docs/azure.md` in
the repository. No resource-capacity, licensing approval, cloud immutability or regulatory claim
is made. SLA ML remains **DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA**.

Hashes in `evidence-checksums.json` detect accidental alteration. They are not signed attestations
or proof against a filesystem administrator who can modify the data and hashes together.
