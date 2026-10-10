# Validation evidence

Baseline reports predate the stage-governance mandate and are retained for provenance, not reused
as proof of the new controls. The authoritative governance result is
`governance-release/release-validation.json` when present. Its declared scope and status govern
the datasets alongside it; a BLOCKED industrial release must not be described as validated
production data.

`governance-tests.xml` records actual expanded test execution. The clean campaign provides
versioned contracts, source-to-output lineage, disjoint record dispositions, reconciliation,
independent metric comparisons, failed-run/recovery evidence and separated analytical datasets.
`tests.xml`, `acceptance.json` and `docker-governance.json` record final local checks when refreshed.

See [governance reproduction and acceptance](../docs/governance.md). Cloud checks remain
NOT_EVALUATED until actual tenant execution supplies their evidence. No Azure/Fabric success,
regulatory certification, immutable cloud retention or sustained production reliability is implied.
