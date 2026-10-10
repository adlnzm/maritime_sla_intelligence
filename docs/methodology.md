# Intelligence and decision methodology v1

## Activity-deviation congestion proxy

For each port/day, use prior observations in a 56-calendar-day window, excluding the current
day. Require 28 prior observations. Baseline is mean port calls; scale is max(1, population
standard deviation). z=(current−baseline)/scale. Absolute z determines NORMAL (<1), ELEVATED
(1–2), HIGH (2–3), CRITICAL (≥3). Both unusually high and low activity merit investigation.
Insufficient history remains unknown and cannot drive a valid network state.

Percentile is the empirical rank against prior calls. Persistence counts consecutive calendar
days with |z|≥1 and resets on a gap or normal activity. Coverage is actual history count / window
length, capped at 1. It is an evidence-coverage measure, not a calibrated probability. Prior
states support historical comparisons. The method does not remove seasonality or establish
causality and must not be described as waiting time, queue length or terminal dwell.

## Dynamic network and propagation

Directed edges carry validity, availability, reference transit, stress and source classification.
The snapshot excludes expired, closed and unavailable routes. Stress is max(endpoint stress).
Alternate simple paths are ranked by transit×(1+0.25×stress). Closures can be supplied as dated
disruptions to the network engine; inferred activity deviations are not automatically closures.

Default topology is explicitly SIMULATED: each configured port pair is connected, with transit
derived from great-circle distance×1.25 / 16 knots. It is unsuitable for navigation and may
cross land; therefore the GIS export never draws these lines. Supply source-backed route GeoJSON
to replace it. Route geometry requires route_id, origin/destination publisher IDs, distance_nm,
transit_hours, available, valid_from and optional valid_to.

Propagation begins at HIGH/CRITICAL states, follows available directed edges, respects cumulative
travel time (720-hour horizon) and maximum depth 4, and attenuates exposure by 0.65 per hop.
It is a deterministic graph derivation, not observed cargo movement. The field called
propagation_confidence is explicitly typed ASSUMED_ATTENUATION_NOT_CALIBRATED. Input
classifications are retained so graph results cannot be mistaken for confirmed shipping flows.

## Synthetic scenarios and SLA

Seeded shipments choose origin/destination, route, planned transit, 6–48h SLA buffer, priority
1–3 and cargo value 10k–250k units. These ranges are modeling assumptions and are editable.
Every shipment remains SIMULATED. Planned delivery uses analysis-day midnight UTC plus transit;
promised delivery adds the SLA buffer.

Stress delay is summed node stress×36 hours. Shared lognormal draws (mean 1, sigma 0.4) model
uncertainty across paired interventions. Delay=max(0, intervention transit + stochastic stress
delay − planned transit). Breach occurs when delay exceeds the contractual buffer. The fraction
of 512 draws breaching is a simulated probability; Monte Carlo standard error describes sampling
noise only, not uncertainty about the assumptions. p10/p50/p90 describe the simulated distribution.

NO_ACTION is the base route. REROUTE evaluates an alternative simple path. ALTERNATE_PORT requires
a different discharge port in the destination country within 300nm plus a 24h last-mile allowance;
otherwise it is explicitly infeasible. EXPEDITE reduces sailing time by 15% for 1800 units.
PRIORITIZE reduces stress delay by 30% for 600×priority units. No intervention assumes unlimited
real carrier capacity: feasibility here is topological and modeled, requiring operator confirmation.

Expected loss=breach probability×cargo value×0.02×priority. Rank feasible actions by operational
cost+expected loss; report reduction relative to NO_ACTION. Recommendation confidence remains
uncalibrated, never an invented percentage. Currency units must be aligned before real use.

## ML

The target is next-day public port-call count, not simulated SLA outcomes. Features are previous
day, previous week, prior-week mean/std and weekday. Missing calendar days remain missing. Only
OBSERVED input is eligible; require 120 usable calendar days and 300 rows. Otherwise report
DEFERRED — INSUFFICIENT VALIDATED HISTORY.

Candidates: persistence, standardized ridge (alpha 1/10), random forest (depth 4/8, 80 trees).
Imputation/variance selection/scaling are fit within training folds for ridge. Expanding temporal
folds in the first 70% select lowest mean MAE. Next 15% calibrates a 90% split-conformal interval;
last 15% is untouched holdout. All ports share date boundaries. Report MAE, RMSE, baseline MAE,
holdout interval coverage, per-port errors, feature mean-shift drift and exact periods/versions.
Temporal dependence means conformal nominal coverage has no unconditional guarantee.

The selected model remains fit on selection data for transparent holdout evaluation and subsequent
batch inference. Registry files and joblib artifacts persist. No SLA ML performance is claimed
without observed operational outcomes. A model winning training folds may lose to persistence
on holdout: that result is retained, not hidden.

## GenAI and learning loop

`genai.extract` accepts text plus its source and retrieval time and calls a configured Azure OpenAI
v1 chat endpoint. Quote, event, location and time must each be exact source spans. Invalid outputs
are rejected and counted. Accepted extraction is ANTICIPATED and UNCONFIRMED; literal grounding
does not establish truth or entailment. It cannot mutate observed state automatically.

Run `maritime extract-evidence --input article.txt --source https://publisher.example/article`
after setting AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT (plus managed identity or an optional API key). The original text is retained in
Bronze and accepted/rejected extraction metrics are persisted in the extraction audit. `/signals`
exposes those audit results to authenticated readers. No provider call is claimed validated without
configured credentials and an actual response.

Operator reviews record accept/reject/override and reason. Outcomes record actual action, delay,
loss and evidence. Comparison produces delay/loss errors and Brier score for simulated probability
calibration. Synthetic shipments reject OBSERVED outcomes. Causal effectiveness remains unknown
because the unchosen action's outcome is unobserved. The architecture retains the information
needed for future observed-shipment integration; it does not invent that history.

Production training and registration execute in Azure ML using the same temporal experiment.
Fabric exports the versioned observed feature contract; it does not run production training.
See [Azure lifecycle](azure.md) for promotion, batch return and monitoring. Local artifacts
remain available for reproducible validation.
