# Operational reporting

Gold JSON marts support local Power Query import through `fabric/powerbi/local-import.pq`.
Fabric notebooks publish typed Delta dimensions/facts for the Lakehouse SQL endpoint. Apply
`sql/reporting.sql` after a successful acceptance run. Use run_id alongside natural keys to avoid
joining history from different runs. `fabric/powerbi/measures.dax` contains operational measures.

Suggested report pages:

1. Executive control tower: port stress category and evidence date, exposed nodes, simulated
   at-risk shipments, recommendation counts and expected modeled cost reduction.
2. Congestion intelligence: calls and prior baseline by port/date, deviation, persistence and
   evidence coverage. Include the activity-proxy caveat in the page subtitle.
3. Network impact: edge availability, propagation origin/depth/travel hours and alternate paths.
4. SLA risk: shipment priority, buffer, expected delay, simulated probability and expected loss.
5. Intervention: all five alternatives, infeasibility reason, cost, benefit and review status.

Each visual should show classification and run/as-of date. Do not label simulated expected benefit
as realized savings. API audits contain operator reviews; they are not automatically replicated to
Fabric from a separate API deployment. An ingestion job is needed when deploying those separately.

`operational.geojson` contains current port stress points and only source-supplied route geometry.
Inspect evidence date and category to prioritize port investigations. Assumed great-circle
connectivity is excluded from route mapping because it is not navigable geometry. No PBIX report
or Power BI tenant deployment is claimed validated in the absence of an actual tenant execution.
