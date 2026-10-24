"""Create source-bound evidence from actual retained validation results."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AUDIT = ROOT / "evidence/component-audit-20261018-084805"
now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3))).isoformat()
inventory = json.loads((AUDIT / "component-status.json").read_text(encoding="utf-8"))
tree = ET.parse(OUT / "verified-tests.xml")
cases = list(tree.iter("testcase"))
assert len(cases) == 85
assert not list(tree.iter("failure")) and not list(tree.iter("error"))
assert not list(tree.iter("skipped"))
inspection = json.loads((OUT / "artifact-inspection.json").read_text(encoding="utf-8"))
assert inspection["status"] == "PASS"
assert "All installed packages are compatible" in (OUT / "dependency-clean.log").read_text()
assert "All checks passed" in (OUT / "lint.log").read_text()
assert "already formatted" in (OUT / "format.log").read_text()
branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
assert branch == (OUT / "branch-before.txt").read_text().strip()
assert commit == (OUT / "commit-before.txt").read_text().strip()
status = subprocess.check_output(
    ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT, text=True
)
(OUT / "git-status-after-tracked.txt").write_text(status, encoding="utf-8")

changed = {
    "src/maritime/api.py": "Map SQLite/OS/Azure dependency exceptions to redacted 503 responses while retaining correlation IDs and liveness.",
    "src/maritime/azure_store.py": "Validate account/container configuration before identity access; pin approved reads; verify destination content before publication; complete interrupted pointer updates without rolling back newer snapshots.",
    "src/maritime/fabric_runtime.py": "Validate task run/contract/stage/latest-attempt dependencies; generate, persist and include returned prediction/decision-evidence field lineage in the release.",
    "src/maritime/pipeline.py": "Declare forecasts unused for recommendation ranking using the existing decision field contract; trace supplemental forecast evidence to predictions.",
    "scripts/deploy_fabric.py": "Inject real HTTP/identity interfaces for testing, reject unexpected request URLs, bound malformed Retry-After handling, retry safe reads on transport failure, propagate ambiguous mutating-call failures.",
    "scripts/azure_ml.py": "Validate required cloud configuration before optional SDK import or credential construction.",
    "pyproject.toml": "Explicit source-distribution inputs prevent retained evidence/environments from entering package builds.",
    "tests/test_code_integration.py": "22 parameterized integration/regression cases across acquisition, cloud serving, API failure, Fabric tasks/REST/forecast return, ML configuration, freshness and forecast isolation.",
    "tests/test_fabric_assets.py": "Generate all six notebooks in a temporary directory and compare with retained assets.",
}

# Each entry describes the code path, its actual evidence, and its boundary.
details = {
    "C01": ("required_local", "Fetcher.arcgis -> ingest_portwatch -> pipeline.run -> validate -> Store checkpoint/Gold -> publication -> API", ["test_acquisition_to_publication_api_and_failed_refresh"], "Synthetic ArcGIS HTTP responses; not a new public acquisition."),
    "C02": ("optional", "ingest_optional(wpi_csv) -> reference_wpi -> governed Gold export", [], "No configured URL; source parsing inspected, no live or dedicated WPI fixture execution claimed."),
    "C03": ("optional", "ingest_optional(unlocode_zip) -> validate(reference) -> reference_unlocode", [], "No configured URL; optional reconciliation code inspected."),
    "C04": ("optional", "ingest_optional(route_geojson) -> supplied_routes -> validate -> graph", [], "No configured URL; default route generation remains SIMULATED."),
    "C05": ("optional", "ingest_optional(weather) -> reference_weather -> governed publication", [], "Optional derived reanalysis; live provider and entitlement unverified."),
    "C06": ("deferred", "No runtime ingestion path by the existing scope decision", [], "WTO/Comtrade remains research only."),
    "C07": ("required_local", "normalize_activity -> UTC observation dates -> validate -> Gates", ["test_observation_dates_are_parsed_completely_in_utc", "test_freshness_uses_each_ports_observation_not_retrieval", "test_pipeline_rejects_freshness_configuration_drift"], "Ten-day threshold and per-port observation dates preserved."),
    "C08": ("required_local", "validate -> exclusive dispositions/quarantine -> silver gate -> publication gate", ["test_exclusive_dispositions_and_temporal_coverage", "test_canonical_adverse_controls"], "Invalid inputs block publication; no assertion weakening."),
    "C09": ("required_local", "field_lineage/enrich -> Gold/Store -> API; prediction return -> updated lineage/manifest", ["test_prediction_return_to_fabric_decisions_and_serving_contract", "test_full_pipeline_api_override_and_recovery"], "Cloud return persistence is a mocked Delta contract."),
    "C10": ("required_local", "Fetcher.get -> content-addressed Bronze -> checksum evidence; fixture -> declared REPLAY", ["test_raw_retention_retry_and_idempotency", "test_raw_mutation_and_partial_extract_block", "test_retained_public_data_end_to_end_and_model_loading"], "Replay is not new acquisition."),
    "C11": ("required_local", "canonical validate output -> run-isolated Silver -> analytical functions", ["test_full_pipeline_api_override_and_recovery"], "Real temporary filesystem and SQLite."),
    "C12": ("required_local", "analytics/scenarios/ML -> enrich -> verify_products -> persisted readback -> release -> Store.publish", ["test_interrupted_persistence_does_not_publish", "test_full_pipeline_api_override_and_recovery"], "Gold/GIS/report outputs are generated only in disposable test roots."),
    "C13": ("required_local", "Store schema -> transaction -> immutable approved products -> approved reads", ["test_empty_legacy_and_future_database_schema", "test_store_atomic_publication"], "No existing database opened for mutation."),
    "C14": ("required_local", "stored activity_cache -> overlap-window replacement -> accounting -> DQ-approved checkpoint", ["test_incremental_replaces_revisions_and_deleted_rows", "test_acquisition_to_publication_api_and_failed_refresh"], "Publisher revisions/deletions and duplicate failures covered."),
    "C15": ("required_local", "exclusive_run -> run identity -> recovery receipt -> verified idempotent return", ["test_fail_closed_publication_idempotency_recovery_and_audit"], "Lock/recovery tests use temporary roots."),
    "C16": ("required_local", "cli.main run arguments -> pipeline.run -> _run stages -> report/result/failure", ["test_invalid_configuration_is_retained", "test_gate_initialization_failure_is_retained", "test_full_pipeline_api_override_and_recovery"], "Pipeline task/result path executed; CLI wrapper inspected/imported. No unrestricted CLI run."),
    "C17": ("optional", "No recurring scheduler in existing scope", [], "Manual orchestration retained."),
    "C18": ("required_local", "create_app routes -> verified_read -> Store/AzureStore approved snapshots", ["test_full_pipeline_api_override_and_recovery", "test_api_cloud_dependency_errors_are_redacted_503"], "In-process TestClient; no server launched."),
    "C19": ("required_local", "key/role dependencies -> body limits -> review/outcome audit", ["test_startup_requires_auth_and_separates_roles", "test_api_large_and_chunked_requests_are_rejected"], "Test-only credentials, no credential values read or emitted."),
    "C20": ("required_local", "health/ready -> approved read/freshness/dependency response", ["test_startup_requires_auth_and_separates_roles", "test_api_cloud_dependency_errors_are_redacted_503"], "Liveness survives storage outage; freshness remains enforced."),
    "C21": ("required_local", "activity -> congestion/history -> latest states -> disruptions/early_warning", ["test_no_future_leakage_and_proxy_persistence", "test_full_pipeline_api_override_and_recovery"], "Derived activity stress, never directly measured waiting/dwell."),
    "C22": ("required_local", "validated ports/routes/states -> network_state -> propagate -> exposure/API", ["test_network_closure_and_temporal_propagation"], "Default topology remains simulated."),
    "C23": ("required_local", "graph -> seeded shipments -> evaluate -> simulated SLA risk", ["test_scenarios_reproducible_and_counterfactuals"], "No observed commercial shipment performance claim."),
    "C24": ("required_local", "evaluated interventions -> rank -> decisions -> published API", ["test_forecasts_are_supplemental_and_failure_preserves_publication", "test_scenarios_reproducible_and_counterfactuals"], "Forecast changes do not affect recommendation ranking."),
    "C25": ("required_local", "API review/outcome -> append-only audit -> export_feedback -> validation -> destination persistence", ["test_feedback_real_destination_replay_and_atomic_conflict", "test_response_pins_decision_release_and_audit_during_publication"], "Observed labels cannot be attached to simulated shipments."),
    "C26": ("required_local", "observed activity -> temporal features/evaluation -> artifact -> predictions -> Gold", ["test_retained_public_data_end_to_end_and_model_loading", "test_ml_cannot_train_on_simulation"], "Research port-call prediction only; not commercial SLA ML."),
    "C27": ("deferred", "No forecast-to-ranking connection; explicit NOT_USED_FOR_RANKING and supplemental evidence only", ["test_forecasts_are_supplemental_and_failure_preserves_publication", "test_prediction_return_to_fabric_decisions_and_serving_contract"], "No coupling introduced or claimed."),
    "C28": ("deferred", "Observed shipment-SLA model intentionally absent; production feature boundary rejects simulated activity", ["test_synthetic_data_rejected_at_production_ml_boundary"], "Representative lawful observed shipment labels remain unavailable."),
    "C29": ("conditional_cloud", "parameterized notebooks -> fabric_gate -> Bronze/Silver/Gold/acceptance/import runtime -> Delta boundary", ["test_notebooks_are_connected_to_runtime_and_parameterized", "test_generated_notebooks_match_retained_assets", "test_fabric_task_dependency_retry_receipts_and_run_identity", "test_prediction_return_to_fabric_decisions_and_serving_contract"], "Actual Spark/Delta engine execution and multi-table runtime behavior not verified."),
    "C30": ("conditional_cloud", "Fabric identity -> REST item/job requests -> bounded retries/polling -> four-stage notebook dependency definition", ["test_fabric_rest_identity_retry_polling_and_timeout_contract"], "Mock HTTP contract plus static deployment-definition inspection; no item deployment."),
    "C31": ("conditional_cloud", "Azure config -> identity/MLClient; features -> train/evaluate/batch/monitor -> promotion contract", ["test_azure_ml_configuration_precedes_sdk_and_maps_identity", "test_azure_ml_job_logic_preserves_model_and_classifications"], "SDK client fake and real local job functions; no Azure ML job/registration/promotion."),
    "C32": ("conditional_cloud", "export_features/load_features -> approved prediction manifest -> import_predictions -> supplemental decisions/lineage -> AzureStore", ["test_fabric_mode_exports_features_instead_of_training", "test_prediction_import_contract_adverse_cases", "test_prediction_return_to_fabric_decisions_and_serving_contract"], "Real importer/manifest/serving code with mocked Delta/Blob; OneLake transfer and service lifecycle unverified."),
    "C33": ("conditional_cloud", "AzureStore audits -> export_feedback/validate_feedback -> Fabric feedback packet -> Delta MERGE/readback interface", ["test_feedback_real_destination_replay_and_atomic_conflict", "test_full_pipeline_api_override_and_recovery"], "Local SQLite destination executed. Fabric MERGE and OneLake transfer inspected, not executed on Spark."),
    "C34": ("conditional_cloud", "extract -> endpoint/key or identity -> bounded AOAI request -> grounded ANTICIPATED signals -> audit interface", ["test_azure_openai_request_and_grounding", "test_aoai_bounded_retry_timeout_and_no_fabricated_fallback"], "Mocked HTTP, never a fabricated live response."),
    "C35": ("conditional_cloud", "API auth -> JWKS/JWT signature/audience/expiry/tenant/role checks", ["test_entra_signature_audience_expiry_and_roles"], "Locally generated signed JWT and mocked key lookup; tenant grants unverified."),
    "C36": ("conditional_cloud", "configuration -> credential -> Blob clients -> immutable products/readback -> pointer -> approved API reads and audit", ["test_blob_configuration_rejected_before_authentication", "test_blob_identity_configuration_and_timeouts", "test_blob_interrupted_pointer_retry_and_corrupt_readback", "test_blob_read_pins_publication", "test_azure_serving_checksum_publication_and_audit_isolation"], "In-memory Blob SDK boundary; no Azure storage live access or concurrency/ETag guarantee claimed."),
    "C37": ("conditional_cloud", "Bicep configuration -> managed identity/account endpoints -> credential/Key Vault/telemetry integration points", ["test_blob_identity_configuration_and_timeouts", "test_azure_ml_configuration_precedes_sdk_and_maps_identity"], "Application auth/config contracts tested; template deployment, Key Vault and telemetry reception not executed."),
    "C38": ("external_operational", "Retention policy template -> owner-approved cloud policy", [], "Duration/locking/denial/expiry verification remains external."),
    "C39": ("required_reporting_assets", "published run-scoped Gold -> SQL views/Power Query/DAX references", ["test_powerbi_schemas_and_governed_field_bindings"], "Generated data contracts tested; SQL Server/DAX/M engine execution unverified."),
    "C40": ("required_reporting_assets", "build_powerbi -> 29 PBIR/schema assets -> published mart field bindings", ["test_powerbi_schemas_and_governed_field_bindings"], "No Desktop rendering or service binding claimed."),
    "C41": ("external_operational", "Semantic model binding/refresh/RLS requires target Power BI environment", [], "Placeholder template remains explicit; no published dashboard claimed."),
    "C42": ("optional", "No dedicated browser UI required by implemented scope; API/OpenAPI available", [], "No new UI introduced."),
    "C43": ("required_local", "pipeline reports/reliability -> API metrics; middleware -> correlation and counters", ["test_full_pipeline_api_override_and_recovery", "test_api_cloud_dependency_errors_are_redacted_503"], "Local output contracts tested; Azure Monitor reception unverified."),
    "C44": ("external_operational", "No configured alert delivery/action group/on-call path in current scope", [], "No delivered notification claim; owners/routing require external decisions."),
    "C45": ("required_local", "backup -> checksummed snapshot -> fresh restore -> audit/publication verification", ["test_actual_backup_restore_and_tamper"], "Disposable data only; not a backup/restore of operational data."),
    "C46": ("external_operational", "Offsite DR/RPO/RTO/failover remains unconfigured", [], "No target DR or retention changes."),
    "C47": ("packaging", "Docker/Compose config -> existing packaged app entry points; wheel/sdist source contracts", ["test_startup_requires_auth_and_separates_roles"], "Package build verified; Docker build/engine/Compose execution deliberately not performed."),
    "C48": ("required_local", "locked clean environment -> pytest/Ruff/build -> source-bound evidence", ["test_release_rejects_source_mismatch"], "85 tests pass. Old .venv defects preserved; clean validation environment passes. No fresh vulnerability-feed scan."),
    "C49": ("external_operational", "CI source -> same pytest/lint/format/build/notebook checks; manual deployment workflows", ["test_generated_notebooks_match_retained_assets"], "Local CI-equivalent checks executed; GitHub workflow/deployment execution unverified."),
}
components = []
for old in inventory["components"]:
    scope, path, selectors, boundary = details[old["id"]]
    matched = [
        f"{case.attrib['classname']}::{case.attrib['name']}"
        for case in cases
        if any(case.attrib["name"].split("[")[0] == s for s in selectors)
    ]
    for selector in selectors:
        assert any(case.attrib["name"].split("[")[0] == selector for case in cases), selector
    components.append({
        "id": old["id"], "name": old["name"], "source_paths": old["paths"],
        "scope": scope,
        "required_for_current_local_product": scope in {
            "required_local", "required_reporting_assets", "packaging"
        },
        "integration_path": path,
        "verification": "AUTOMATED_LOCAL_AND_OR_MOCK_CONTRACT" if matched else "STATIC_SCOPE_REVIEW",
        "tests": matched, "boundary": boundary,
        "live_runtime_verified": False,
    })

matrix = {
    "schema_version": "1.0", "generated_at": now, "timezone": "Asia/Qatar",
    "audit_source": str(AUDIT.relative_to(ROOT)).replace("\\", "/"),
    "branch": branch, "commit": commit,
    "verdict": "CODE-INTEGRATED AND VALIDATED",
    "scope": "Implemented local analytical product and explicitly tested offline adapter contracts; no live runtime, cloud-service, reporting-engine or production certification.",
    "required_local_disconnected_components": [],
    "component_count": len(components), "components": components,
}
(OUT / "COMPONENT_INTEGRATION_MATRIX.json").write_text(
    json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
)
file_changes = "\n".join(f"- `{path}` — {purpose}" for path, purpose in changed.items())
report = f"""# Code integration report

**CODE-INTEGRATED AND VALIDATED** — implemented local analytical scope, with the offline cloud adapter contract coverage explicitly bounded below. This is not live runtime, cloud-service, Power BI engine, or production verification.

Assessment time: {now} (Asia/Qatar). Branch `{branch}`, commit `{commit}` remain unchanged. The existing audit's 49 components were traced using actual source, contracts and callers; see COMPONENT_INTEGRATION_MATRIX.json for every classification and test link.

## Project preservation

Branch, SHA and complete tracked/untracked/ignored Git status were recorded before source edits in `branch-before.txt`, `commit-before.txt`, and `git-status-before.txt`. The workspace was already dirty. Existing unrelated modifications, data, checkpoints, environments, ignored files and historical evidence were retained. No reset, clean, checkout, branch switch, commit, push, tag or Git release occurred. No application services, deployment, unrestricted pipeline, existing persistent database or external system were operated. Test pipelines and backup/restore ran only on disposable roots. External HTTP/SDK responses were mocked; the runner blocked outbound sockets and removed cloud/telemetry settings from its own process.

Windows' sandbox stalled asyncio's internal loopback socket-pair setup. Those test processes were stopped; bounded test runs succeeded with loopback available outside that sandbox, retaining the runner's external-network guard. No application server was started.

## Changes made in this task

{file_changes}

These are task-specific descriptions, not a claim that the entire Git diff belongs to this task. Several edited files already contained user changes. The existing governance JSON is byte-identical to Git HEAD; no freshness/schema-fingerprint migration was introduced. Existing historical release contracts therefore remain unchanged.

## Connected and exercised paths

1. Mocked ArcGIS HTTP acquisition -> production Fetcher/count reconciliation -> normalization -> DQ/quarantine -> incremental checkpoint -> analytics/scenarios -> verified SQLite/Gold publication -> authenticated API/report/freshness responses. Replay paths separately exercise successful API reads and observed-history model training.
2. Revised/deleted source records, duplicate inputs, exhausted timeouts, invalid configuration, stale observations and interrupted persistence -> retained failed report -> previous publication preserved.
3. Graph/scenario outcomes -> recommendations, with forecasts explicitly separate from ranking. Changed forecast values leave actions and benefits unchanged; forecast failure prevents new publication. Simulated shipments remain simulated and observed commercial SLA training remains deferred.
4. Fabric task dependency/attempt receipts -> guarded task invocation/result/error. Real prediction import -> validated manifest -> mocked Delta boundary -> supplemental decision evidence -> newly connected field lineage -> release hashes -> real AzureStore code over fake Blob clients.
5. Blob endpoint/container configuration -> real credential injection point -> timeouts -> verified destination readback -> published pointer -> pinned approved reads. Interrupted pointer publication is recoverable; corrupt destinations cannot publish; replay of an older completed run cannot roll back a newer snapshot.
6. API -> local/cloud data-access failure -> redacted 503 plus correlation ID; health remains available. Review/outcome/audit/export, request limits, simultaneous publication and recovery retain existing regression coverage.
7. Gold mart contracts -> generated reporting assets, and parameterized notebook generators -> six retained notebook definitions. Source distribution and wheel build from the final source without sweeping retained evidence into the package.

## Validation

- **85 passed, 0 failed, 0 errors, 0 skipped** in the final full suite (`verified-tests.xml`, `verified-tests.log`).
- Ruff lint and configured formatting checks pass for `src tests scripts`.
- All {len(inspection['imported_modules'])} application modules import; {inspection['parsed_python_files']} Python files parse.
- Clean frozen/offline validation environment: 85 installed packages compatible. Existing `.venv` was not repaired or replaced.
- Source distribution and wheel build pass; archive inspection verifies the wheel's source/governance bytes and excludes evidence/environment content from the source distribution.
- Six generated notebooks match retained assets; reporting test checks 29 PBIR files and governed field bindings.
- No static type checker is configured. One existing Starlette/httpx deprecation warning remains; it is not suppressed.

See END_TO_END_TEST_RESULTS.md for commands, intermediate attempts and actual outcomes. `source-hashes.json` binds final validation to source/config/assets. Final build outputs are validation artifacts, not a release.

## Scope decisions and limits

Required local data, analytical, persistence, orchestration, API, audit, recovery, model-research and reporting-asset paths are connected. Optional reference URLs, trade context, recurring scheduling and a custom UI remain optional/deferred. Forecast-to-ranking coupling and observed commercial shipment-SLA ML were not added.

Cloud interfaces remain conditional on the existing optional deployments. Mock contract tests do not certify Spark/Delta semantics, Azure SDK/service operation, IAM, OneLake transfer, managed identities, concurrent Blob publication, reporting-engine evaluation, model approval, alerts or production operation. The matrix states where a cloud portion was inspected rather than executed. All deployment/operational gaps remain explicit in UNRESOLVED_INTEGRATION_GAPS.md.
"""
(OUT / "CODE_INTEGRATION_REPORT.md").write_text(report, encoding="utf-8")

results = """# End-to-end test results

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
"""
(OUT / "END_TO_END_TEST_RESULTS.md").write_text(results, encoding="utf-8")

gaps = """# Unresolved integration gaps and external verification limits

## Required local code

No required local component is disconnected and no final automated test/static/build check remains failing. This is a code-level result for the implemented local analytical scope, not certification of every deployment described in historical plans.

## Existing local environment

The user's original `.venv` still contains duplicate pytz distributions and incomplete aiohappyeyeballs metadata. It was preserved. Final validation uses the separately created `validation-copy` environment; its dependency check passes. The product has not been launched in either environment.

## Conditional cloud and reporting boundaries

| Components | Remaining verification |
|---|---|
| C29, C32, C33 | Actual Spark/Delta Bronze/Silver/Gold/acceptance, prediction import and feedback MERGE; OneLake transfer; engine-level readback, retry/concurrency and multi-table publication behavior. The prediction importer was executed with a fake Delta boundary; the feedback local SQLite destination was executed. This does not verify a live Fabric transaction. |
| C30, C31 | Real Fabric item/job creation and polling, Azure ML job submission/registration/promotion/batch and effective permissions. Tests cover mocked REST/config/client boundaries and real local train/batch/monitor functions. No approved cloud model exists by this evidence. |
| C34–C37 | Actual AOAI, Entra/JWKS, Blob, managed identity, Key Vault and Monitor round trips; IAM/least privilege; live failures and concurrent Blob writer behavior. Mocks are contract evidence only. |
| C39–C41 | Execute SQL/DAX/Power Query in target engines; bind the semantic model, render, refresh and test RLS. PBIR schemas and generated mart fields pass locally. The model-binding template is still a template. |
| C38, C44, C46 | Approved immutable-retention policy, alert/action-group/on-call routing, offsite DR and measured RPO/RTO. These operational features were not invented or configured. |
| C47, C49 | Container/Compose runtime and remote CI/deployment execution. No application service was started; no remote workflow was triggered. |

These checks require target services, credentials, deployment permissions or operational decisions and are outside this task's allowed live actions. They must not be reported as successful live integrations. Static-only portions are identified per component in the matrix, rather than inferred connected from imports.

## Optional or deliberately deferred

- C02–C05: Optional WPI, UN/LOCODE, route and weather enrichment retain explicit configured/degraded behavior. Unconfigured URLs are not fabricated feeds.
- C06: WTO/Comtrade stays outside runtime scope under existing rights/data-contract decisions.
- C17, C42: Recurring scheduling and a dedicated custom web dashboard are not required by the current manual/API product.
- C27: Forecasts do not affect ranking. Supplemental forecast evidence is not an SLA probability or a calibrated improvement in recommendations.
- C28: Observed commercial shipment-SLA modeling remains deferred until representative lawful observed labels exist. Simulated shipments/outcomes remain explicitly simulated.

No live-runtime, cloud-service, reporting-engine, commercial-SLA, or production-readiness verdict is made. The existing Starlette/httpx deprecation warning remains visible; no dependency upgrade was imposed.
"""
(OUT / "UNRESOLVED_INTEGRATION_GAPS.md").write_text(gaps, encoding="utf-8")

artifacts = [
    p for p in OUT.iterdir() if p.is_file() and p.name != "evidence-manifest.json"
]
artifacts += list((OUT / "verified-build").glob("*.whl"))
artifacts += list((OUT / "verified-build").glob("*.tar.gz"))
manifest = {
    "schema_version": "1.0", "generated_at": now, "timezone": "Asia/Qatar",
    "branch": branch, "commit": commit, "verdict": matrix["verdict"],
    "scope": matrix["scope"], "tests": {"passed": len(cases), "failed": 0, "errors": 0, "skipped": 0},
    "source_hashes": "source-hashes.json",
    "changed_by_this_task": changed,
    "preserved": {"branch": True, "commit": True, "old_evidence": True, "existing_persistent_data_not_mutated": True},
    "not_performed": [
        "Git commit/push/tag/release", "application launch", "unrestricted pipeline",
        "service start/stop/restart", "live cloud/deployment", "production verification",
    ],
    "artifact_hashes": {
        p.relative_to(OUT).as_posix(): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size
        } for p in sorted(artifacts)
    },
    "manifest_scope": "Top-level evidence and authoritative verified-build archives. Self hash omitted.",
    "excluded_retained_workspaces": [
        "validation-venv", "validation-copy", "uv-cache", "pytest-cache",
        "*temp*", "build", "final-build",
    ],
    "exclusion_reason": "Disposable/failed environments, package caches and test roots remain present; authoritative results, source hashes and build archives are individually hashed instead.",
}
(OUT / "evidence-manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(json.dumps({"verdict": matrix["verdict"], "components": len(components), "tests_passed": len(cases)}))
