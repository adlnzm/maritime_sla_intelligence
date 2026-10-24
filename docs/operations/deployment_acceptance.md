# Deployment acceptance handoff — 2026-10-14

All target gates below are **BLOCKED — DEPLOYMENT ACTION REQUIRED** until executed with retained target evidence. Local compilation, contracts and fault tests do not pass these gates. Owners and escalation contacts are UNASSIGNED; retention, RPO/RTO and performance targets are UNAPPROVED. No model is approved for production. Shipment-SLA ML is deferred for lack of representative observed shipment outcomes; the implemented model forecasts port calls.

Run from the repository root in PowerShell. Replace placeholders with owner-supplied values; do not copy tokens or secret values into evidence. Use a new evidence folder per deployment. Set nonsecret values from `.env.example` explicitly: the application does not load it automatically. Retain command, UTC start/end, exit code, redacted output and resource/job/run IDs for every command. A nonzero command stops advancement.

## 1. Identity, configuration and owner approval

Owner supplies tenant, subscription, existing resource group and region, prefix, immutable image digest, registry/pull identity, API app audience and Reader/Operator app assignments, existing OpenAI account and model deployment, Fabric capacity/workspace/lakehouse IDs, AML workspace/compute/quota, and network allowlists. Obtain signed retention duration/lock approval separately; do not deploy retention before it exists.

Provisioning identity needs resource writes on the selected resource group and role-definition/role-assignment writes at the relevant scopes. Use resource-group-scoped Contributor plus narrowly delegated RBAC administration or a custom deployment role; do not grant subscription Owner. API identity receives serving-container read, the template's audit write/read role without delete, OpenAI inference, and Key Vault secret read only if needed. Serving publisher receives Blob Data Contributor only on the serving container. Review inherited grants before acceptance.

Fabric deploy/run identity: Contributor on the intended capacity-backed workspace and the required OneLake item permissions; tenant administrator enables service-principal use if selected. AML runner: AzureML Data Scientist scoped to workspace, with only needed input/output storage access; compute provisioning stays with the deployment operator. Separate the promotion approver from ordinary job submission. Reporting author needs semantic-model Build and publish rights; consumers should be viewers, with approved RLS roles where data requires them. See [Fabric roles](https://learn.microsoft.com/en-us/fabric/get-started/roles-workspaces) and [AML roles](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles).

```powershell
az login --tenant $env:AZURE_TENANT_ID
az account set --subscription $env:AZURE_SUBSCRIPTION_ID
powershell -File scripts/deployment_preflight.ps1 -Output evidence/target-preflight.json
az role assignment list --all --include-inherited --scope /subscriptions/$env:AZURE_SUBSCRIPTION_ID/resourceGroups/$env:AZURE_RESOURCE_GROUP -o json
```

Expected: configuration checks true, account/tenant match, group readable, reviewed least-privilege assignments. Capture the preflight and role inventory in restricted evidence. Preflight does not prove effective authorization. Remedy wrong scope or missing grants, then rerun; remove temporary deployment privileges after acceptance.

## 2. Azure validation, deployment and application

Create a private parameter file `data/target.parameters.json` containing apiImage (digest), apiAudience, openAIAccountName, openAIDeployment, location, prefix, computeSku and owner-approved auditRetentionDays. No secrets belong in it. Private registry authentication and organization-specific private endpoints/firewalls are not configured by the current template: resolve them before exposing production traffic. The template has TLS ingress and HTTPS storage, but does not establish private network isolation.

```powershell
az deployment group validate -g $env:AZURE_RESOURCE_GROUP -f azure/main.bicep -p '@data/target.parameters.json'
az deployment group what-if -g $env:AZURE_RESOURCE_GROUP -f azure/main.bicep -p '@data/target.parameters.json'
az deployment group create -g $env:AZURE_RESOURCE_GROUP -n maritime-accepted-release -f azure/main.bicep -p '@data/target.parameters.json'
az deployment group show -g $env:AZURE_RESOURCE_GROUP -n maritime-accepted-release -o json
az resource list -g $env:AZURE_RESOURCE_GROUP -o json
az containerapp show -g $env:AZURE_RESOURCE_GROUP -n <api-name> -o json
```

Expected: validation success, reviewed what-if, provisioningState Succeeded, intended image digest, managed identity and TLS configuration, healthy revision after publishing accepted data. Set production `MARITIME_AUTH_MODE=entra`, `MARITIME_STORAGE_BACKEND=azure_blob`, tenant/audience, storage URL/container names, OpenAI endpoint/deployment, telemetry connection, and optional Key Vault URL/secret reference. Prefer managed identity; keep client secrets/API keys in Key Vault or platform secret references. Do not export container environments into public evidence.

Verify `Invoke-WebRequest https://<fqdn>/health/ready` returns 200 only with available accepted data; call `/ready`, `/decisions`, `/audit` with properly scoped bearer tokens. Repeat with no token, expired/wrong-audience token, Reader write attempt and Operator write: expect denied access for unauthorized cases, accepted authorized action and matching audit identity. Restart the revision and compare publication and audits. Record request IDs/statuses, never bearer tokens. Test storage access loss on an isolated acceptance revision and expect readiness 503 until recovery. Roll back using `az containerapp update -g <rg> -n <api> --image <previous-digest>` and verify the prior compatible release; do not delete audit storage or downgrade database schema.

## 3. Fabric ingestion and feedback

```powershell
uv build
python scripts/build_fabric_assets.py
python scripts/deploy_fabric.py --execute
python scripts/fabric_feedback.py --run-id <accepted-run> --evidence evidence/feedback-first.json
python scripts/fabric_feedback.py --run-id <accepted-run> --evidence evidence/feedback-replay.json
```

Owner supplies capacity/runtime, source credentials and outbound connectivity, workspace/lakehouse IDs and accepted source contract versions. Expected: terminal successful notebook/pipeline jobs, persisted Delta counts/hashes matching stage receipts, accepted publication, retained provenance/classification/lineage, feedback duplicates on replay without data loss. Capture `fabric/deployment.json`, notebook logs and `Files/maritime/runs/<run>/` receipts and actual SQL/Delta readback. Inject an invalid source contract in a disposable run and verify failed accounting and unchanged publication. Restore previous notebook definitions/accepted run on failure; retain failed run receipts. Details: `docs/fabric.md` and `docs/operations/production_closure.md`.

## 4. Azure ML

```powershell
python scripts/fabric_ml_bridge.py download-features --run-id <accepted-run> --folder data/target-features
python scripts/azure_ml.py train --data data/target-features --output data/target-training
# Only after an identified approver reviews actual holdout metrics and artifact hashes:
python scripts/azure_ml.py promote --model-version <candidate-version> --approver <named-approver>
python scripts/azure_ml.py batch --data data/target-features --model-version <approved-version> --output data/target-batch
python scripts/fabric_ml_bridge.py upload-predictions --run-id <accepted-run> --folder <downloaded-prediction-folder>
python scripts/fabric_ml_bridge.py publish-serving --run-id <accepted-run> --folder data/target-serving
```

Expected: completed real jobs, downloaded evaluation and integrity manifests, registered candidate linked to job, explicit approved version, compatible inference outputs and Fabric readback. Capture job.json, registration.json, evaluation/model hashes and approver record. Failed or ineligible jobs must not be promoted. Restore the prior approved model version and accepted serving run on failure. No shipment-SLA performance claim follows from port-call forecasting.

## 5. Azure OpenAI

Owner supplies reachable authorized endpoint/deployment, quota, managed identity with Cognitive Services OpenAI User at account scope, or an authorized Key Vault secret. Execute:

```powershell
python -m maritime.cli extract-evidence --input <retained-public-text> --source <original-public-url> --data-dir data/target-aoai
```

Expected: actual authorized response, grounded spans, ANTICIPATED classification and audit records; capture request ID, deployment/model version, latency, token accounting if returned, grounding receipt and redacted service errors. Repeat on an isolated configuration with unavailable/unauthorized deployment and controlled quota exhaustion; verify bounded retries/timeouts and no fabricated fallback. Inspect input/body/output limits in `src/maritime/genai.py` against tenant quotas. On failure disable extraction, retain failure accounting, and restore previously approved configuration. Local mocked transport tests are only contract tests.

## 6. Power BI

Reporting/data owner creates the semantic model over accepted Gold tables, names and types from `docs/reporting.md`, with run_id in relationships and approved measures from `fabric/powerbi/measures.dax`.

```powershell
python scripts/build_powerbi.py --output data/BoundMaritime.Report --semantic-model-id <actual-model-uuid>
```

Open `data/BoundMaritime.Report/definition.pbir` in Power BI Desktop. Authenticate and render all five pages; compare row counts, filters, measures, null infeasible interventions and classifications with Gold. Verify run isolation, relationships, refresh, RLS positive/negative users and service publish. Capture screenshots, report/model IDs, refresh history and role results. UI execution is required; no command-line schema check substitutes for it. Preserve prior report/model versions and revert both on failure. Network geometry/review-status extensions described in reporting.md remain outside the authored core visuals and require owner scope acceptance.

## 7. Retention, immutability and access

Security/data owner signs duration, lock consequences, exception handling and expiry-test plan before deployment/locking. [Microsoft's container policy procedure](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-policy-configure-container-scope) requires obtaining the current ETag before locking.

```powershell
az storage container immutability-policy show --account-name <account> --container-name maritime-audit --resource-group <rg>
# Only with explicit lock approval and the returned ETag:
az storage container immutability-policy lock --account-name <account> --container-name maritime-audit --resource-group <rg> --if-match <etag>
az storage container immutability-policy show --account-name <account> --container-name maritime-audit --resource-group <rg>
```

Using the actual application identity, attempt `az storage blob upload --auth-mode login --account-name <account> --container-name maritime-audit --name <disposable-existing-blob> --file <changed-test-file> --overwrite true` and `az storage blob delete --auth-mode login --account-name <account> --container-name maritime-audit --name <disposable-existing-blob>`. Expect both denied; read back and compare original SHA-256. Capture Locked state/duration/ETag, role inventory, denied operations, original/readback digests. An unlocked policy is not accepted. Observe an approved disposable policy through real expiry and test deletion with the designated retention administrator; the application's no-delete role should still deny deletion after expiry. Locking cannot be rolled back by reducing retention. Break-glass requires named security approval, monitored privileged access and immutable incident evidence, never bypassing locked retention.

## 8. Monitoring, ownership and recovery

Platform owner must name primary/on-call/escalation contacts; approve alert windows, RPO/RTO, offsite location/encryption and workload targets. Monitor readiness and freshness externally, terminal pipeline/feedback failures, integrity/accounting failures, auth anomalies and ML drift. Configure an Azure Monitor action group and alert rules in the target subscription using approved contacts; capture `az monitor action-group show -g <rg> -n <group>` and `az monitor scheduled-query list -g <rg>`. No notification destination or alert threshold is invented here.

Authorize failure injection against a disposable revision/job, capture correlated logs, fired alert and actual received notification with timestamps. Restore service and verify alert resolution. Application Insights deployment alone is insufficient. Roll back faulty alert rules to their saved definitions without silently dropping monitoring.

Execute `maritime backup --help` and `maritime restore --help` for the checked-in CLI, then use the documented source/destination flags in `docs/operations/READY_TO_RUN.md`. Restore to a fresh location, compare SHA-256 manifest, SQLite integrity, audit chain and published run before switching traffic. Separately copy encrypted backups to the approved offsite destination, simulate loss of the primary, restore with the recovery identity and measure actual elapsed time/data loss against approved targets. Capture access/restore logs and failover tests. Local restore is not verified disaster recovery or production RPO/RTO. Retain original data and revert the data-directory/serving pointer if acceptance fails.

## Optional images

No image-generation environment or assets are required or created for this release. The Docker build has no dependency on image generation. Any future workflow must use a dedicated isolated environment/output volume, no application secrets/database/socket mounts, explicit limits and network-off by default; approved assets need filename/hash/provenance records and secret inspection before runtime inclusion.
