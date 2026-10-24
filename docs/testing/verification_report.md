# Verification report — 2026-10-10

**LOCAL_READY** for the documented local analytical API workflow. **Not production ready.**
The production release gate remains BLOCKED with five mandatory external controls not evaluated.
The feature matrix records incomplete Power BI report authoring separately; no cloud runtime or
commercial SLA predictive performance is claimed.

Environment: Windows, Python 3.11.9, uv 0.12.18; Docker Desktop Linux containers. Local tests that
create asyncio loopback sockets required execution outside the restricted agent sandbox.
New Docker projects each used a fresh named volume. No existing user data was reset or deleted.

| Actual command/check | Result | Evidence |
|---|---|---|
| python -m pytest -q --junitxml=evidence/ready-to-run/verified-tests.xml | Exit 0; 39 passed, no skipped tests, 88.79 seconds | verified-tests.xml / verified-tests.log |
| python -m ruff check src tests scripts | Exit 0 | lint.log |
| python -m ruff format --check src tests scripts | Exit 0 | format.log |
| uv build | Exit 0; wheel and source distribution | build.log |
| Isolated copy of the Azure ML source whitelist, then uv build --directory <staging> | Exit 0; package hashes retained; not a cloud job | aml-staged-build.json / .log |
| python scripts/docker_demo.py | Exit 0; new image/volume, seed dependency, real authenticated HTTP, malformed/unauthorized rejection, review/outcome, learning export, restart persistence | maritime-demo-e8f5c6a5f1/result.json and command logs |
| python scripts/governance_release.py --root data/readiness-live-20261010 --output evidence/ready-to-run/live --as-of 2026-10-10 | Exit 0; local campaign PASS, industrial release BLOCKED | live/release-validation.json |
| uv tool run --from pip-audit==2.9.0 pip-audit --disable-pip --no-deps -r evidence/ready-to-run/runtime-requirements.txt -f json -o evidence/ready-to-run/dependency-audit.json | Exit 0; 104 pinned dependencies, zero known advisories | dependency-audit.json |

All relative evidence references above are under `evidence/ready-to-run/`. Quality exit codes are
machine-readable in `quality-exit-codes.json`. The repository does not configure a static type
checker; none is claimed executed. Tests cover business logic, database/API integration,
chronological ML, classification contracts, governance/recovery, and local Azure contract adapters.
Mock Azure adapter tests are explicitly not evidence of a live cloud round trip. One Starlette
deprecation warning recommends httpx2 for future TestClient versions; it did not fail the tests.

The live campaign retained actual public source responses and three successful runs plus two
injected failures (invalid coordinate and partial decision persistence). Both failures blocked
publication and preserved the previous snapshot. Canonical reconciliation was 1,434 received =
1,434 accepted + 0 rejected + 0 quarantined on the successful run. Audit-chain verification and
independent scalar metrics passed. Primary live run: `e0cb54d06e9440328dd005fca57c2857`.
Its recorded source fingerprint and dirty-working-tree flag are retained honestly; later API
metrics/packaging edits are covered by the final suite/build/Compose checks rather than relabeled
as that earlier exact source snapshot.

Corrections made during validation:

- The first Compose attempt failed because this version rejects `restart --wait`. A bounded HTTP
  readiness poll replaced that flag. The failed attempt remains in maritime-demo-6a047e0383.
- Restricted Windows tests stalled in Python's internal socketpair initialization. The diagnostic
  run was terminated, then the complete suite passed with local socket access.
- The initial audit found cryptography 49.0.0 affected by
  [GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5).
  The lock now uses 50.0.2 with a minimum patched-version constraint. MLflow's unused full server
  package constrained cryptography; it was replaced with the
  [Azure-supported tracking client](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2).
  The original advisory is retained in dependency-audit-before.json; the complete application/ML
  dependency export was audited again without advisory suppression.
- OneDrive hardlink/read-only errors affected environment updates. Copy mode and a scoped virtual
  environment repair resolved installation; reinstalling mlflow-skinny restored shared module files.
  Its start_run/log_artifacts imports were then checked successfully.
- Missing Azure ML staged README was fixed and the isolated staged package built successfully.
- Missing/invalid pipeline configuration and gate initialization now retain failed preflight
  reports; API metrics expose the latest failed attempt even while an earlier approved release serves.

External prerequisites remain Fabric capacity/workspace/lakehouse/identity, Azure ML workspace
and compute, Entra/storage/Key Vault/Monitor deployment, Azure OpenAI deployment, Power BI report
authoring/runtime, owner-approved retention/IAM tests and sustained workload/SLO evidence.
Current environment-variable presence checks are recorded in cloud-preflight.json without secrets.
SLA ML remains **DEFERRED — INSUFFICIENT OBSERVED OUTCOME DATA**.

Reproduce the clean demonstration using [READY_TO_RUN](../operations/READY_TO_RUN.md). Generate
the requirement-linked checksum manifest and ZIP after successful checks with:

```powershell
.venv/Scripts/python.exe scripts/package_readiness.py --demo maritime-demo-e8f5c6a5f1
```

For a new run, substitute the completed project name printed by docker_demo.py. The packaging
command refuses missing/failed checks, verifies ZIP contents against individual hashes, and
never grants production readiness. Earlier evidence packages remain intact.
