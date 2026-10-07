# Maritime Congestion & SLA Intelligence Platform

Early-warning, impact analysis and decision support for maritime supply-chain disruptions.

This repository implements a public-data-to-decision pipeline with retained source responses,
validated contracts, run-versioned data, activity-deviation intelligence, temporal network
exposure, reproducible shipment simulations, counterfactual interventions, cost-based decisions,
chronologically validated port-call forecasting, an authenticated FastAPI service, and Fabric assets.

**Interpretation:** PortWatch activity deviation is a proxy for port stress, not measured vessel
waiting time. Shipments, assumed routes, delay distributions, SLA probabilities and intervention
benefits are explicitly **SIMULATED**. No carrier/customer shipment history is available.
Default route connectivity is an assumption, not a claim about actual shipping services.
Consult [validation evidence](evidence/README.md) before drawing deployment conclusions.

## Local setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required. Commands run from this repository.
The committed `uv.lock` resolves direct and transitive dependencies.

```powershell
# Windows: needed for Python 3.11 editable imports under non-ASCII paths.
$env:PYTHONUTF8 = "1"
uv sync --frozen --extra dev --extra fabric
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
```

On Linux/macOS, use `export PYTHONUTF8=1` instead of the PowerShell assignment.
No database server is required locally. The first run initializes SQLite with WAL and migrations
defined in `Store`. Use one pipeline writer per data directory.

## Execute and inspect

```powershell
# Live public observations; critical source failure stops publication.
uv run maritime run --as-of 2026-10-07
# Later dates: omit --as-of to use the current UTC date.

# Historical replay of retained public observations, when the sample is present:
uv run maritime run --fixture tests/data/portwatch_sample.json --data-dir data/replay

# Latest attempt, including failures:
uv run maritime report
```

Raw responses are in `data/bronze/`; validated snapshots in `data/silver/<run_id>/`;
JSON reporting marts and GIS in `data/gold/<run_id>/`; JSON/Markdown reports in
`data/reports/<run_id>/`. SQLite retains all attempted runs and all published products.
The published-run pointer changes only after every core stage succeeds.

Configure ports, history, freshness limits, random seed and intervention assumptions in
`configs/pipeline.json`. Source contracts and adapter URLs are in `configs/sources.json`.
WPI, UN/LOCODE downloads and public route geometry are independently configurable. Missing
optional sources are exposed as NOT_CONFIGURED or FAILED_OPTIONAL, never silently fabricated.
Open-Meteo reanalysis is retained as DERIVED reference evidence; it does not masquerade as a
direct weather observation or automatically close ports.

## API

Generate independent read and operator secrets locally; never commit them. `.env.example`
documents names but is not automatically loaded by the Python process.

```powershell
$env:MARITIME_API_KEY = [guid]::NewGuid().ToString("N")
$env:MARITIME_OPERATOR_KEY = [guid]::NewGuid().ToString("N")
uv run maritime serve
Invoke-RestMethod http://127.0.0.1:8000/ports -Headers @{"X-API-Key"=$env:MARITIME_API_KEY}
```

OpenAPI is at `/docs`. `/health` is public liveness; `/ready` requires a published run and a key.
Read endpoints: `/ports`, `/congestion`, `/congestion/history`, `/network`, `/network/exposure`,
`/disruptions`, `/scenarios`, `/sla-risk`, `/interventions`, `/decisions`, `/lineage`,
`/data-quality`, `/predictions`, `/early-warning`, `/run-report`, `/metrics`.
Lists support `limit` (1–1000), `offset`, and optional `run_id`.

Operator endpoints: `POST /decisions/{id}/review` (accept/reject/override with reason),
`POST /outcomes`, and `GET /audit`. Outcomes for synthetic shipments must remain SIMULATED.
Review is an audit record; it never sends a carrier instruction. API-key roles are a foundation;
deploy behind TLS and an identity gateway for named-user RBAC and centralized audit retention.

## Containers

Set the two API keys in `.env` locally, then:

```sh
docker compose --profile pipeline run --rm pipeline
docker compose up --build -d api
```

Containers run as a non-root user. A named volume shares pipeline data with the API.
Docker availability and runtime validation are separately recorded in the evidence report.

## Microsoft Fabric

```powershell
uv build
uv run python scripts/build_fabric_assets.py
$env:FABRIC_WORKSPACE_ID = "<your-workspace-uuid>"
# Optional existing Lakehouse; otherwise creates MaritimeIntelligence.
$env:FABRIC_LAKEHOUSE_ID = "<your-lakehouse-uuid>"
# Authenticate with az login or the AZURE_* environment variables in .env.example.
uv run python scripts/deploy_fabric.py --execute
```

Deployment uploads the wheel and configuration, creates/updates four notebooks and a Data
Factory pipeline, runs Bronze → Silver → Gold → acceptance, polls the real job, and persists
deployment/job evidence. No settings means a nonzero preflight exit, not a false success.
The acceptance notebook verifies actual Delta row counts before recording a published run.
See [Fabric deployment](docs/fabric.md) for identity, capacity, reporting and known limits.

## Further documentation

- [Architecture, data model and contracts](docs/architecture.md)
- [Intelligence, scenario, SLA, ML and GenAI methods](docs/methodology.md)
- [Sources, classification, provenance and licensing](docs/sources.md)
- [Operations, failure recovery, security and metrics](docs/operations.md)
- [Power BI and GIS reporting](docs/reporting.md)
- [Measured validation and remaining external dependencies](evidence/README.md)

GitHub workflows run formatting, lint, contracts, algorithm regressions, full integration/API
tests and package builds. The Fabric workflow is manually dispatched against a configured
`fabric` environment. A configured Git remote and credentials are needed to publish this repo.
