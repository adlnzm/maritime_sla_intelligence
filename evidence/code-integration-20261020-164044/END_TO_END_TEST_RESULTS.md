# End-to-end test results

## Final authoritative results

Working directory: repository root. `E` below denotes `evidence/code-integration-20261020-164044`; `P` denotes `E/validation-copy/Scripts/python.exe`.

| Command | Actual outcome | Evidence |
|---|---|---|
| Set `UV_PROJECT_ENVIRONMENT=E/validation-copy`; `uv --cache-dir C:/Users/User/AppData/Local/uv/cache sync --frozen --offline --link-mode copy --python .venv/Scripts/python.exe --extra dev --extra azure --extra fabric` | Installed a separate frozen environment from local cache, no network | environment-copy-setup.log |
| `uv --cache-dir E/uv-cache --offline pip check --python P` | 85 packages compatible, exit 0 | dependency-clean.log |
| `P -u E/run_validation.py -q -o faulthandler_timeout=60 --basetemp=E/verified-temp --junitxml=E/verified-tests.xml` | **85 passed**, 0 failed/errors/skipped, one existing deprecation warning; exit 0 | verified-tests.xml, verified-tests.log |
| `E/validation-copy/Scripts/ruff.exe check src tests scripts` | Pass, exit 0 | lint.log |
| `E/validation-copy/Scripts/ruff.exe format --check src tests scripts` | 51 files already formatted, exit 0 | format.log |
| `uv --cache-dir C:/Users/User/AppData/Local/uv/cache build --offline --link-mode copy --out-dir E/verified-build --python P` | Source distribution and wheel built, exit 0 | verified-build.log |
| `P E/inspect_artifacts.py` | Application imports, AST parsing, source/governance wheel equality, source archive bounds pass | artifact-inspection.json, source-hashes.json |

The full suite includes retained-public-data replay and real local model training, in-process API-to-SQLite requests, actual temporary SQLite publication/audit/feedback/backup/restore, source and cloud transport fakes, and generated reporting/notebook contracts. The runner does not start an API server, Docker, Spark or a cloud service. New synthetic ArcGIS responses exercise the acquisition code branch, but are not real public observations. Historical replay is not current source acquisition.

## Behavioral coverage

- Observation-date normalization and per-port ten-day freshness boundary, including rejection of changed configured thresholds.
- Source pagination/count reconciliation, revision/deletion replacement, duplicate rejection, Bronze tamper detection, retry/circuit/timeout accounting.
- DQ dispositions, quarantine evidence, provenance, classifications, run identity, idempotency, locking and interrupted/failed-run publication safeguards.
- Activity stress, graph propagation, simulated interventions/ranking, temporal model eligibility, feature skew, artifact integrity, approval boundaries.
- Forecast independence from recommendation ranking; failed forecasts preserve prior publication. Fabric return retains supplemental status and traces new fields to predicted activity.
- API authentication, authorization, body limits, publication races, error redaction, correlation, liveness and readiness.
- Cloud SDK/HTTP configuration, identity injection, retries/timeouts, manifest/checksum contracts, Blob pointer interruption/corruption/replay and pinned reads.
- Six notebook definitions regenerated in a temporary root; reporting assets checked against generated mart columns.

## Intermediate attempts and failures retained

These do not replace the final result:

- `.venv` imports were available, but `python -m pip check` could not run because pip was not installed. `uv pip check` then confirmed duplicate pytz metadata and incomplete aiohappyeyeballs metadata (`dependency-check.log`). Existing `.venv` remains unchanged.
- The first uv check used a sandbox cache location that denied writes; it was stopped and repeated with a cache under this evidence directory.
- Initial sandbox test attempts (`initial-tests.log`, `targeted-tests.log`, `targeted-isolated.log`, plus an uncaptured `-s -vv` diagnostic) stalled in `socket.accept -> socketpair -> asyncio ProactorEventLoop`, not application logic. They were interrupted and have no passing verdict.
- A read-only broad file-hash traversal was cancelled before completion because `data/` also contains historical environments. It is not treated as a preservation checksum. Final source-only hashes are retained separately.
- First corrected targeted run: 15 passed (`targeted-final.log`, `targeted-tests.xml`). First full run: 78 passed (`full-tests.log`, `full-tests.xml`). Extended clean-environment run: 18 passed (`target-clean.log`, `target-clean.xml`). These are intermediate source states.
- First clean environment attempt failed because OneDrive rejected cached hardlinks (`environment-setup.log`); full-copy installation in a separate directory succeeded. Both directories are retained.
- Initial package build was interrupted after overly broad source discovery; the explicit source-distribution allowlist fixed that boundary. `final-build.log` is an intermediate successful build; `verified-build.log` is authoritative.
- An earlier final-suite attempt (`final-tests.log`) was stopped while preserving historical governance-contract compatibility. No result is claimed for it.
- Ruff formatting initially identified new-code formatting/import-order adjustments; they were corrected. Final checks pass.

No test assertion was weakened, no failing test was removed, no exception was hidden to obtain a pass, and no new external service was substituted with a fabricated success. Static type checking is not configured. Dependency compatibility is not a fresh vulnerability/advisory audit.
