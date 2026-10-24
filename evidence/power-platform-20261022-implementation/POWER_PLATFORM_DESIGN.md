# Implemented Power Platform interfaces and artifacts

## Connected local code

`operations.py` consumes pinned approved weekly Gold and keeps a separate SQLite operational store. Transactional reviews require IGNORE/MONITOR/ESCALATE, a reason, the expected version and risk revision. Ignoring HIGH/CRITICAL needs at least forty trimmed characters. The API obtains identity from existing verified Entra claims; it rejects a client-supplied actor. Stable request IDs provide idempotency; conflicting decisions return 409. Immutable action history retains previous action, actor, ownership, time, run, classification and lineage.

Gold synchronization creates a durable deduplicated event for an initial eligible flag or a transition into HIGH/CRITICAL. Claims are leased; transport failure schedules bounded retry, worker expiry creates an auditable failed attempt, stale/superseded results become exceptions, and missing recipients never cause a send. Acknowledgements are idempotent and reject expired/conflicting leases. Gold calculations never depend on user decisions or notification outcomes.

`operations_api.py` connects queue/filter/paging, reviews/history, observation drill-through, events/claim/result and reporting to the same services. Reader and Operator roles follow the existing API authorization. Invalid/unavailable workflow configuration returns a sanitized 503.

## Generated artifacts

- `power-platform/schemas/`: actual Pydantic Silver, Gold, review and delivery contracts.
- `power-platform/connector/openapi.json`: OAuth2 custom connector operations matching real API routes and parameters.
- `power-platform/canvas/`: schema-checked screen source, supported code-view controls and explicit App/Screen property setup. No .msapp or deployed app is claimed. Generated .pa.yaml is a source reference; use Studio code view and set properties, then compile/validate in the tenant.
- `power-platform/automate/`: schema-checked recurrence flow, custom-API claim/ack, Outlook send, failure branches, connection placeholders and recipient exception path. The real service is tested with injected notification transports. No real email was sent.
- Existing `fabric/powerbi/Maritime.Report`: ten schema-validated pages, preserving the original five and adding queue/history/escalations/Hamad/portfolio. `power-platform/reporting/` contains typed Power Query imports, DAX measures, table contracts and explicit many-to-one history/event relationships to Gold review IDs. All client risk displays use server-produced classifications.
- `scripts/export_operations.py`: authenticated HTTPS snapshot export with timeout, required-table validation, redirect refusal and no overwrite. In-process API export is tested. Exported human reasons/identities require restricted access.

Detailed setup is in `power-platform/README.md`. No tenant or credentials were available or required for the local contract tests.

## Honest validation boundaries

The official workflow JSON schema passes offline. The upstream Canvas schema contained an invalid regex with an unmatched closing parenthesis in CodeComponent-ComponentName. The original is preserved as `canvas-schema-original.json`; only the optional publisher-prefix regex group was corrected to make the schema usable. The source and correction are recorded in `configs/powerplatform_schemas/sources.json`. Other constraints remain intact. The full screen passes that corrected schema. Schema validity does not establish Power Fx compilation or designer acceptance.

Microsoft references: [Canvas source](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/power-apps-yaml), [Studio code view](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/code-view), [custom connector definition](https://learn.microsoft.com/en-us/connectors/custom-connectors/define-openapi-definition), [workflow schema](https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json). Source copies are retained locally.

Outstanding external acceptance: tenant/application registration and OAuth consent/roles; API HTTPS hosting and durable operational storage; approved recipient/mailbox permissions; Power Platform/custom connector/Power BI entitlements and DLP policy; Studio compilation, flow designer binding and actual delivery; semantic model binding, M/DAX execution, visuals, refresh/gateway and row-level security. No cloud, tenant, license purchase or production resource was changed.

Notification processing is at-least-once. A send accepted by Outlook followed by a lost acknowledgement can produce a retry; stable event IDs support reconciliation. SENT is the connector acknowledgement, not proof of human receipt. Terminal exception investigation and workflow-database backup/retention need an operational procedure. Multi-host SQLite and production load/security acceptance remain unverified.
