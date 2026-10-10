# Microsoft Fabric deployment and validation

The implementation follows Microsoft's [notebook definition API](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/notebook-definition)
and [Data Factory REST API](https://learn.microsoft.com/en-us/fabric/data-factory/pipeline-rest-api-capabilities).
Real target-workspace execution is still required: valid-looking definitions are not proof of deployment.

## Prerequisites

- A Fabric-capacity workspace, contributor-level deployment identity, and tenant permission for
  the chosen user/service principal to use Fabric APIs and OneLake.
- `FABRIC_WORKSPACE_ID`; optionally `FABRIC_LAKEHOUSE_ID` for an existing Lakehouse.
- DefaultAzureCredential via Azure CLI or `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
  GitHub uses workload federation through azure/login rather than committing a client secret.
- Notebook Spark runtime with network access to configured public sources and Python package index.
- Permission to upload the application wheel and configuration into the Lakehouse Files area.

## Assets and commands

`python scripts/build_fabric_assets.py` generates four ipynb artifacts. `uv build` builds the
application wheel. `python scripts/deploy_fabric.py --execute` creates or updates the owned names,
uploads wheel/configuration, attaches the Lakehouse, creates the dependency-ordered pipeline and
executes it. All stages receive the same pipeline run ID and analysis date.

Bronze retains raw source bytes and normalized ingestion snapshots; Silver performs Spark casts,
duplicate/schema checks and shared contract/freshness validation; Gold computes Spark rolling
baselines, executes the shared decision pipeline and materializes Delta marts; acceptance reads
each persisted table back and verifies counts before writing the published-run manifest.

Create/update APIs poll long-running operations. The execution monitor checks terminal job status;
failure/timeout produces a nonzero exit. `fabric/deployment.json` contains item IDs and actual job
results and is excluded from Git. Stage evidence is in `Files/maritime/runs/<run_id>/`.
The acceptance result is `fabric-report.json`; retain it with CI artifacts.

## Boundaries requiring target-workspace validation

Fabric Python library/runtime compatibility, OneLake permissions, notebook attachment and pipeline
activity schema must be tested in the actual tenant. Shared logic runs locally but no local mock
establishes those cloud properties. APIs and capacity policies can change independently.

Fabric Bronze restores its revision-window checkpoint from OneLake; Silver advances it only after
shared DQ succeeds. Local execution uses the same cache semantics. Delta output is idempotent by run
partition, but scheduling should prevent concurrent publication. Graph/scenario/ML stages use
bounded driver memory; Spark handles the scalable baseline and table transformations.
Optional WPI/weather/UNLOCODE ingestion runs independently in Fabric Bronze and local execution;
configure public download versions and promote source-backed snapshots deliberately.

SQL views and Power BI measures are supplied, but tenant report publication remains separate.
The API reads its local SQLite adapter. Download the verified Gold run directory from
`Files/maritime/runs/<run_id>/evidence/gold/<run_id>/` and its `fabric-report.json`, then execute:

```sh
maritime import-gold --folder exported-gold --report fabric-report.json --data-dir data
```

This validates run identity and required products before publication. Do not point SQLite at OneLake.
