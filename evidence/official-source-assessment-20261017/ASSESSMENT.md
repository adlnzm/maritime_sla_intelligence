# Source strategy assessment — 17 October 2026

## Decision

Keep **IMF PortWatch as PRIMARY_OPERATIONAL for the existing daily activity metric**, subject to its unchanged independent ten-day check for every required port. Actual source probes now show October 9 for all six ports, age eight days on October 17. The previous October 14 failure remains valid: its captured source data stopped on October 2. The new availability is an upstream advance, not an alternative-provider substitution or a relaxed gate.

No researched alternative demonstrated a fresh, equivalent daily port-call feed across all six configured port entities. Do not integrate or replace providers in this pass. Separate detailed [port/government findings](ports.md), [international findings](international.md), and [PortWatch root-cause findings](../freshness-diagnosis-20261017-131acd0c/FINDINGS.md) contain exact endpoints, source/retrieval dates, access results, fields and limitations.

| Source | Geographic/metric fit | Actual availability evidence | Classification |
|---|---|---|---|
| [IMF Daily Ports Data](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query) | All six; daily AIS-derived activity/calls, estimated tonnage; no measured vessel waiting | Six independent latest-row queries: Oct 9; six fresh-window counts: 3 each; HTTP 200 | PRIMARY_OPERATIONAL, conditional on gate |
| [MPA Singapore monthly arrivals](https://data.gov.sg/datasets/d_d48c5a038904f6da3c603cd854b6c191/view) | Singapore only; monthly arrivals for vessels over 75 GT | Actual public API latest row August 2026, 11,631 arrivals; HTTP 200 | CONTEXTUAL_ENRICHMENT |
| [Singapore MPA OCEANS-X](https://oceans-x.mpa.gov.sg/) | Actual/expected arrival/departure products advertised; Singapore only | Catalogue accessible; no authorized operational records retrieved | UNVERIFIED |
| [Rotterdam API products](https://portal.api.portofrotterdam.com/get-started) | Candidate actual port-call events; Rotterdam only | Approved guest/product subscription key required; newest observation unverified | UNVERIFIED |
| [Rotterdam throughput](https://www.portofrotterdam.com/en/pressroom/throughput-figures) / [China MOT statistics](https://www.mot.gov.cn/shuju/) | Rotterdam cargo totals / national and Shanghai-context throughput | H1 2026 Rotterdam release; Jan–Aug 2026 China catalogue, Shanghai row not independently inspected | CONTEXTUAL_ENRICHMENT |
| [Shanghai TIP](https://wlgs.portshanghai.com.cn/khfw/index.jhtml) | Candidate berth/tally events, Shanghai only | Documentation found; no live records; related facts page 403 | UNVERIFIED |
| [Port of LA operations](https://portoflosangeles.org/business/operations) | LA berth/container indicators and explicitly scoped LA/LB regional counts | Actual reports Oct 15 operations, Oct 16 08:04 import-container dwell; PDF captures HTTP 200 | SECONDARY_VALIDATION candidate, distinct metric/geography |
| [NY/NJ dashboard](https://cloud.email.panynj.gov/newsletter) | Weekly port operational context; NY/NJ only | Signup page 200; no latest issue acquired or signup performed | UNVERIFIED |
| [Dubai Trade vessel information](https://dpwdtjb2.dubaitrade.ae/pmisc1/vessel.do) | Jebel Ali candidate movements/schedules | HTTP 200 body is Request Rejected; no actual event obtained | UNVERIFIED |
| [US BTS port performance](https://www.bts.gov/ports) | Historical US port throughput/performance | Annual report, not a current daily feed | HISTORICAL_ONLY |
| [WTO statistics](https://apiportal.wto.org/) and [tariff data](https://www.wto.org/ENGLISH/tratop_e/tariffs_e/tariff_data_e.htm) | National economy/product trade and tariff context; no six-port events | Timeseries API 401 without subscription key; newest data row unverified | CONTEXTUAL_ENRICHMENT |
| [UN Comtrade](https://comtradeplus.un.org/) | National commodity trade, quantities/values/periods, not port events | Singapore annual 2025 record 200/count 1; August 2026 query 200/count 0; 429 captured before successful bounded retry | CONTEXTUAL_ENRICHMENT |
| [WTCA/HCSS GATRI](https://www.wtca.org/blog_posts/2nd-edition-of-the-geopolitical-annual-trade-risk-index-gatri) | Annual geopolitical risk context; not maritime observations | Actual WTCA-related organization/tool identified; row/API/licence unverified | UNVERIFIED |

“World Trade Center” is ambiguous. No exact previous recommendation was identifiable in the repository. WTCA, WTO and the International Trade Centre are distinct; the discovered GATRI tool is **not assumed to be the recommendation**. Obtain the original URL before evaluating that intended dataset further.

## Recommended architecture and reviewable next step

1. Preserve the current activity series, stable port IDs, original event dates, source lineage and per-port freshness gate. Monitor observation lag separately from HTTP uptime. A successful download does not clear stale data.
2. Qualify LA authority reports as a separate corroboration dataset first, after rights review. Preserve the distinction between container dwell, berth count, regional vessel count and port-call activity. Do not use it to fill PortWatch dates, or claim complete combined LA/LB coverage.
3. Seek approved Singapore/Rotterdam actual-event API samples and schemas. Require observed-vs-expected event flags, timezone, vessel/geofence/category scope, revision behaviour, and a demonstrated current history before proposing an adapter. Shanghai, NY/NJ and Jebel Ali remain access/schema/rights work.
4. Keep WTO, Comtrade, government monthly throughput and geopolitical context in separate tables with period start/end, release/revision time, estimates/quality flags and source-specific contracts. National data cannot be joined as if it were a measured port outcome.
5. Any proposed adapter is a separate review: minimal real sample; explicit licence/attribution/redistribution review; ID and metric mapping; independent freshness contract appropriate to the metric; content hashes and retained failures; tests for missing/stale/future timestamps, timezone boundaries, revisions, 429/auth failures, and HTML errors returned with status 200. For PDF reports, add layout/version and missing-timezone tests. Integrate only after these checks pass.

Operational signals must retain native semantics. Estimated tonnage/indices are identified as estimates; computed stress remains DERIVED; expected movements remain ANTICIPATED; synthetic shipment scenarios remain SIMULATED; forecasts remain PREDICTED. None of the researched data supplies representative observed commercial shipment-SLA labels, so that ML work remains deferred.

## Access and rights

Public PortWatch calls required no key; its 1,000-row page size is not a rate entitlement. The IMF item links IMF terms; redistribution permission was not established by the accessible API. Singapore's public monthly dataset uses the Singapore Open Data Licence with attribution/exclusions; that does not authorize reuse of authenticated MPA products. Rotterdam needs approved product credentials; WTO needs a subscription key. Comtrade supports public preview but returned a real 429; registered quotas and licence terms must govern production use. Other rate allowances and commercial redistribution permissions remain unknown unless explicitly documented in the detailed assessments. No credentials were added, signups made, or large bulk datasets downloaded.

## Evidence and acceptance boundary

`port-access-results.json`, `la-report-access.json`, `singapore-data-access.json` and `international-access.json` retain individual request URLs, acquisition times, HTTP statuses and hashes. Small raw response bodies and two LA PDFs are preserved. Script exit 0 means the capture completed, not that each source passed; failed/inaccessible responses are not usable data. `../freshness-diagnosis-20261017-131acd0c/diagnosis.json` retains the independent PortWatch probes.

This assessment is research and proof-of-access only. It makes no production deployment or alternative-provider integration claim. The final local-release conclusion must come from the new complete campaign `../local-release-20261017-freshness-01/result.json` and verified evidence manifest, not from this comparison table.
