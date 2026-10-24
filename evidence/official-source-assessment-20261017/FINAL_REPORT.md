# Final freshness and source assessment — 17 October 2026

**LOCAL_RELEASE_READY = YES**
**PRODUCTION_READY = NO**

The original failure and the current success are separate: retained October 14 responses genuinely ended October 2 (age 12); fresh October 17 requests now end October 9 (age 8). The source advanced. No date was rewritten and all three configured freshness limits remain 10.

The narrow parser fix rejects malformed suffixes and ambiguous timestamps, and converts explicit timezone offsets to UTC before extracting the date. It fixes a reproduced acceptance/boundary defect, but did not cause PortWatch to publish newer data. Only `src/maritime/sources.py` and `tests/test_source_contracts.py` changed in application/test code for this workstream. Earlier dirty changes were preserved.

Detailed diagnosis: [FINDINGS](../freshness-diagnosis-20261017-131acd0c/FINDINGS.md), [raw-probe manifest](../freshness-diagnosis-20261017-131acd0c/diagnosis.json). Source strategy: [comparison and recommendation](ASSESSMENT.md), [port/government details](ports.md), [international sources](international.md).

| Port | ID | Current direct-source observation | Age on Oct 17 | Full campaign observation / age |
|---|---|---|---:|---|
| Rotterdam | port1114 | 2026-10-09 | 8 | 2026-10-09 / 8 |
| Shanghai | port1188 | 2026-10-09 | 8 | 2026-10-09 / 8 |
| Singapore | port1201 | 2026-10-09 | 8 | 2026-10-09 / 8 |
| Los Angeles-Long Beach | port664 | 2026-10-09 | 8 | 2026-10-09 / 8 |
| Jebel Ali | port744 | 2026-10-09 | 8 | 2026-10-09 / 8 |
| New York-New Jersey | port815 | 2026-10-09 | 8 | 2026-10-09 / 8 |

Focused verification: 31 passed, zero failures. Full suite: 63 tests, 0 failures, 0 errors, 0 skipped. One Starlette/httpx deprecation warning. Full campaign scope includes real Docker startup/auth/security/outage/restart/recovery, actual backup/restore, source and governance regression, publication concurrency, model contracts, lint/format/package build, dependency audit, Bicep and PBIR static validation, and live acquisition/replay/failure accounting.

Git revision `4b50f50769b08e763015064c53d91b6bda4ae079` with dirty working tree. New campaign `evidence\local-release-20261017-freshness-01` status `LOCAL_READY`. Independently verified 146 source hashes and 111 evidence hashes in both directory and ZIP. Command arrays/timestamps/exits are in `verification.json` and the campaign manifest.

| Campaign command | Exit code | Log |
|---|---:|---|
| git-diff | 0 | `evidence\local-release-20261017-freshness-01\git-diff.log` |
| clean-install | 0 | `evidence\local-release-20261017-freshness-01\clean-install.log` |
| tests | 0 | `evidence\local-release-20261017-freshness-01\tests.log` |
| package-consistency | 0 | `evidence\local-release-20261017-freshness-01\package-consistency.log` |
| lint | 0 | `evidence\local-release-20261017-freshness-01\lint.log` |
| format | 0 | `evidence\local-release-20261017-freshness-01\format.log` |
| build | 0 | `evidence\local-release-20261017-freshness-01\build.log` |
| powerbi | 0 | `evidence\local-release-20261017-freshness-01\powerbi.log` |
| fabric-assets | 0 | `evidence\local-release-20261017-freshness-01\fabric-assets.log` |
| bicep-version | 0 | `evidence\local-release-20261017-freshness-01\bicep-version.log` |
| bicep | 0 | `evidence\local-release-20261017-freshness-01\bicep.log` |
| dependency-export | 0 | `evidence\local-release-20261017-freshness-01\dependency-export.log` |
| dependency-audit | 0 | `evidence\local-release-20261017-freshness-01\dependency-audit.log` |
| docker | 0 | `evidence\local-release-20261017-freshness-01\docker.log` |
| live | 0 | `evidence\local-release-20261017-freshness-01\live.log` |

Read-only official-source capture scripts exited 0 after retaining per-request results; HTTP outcomes include usable 200 data, 200 empty records, 200 rejection HTML, 401, 403 and 429. A capture-script success is not a provider acceptance. Exact request URLs, timestamps and body hashes are in the separate access manifests. The original diagnostic helper failed once because it assumed numeric dates; it was corrected to inspect actual date-only values, then completed with exit 0.

No alternative provider was integrated. Retain PortWatch primary for the existing activity metric; propose a separate rights-reviewed LA operational corroboration pilot and approved Singapore/Rotterdam event-feed samples. Trade/tariff/throughput series belong in contextual tables, not fresh port-call or waiting-time fields. The exact previously recommended World Trade Center source remains ambiguous; WTCA GATRI was identified but is not assumed to be that recommendation.

Production remains blocked by actual cloud/workspace deployment, identity and effective permissions, provider reuse rights, Power BI rendering/refresh, approved retention/locking, named owners and alert routing, and production backup/failover/SLO evidence. Shipment-SLA ML remains deferred. No new image-generation services/dependencies were introduced.

Freshness is time-dependent: October 9 observations become eleven days old on October 20; absent newer data, the unchanged gate must block again. Full local acceptance does not establish sustained upstream timeliness, production deployment, or commercial shipment prediction accuracy.
