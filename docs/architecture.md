# Architecture and contracts

## Business problem

Port activity can change before downstream service commitments are missed. This system retains
the evidence, reconstructs a daily stress proxy, explores exposure through an explicitly modeled
network, and compares interventions for synthetic operational scenarios. Its output supports an
operator's investigation; actual maritime routing requires navigable routes and carrier capacity.

## Execution

`sources.py` retrieves and hashes public responses. PortWatch pagination uses stable ObjectId
ordering and fails on schema errors. An activity checkpoint is scoped to configured port IDs;
the last 14 days are replaced each run to capture revisions and deletions. Data before that window
is retained within the configured history horizon. Delete the scoped cache metadata for a full
revision reload. Raw files are content-addressed and never overwritten with different bytes.

`quality.py` validates strict Pydantic contracts, ranges, duplicates, foreign keys, freshness,
classification, future observations and route validity. Rejected input is retained in Bronze;
critical violations prevent Gold publication. Score alone cannot override a failed check.

`intelligence.py` computes rolling activity statistics, current states, graph state and bounded
propagation. `scenarios.py` creates shipments and paired outcome distributions. `ml.py` forecasts
port calls independently. `pipeline.py` writes dimensional/fact products, field lineage, GIS,
metrics and reports. `api.py` exposes the published run and append-only review/outcome audit.

## Storage and table model

| Grain | Local product | Fabric table |
|---|---|---|
| Port | ports | dim_ports |
| Directed route | routes | dim_routes |
| Location | dim_location | dim_location |
| UTC calendar day | dim_time | dim_time |
| Source | sources | dim_sources |
| Synthetic shipment/scenario | scenarios | dim_scenarios |
| Intervention type | dim_intervention | dim_intervention |
| Port/day activity | activity | fact_activity |
| Port/day proxy state | congestion_history | fact_congestion_history |
| Current port state | congestion | fact_congestion |
| Directed edge/run | network | fact_network |
| Signal/port | disruptions | fact_disruptions |
| Origin/exposed node/path | exposure | fact_exposure |
| Shipment/no-action outcome | sla_risk | fact_sla_risk |
| Shipment/intervention | interventions | fact_interventions |
| Shipment recommendation | decisions | fact_decisions |
| Early warning | early_warning | fact_early_warning |
| Port/forecast day | predictions | fact_predictions |
| Output field/run | lineage | fact_lineage |

Products include run IDs; analytical records preserve classification and lineage references.
Port IDs come from the publisher; scenario/route/model IDs use stable SHA-256-derived keys.
Field lineage records source IDs, upstream products, upstream hashes, transformation and
methodology version. The record-level lineage reference identifies contributing snapshots.
Do not interpret lineage metadata itself as evidence that simulated values were observed.

Run timestamps are timezone-aware UTC. Public daily observations use publisher UTC date semantics.
Routes include valid_from/valid_to. Historical states remain queryable by run and date.

## Transaction and scaling boundaries

Local writes are transactional per product. Failed attempts remain inspectable, while the API
reads only the last fully published run. A single writer per data directory is required; concurrent
API readers use SQLite WAL. For horizontally scaled API writes, replace the storage adapter with
a managed transactional database. Fabric performs distributed casts, duplicate validation and
calendar rolling baselines in Spark; the graph/scenario workload is bounded on the driver.
The million-record guard is explicit. This is not an unlimited global graph execution engine.

No API request initiates arbitrary source retrieval or loads an untrusted model file.
Model artifacts must come from the local training registry: joblib is not a safe format for
untrusted artifacts.
