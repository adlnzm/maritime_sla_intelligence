# Operations and recovery

## Run lifecycle

Each attempt has an immutable run ID, UTC start/end, duration, stage status, source events and
errors. Bronze responses are content-addressed. Silver/Gold snapshots are scoped to a run.
Only success advances the publication pointer. Inspect the latest-attempt report independently
of the published run: the API can serve last-good data while a new run has failed.

1. Run `maritime report` and inspect `failures`, `source_status`, and `data_quality.errors`.
2. For network/429/5xx errors, the source layer retries four total attempts with backoff.
3. For contract changes, retain the failed raw response, update the adapter and add a fixture test.
4. For freshness failures, inspect publisher lag; never relabel stale data as current.
5. Repair the source/configuration and rerun. Recent activity is replaced over the revision window.
6. For older corrections, clear the scoped `activity_cache:<scope>` metadata (retain a backup),
   then rerun to request the configured history again.

Optional integrations fail independently; critical public sources/DQ stop the run. Source error
responses remain distinguishable from a successful empty response. Do not run concurrent pipeline
writers against one local store. Back up SQLite using its backup API or while writers are stopped;
retain source hashes, model registry, audit and run reports together.

## Metrics dictionary

| Metric | Meaning |
|---|---|
| records_ingested | Normalized ports + activity rows in run history |
| records_processed / rejected | DQ input count / rejected contract or key violations |
| completeness_rate | 1 − missing required-field errors / input records |
| duplicate_rate | Repeated natural-key records / input records |
| referential_integrity_rate | 1 − orphan activity/route rows / activity+route rows |
| overall_dq_score | max(0, 1 − check failures / input records); critical failures still block |
| freshness_status | Every selected port has a latest date within the configured threshold |
| affected_nodes / depth | Distinct exposure destinations / maximum traversed hops |
| scenario executions / infeasible | All evaluated alternatives / alternatives rejected by feasibility |
| expected_breaches | Sum of simulated NO_ACTION breach probabilities |
| expected_loss / benefit | Modeled late penalty / reduction in total modeled cost |
| decision confidence | Unknown until validated against appropriate operational evidence |
| ML MAE / RMSE | Holdout port-call errors; not shipment SLA error |
| grounding_rate | Accepted exact-span extractions / all extracted candidates; null when none |
| retries / timeouts / recoveries | Actual transport events counted during execution |

`/metrics` exposes Prometheus-compatible numeric text for API request/error/latency totals,
pipeline duration, DQ score, scenario count and decision count. API counters are process-local
and reset on restart; pipeline reports are persistent. Scrape through authenticated TLS ingress.
No zero-valued gauge should be interpreted as evidence that a stage was configured and executed.

## Security and deployment

Secrets come from environment/managed identity and are excluded from Git. Never place secrets
in source registry URLs; use headers or a secret-aware adapter for authenticated sources.
Reader and operator keys are separate; absent keys fail closed. Named actor values are
self-reported under the operator key; use identity-gateway claims for accountable enterprise users.
TLS termination, rate limiting, key rotation, centralized logs, backups and retention policy are
operator deployment responsibilities. Synthetic decisions do not execute commercial actions.

GitHub CI is repeatable from `uv.lock`, uploads test/build evidence, and fails critical checks.
Fabric deployment is environment-gated and manually dispatched. Validate a target workspace before
promoting its configuration to production. No workspace/credentials means ENVIRONMENT_DEPENDENT.

## Known operational bounds

Default scope is six ports and 240 days, not all global shipping. Local storage and graph engines
are single-host. Public activity revisions outside the overlap require full refresh. Source terms,
rate limits and availability are outside this repository's control. Fabric and Docker validation
must be measured in their real execution environments; local tests cannot substitute for them.
