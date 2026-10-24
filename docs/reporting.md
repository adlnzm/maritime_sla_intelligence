# Operational reporting

Gold JSON marts support local Power Query import through `fabric/powerbi/local-import.pq`.
Fabric notebooks publish typed Delta dimensions/facts for the Lakehouse SQL endpoint. Apply
`sql/reporting.sql` after a successful acceptance run. Use run_id alongside natural keys to avoid
joining history from different runs. `fabric/powerbi/measures.dax` contains operational measures.

The authored PBIR pages implement the core analytical tables and run/date/classification filters. The broader intended page scope remains:

1. Executive control tower: port stress category and evidence date, exposed nodes, simulated
   at-risk shipments, recommendation counts and expected modeled cost reduction.
2. Congestion intelligence: calls and prior baseline by port/date, deviation, persistence and
   evidence coverage. Include the activity-proxy caveat in the page subtitle.
3. Network impact: edge availability, propagation origin/depth/travel hours and alternate paths.
4. SLA risk: shipment priority, buffer, expected delay, simulated probability and expected loss.
5. Intervention: all five alternatives, infeasibility reason, cost, benefit and review status.

Each visual should show classification and run/as-of date. Do not label simulated expected benefit
as realized savings. API audits contain operator reviews; they are not automatically replicated to
Fabric without an explicit transfer. Use `scripts/fabric_feedback.py --run-id <run> --evidence <file>`
after deploying the `import_feedback` notebook. It imports a classified, checksummed audit snapshot
into `fact_learning_feedback` and requires matching Delta readback. Local export is also available
at the operator-only `/learning/export` endpoint. Cloud execution remains unverified.

`operational.geojson` contains current port stress points and only source-supplied route geometry.
Inspect evidence date and category to prioritize port investigations. Assumed great-circle
connectivity is excluded from route mapping because it is not navigable geometry. No PBIX report
or Power BI tenant deployment is claimed validated in the absence of an actual tenant execution.

## Authored project and remaining acceptance

`scripts/build_powerbi.py` produces `fabric/powerbi/Maritime.Report`: five pages and 20 visuals, checked offline against Microsoft's PBIR JSON schemas. Field bindings are checked against an actual governed local pipeline run. Infeasible interventions have blank estimates, never zero loss. Schema acceptance is not a render/filter test.

1. After a successful Fabric acceptance run, create the semantic model over the governed fact_congestion, fact_congestion_history, fact_exposure, fact_sla_risk and fact_interventions tables, with exactly those names. Restrict it to the accepted run or require run selection; do not join natural IDs across runs. Set dates/timestamps correctly and retain nullable intervention metrics.
2. With the real semantic model UUID, run `python scripts/build_powerbi.py --output data/BoundMaritime.Report --semantic-model-id <real-uuid>`. Without a UUID the generator deliberately writes definition.pbir.template, not a falsely connected report.
3. Open the resulting definition.pbir in supported Power BI Desktop, authenticate, and verify each page against the accepted Gold rows. Test run/date/classification filters, empty exposure, infeasible alternatives and cross-run isolation. Capture report screenshots, filtered row counts and refresh history. Complete the intended network geometry and review-status visuals using the governed network/feedback marts if required for the tenant's final report acceptance; the current authored core pages do not claim those additional visuals.
4. Save/publish with an authorized identity. Configure semantic-model refresh/service credentials, reader/workspace permissions and any required RLS. Confirm an unauthorized viewer cannot read protected outcomes, and a refresh uses the approved run. Retain the real report/model IDs and results before BI-02 can pass.

No Desktop installation/session or tenant binding is available in this environment. PBIX, rendering, DAX execution, filter behavior and service refresh remain BLOCKED_EXTERNAL. Format reference: https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report .
