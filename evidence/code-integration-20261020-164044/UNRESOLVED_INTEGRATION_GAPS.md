# Unresolved integration gaps and external verification limits

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
