# Portfolio release audit — 18 October 2026

**Credible portfolio candidate, but public release is not approved.** Recommend a curated source/documentation review package, not publishing this working directory, its complete Git history, evidence ZIPs or Docker image as-is. Every classification below is an assessment, not permission to publish. No existing file was changed or removed; no provider integrated, cloud service deployed or publication performed.

Baseline: branch `codex/build-maritime-platform`, revision `4b50f50769b08e763015064c53d91b6bda4ae079`, dirty working tree. The six reachable commits include retained raw source data and a tracked evidence ZIP. Ignoring files now would not remove them from published history. `git-status-before.txt`, `ignored-before.txt` and the final manifest record this review's boundaries. No reset, clean, commit, branch change or push occurred.

## Freshness, independently checked today

Retained canonical activity files examined in `retained-activity-dates.json` stop at October 2 except the October 17 campaign, which reaches October 9. No newer retained canonical observation was found in those inspected paths. This is not an exhaustive semantic examination of every database or binary archive.

Six read-only official ArcGIS queries were executed, each asking for one row ordered by source date descending, with a 20-second timeout, a 64-KiB response ceiling, one-second spacing and no retries. HTTP 200 alone was insufficient: each body had to contain the requested port and a valid source date. `freshness.json` retains exact URLs, UTC retrieval times, ages and raw hashes. `latest-port*.json` retains the responses. The source's transfer-limit flag is expected for a top-one query and is not treated as complete-history evidence.

| Port | Latest source observation returned | Age on 2026-10-18 | Independent 10-day rule |
|---|---|---:|---|
| Singapore | 2026-10-09 | 9 days | PASS |
| Rotterdam | 2026-10-09 | 9 days | PASS |
| Shanghai | 2026-10-09 | 9 days | PASS |
| Los Angeles–Long Beach | 2026-10-09 | 9 days | PASS |
| New York–New Jersey | 2026-10-09 | 9 days | PASS |
| Jebel Ali | 2026-10-09 | 9 days | PASS |

Requests began between 05:35:19 and 05:35:29 UTC on October 18 (08:35:19–08:35:29 Qatar). These acquisition timestamps are separate from observation dates. The source returned no newer date than yesterday's retained evidence. Absent newer observations, age becomes 11 on October 20 and the gate must fail. No application ingestion/publication was run; this is a latest-observation check, not a new full acceptance campaign or proof that local cached products are fresh. Older local October 2 datasets are 16 days old today and cannot be presented as current live outputs.

## Proposed public artifact decisions

Primary classifications identify the first blocking review; rows can have additional security, rights or claim requirements. The smallest candidate allowlist is explicit below. Unlisted content is NOT_ASSESSED and excluded from that proposal.

| Proposed artifact | Classification | Supporting evidence / issue | Owner decision and minimum action |
|---|---|---|---|
| First-party `src/`, test code excluding `tests/data/`, `scripts/`, `sql/` | APPROVED_FOR_REVIEW | Engineering implementation and October 17 source-bound tests; heuristic findings in `artifact-screening.json` still require adjudication | Review exact allowlist and test constants; establish ownership and chosen code licence. This is not a secret-free signoff |
| `pyproject.toml`, `uv.lock`, `.gitignore`, `.gitattributes`, `.amlignore`, `.dockerignore`, blank `.env.example` | APPROVED_FOR_REVIEW | Config inspection: example credentials blank, dependency lock retained; these are not actual credentials | Review package notices and licence requirements, publish templates only; inspect final staged artifact |
| First-party configs excluding vendored schemas; Azure/Fabric templates, notebook source and CI definitions | APPROVED_FOR_REVIEW | Implemented deployment targets; no target execution established | Label cloud components unverified, review placeholders and notebook outputs; no environment-specific deployment files |
| `configs/powerbi_schemas/` and other vendored/generated third-party material | BLOCKED_RIGHTS_REVIEW | Official schemas were downloaded; their redistribution/notice treatment not fully established by this review | Confirm applicable notices/rights or distribute source links/acquisition instructions; preserve local files |
| README and public evidence index | BLOCKED_CLAIM_VERIFICATION | `evidence/README.md` calls older `ready-to-run` campaign current; `docs/testing/verification_report.md` is Oct 10 / 39 tests. README says production uses Entra and introduces production layers in present tense | Prepare a separately reviewed publication copy identifying the Oct 17 dirty-tree campaign/63 tests and clearly labelling cloud behavior as implemented target, unverified live. Keep old reports dated/history intact |
| Dockerfile / Compose demo as a downloadable runnable bundle | BLOCKED_RIGHTS_REVIEW | `docker/Dockerfile:8` copies `tests/data` into `/app/samples`; `compose.demo.yml` seeds the real retained fixture | Resolve sample rights first, then review actual build context/image contents. Source-only build files may be reviewed, but do not advertise an approved self-contained demo without its authorized fixture |
| `tests/data/portwatch_sample.json` | BLOCKED_RIGHTS_REVIEW | Contains OBSERVED PortWatch records and original retrieval/lineage; not wholly synthetic | Confirm retained-source redistribution/attribution or design a separate explicitly synthetic fixture in a future scoped change; do not relabel real rows as synthetic |
| `evidence/governance-final/bronze`, `governance-release/bronze`, campaign datasets and raw captures | BLOCKED_RIGHTS_REVIEW | Actual IMF/weather records, metadata and derived copies are present, some tracked | Data owner reviews each provider and exact public data scope; exclude from proposed public package pending rights |
| `evidence/official-source-assessment-20261017/*.response`, response JSON/text and LA PDFs | BLOCKED_RIGHTS_REVIEW | Raw Comtrade record, source HTML and port-authority attachments are research captures, not licensed public redistribution bundles | Prefer official links and a reviewed factual summary; obtain applicable permission before distributing attachments |
| Evidence ZIPs, including tracked `evidence/governance-evidence.zip`, newer release ZIPs and full evidence folders | BLOCKED_SECURITY_REVIEW | Archives include datasets/logs; bounded nested text inspection is not full binary/privacy review; rights also unresolved | Publish only a reviewed sanitized summary, not archive-as-is. Inspect each member, signatures/metadata, rights and identifiers before any future packaging |
| Raw test logs/XML, Git inventories/diffs and full assessment evidence | BLOCKED_SECURITY_REVIEW | Local user paths, host metadata and Git author/committer email categories found by screen; requests/scripts can include configured URLs | Owner approves intentional identity disclosure; create sanitized copies separately. Do not expose exact metadata merely because logs passed |
| Complete reachable Git history | BLOCKED_SECURITY_REVIEW | Six commits; author/committer metadata and historical raw/ZIP artifacts. A current-tree-only scan cannot clear history | Choose a fresh curated export for review rather than pushing existing history; if history is required, review every reachable artifact and identity. No rewriting authorized/performed |
| Ignored `data/`, databases/WAL, models, staging dirs, local tools/environments, `dist/` and build outputs | NOT_ASSESSED | Bounded text/inventory scan does not establish binary contents, model safety, DB privacy or package rights | Exclude from public candidate; review specifically only if needed. `.gitignore` is not an export security boundary |
| Generated `fabric/powerbi/Maritime.Report/`, report screenshots or dashboard demo claims | BLOCKED_CLAIM_VERIFICATION | Oct 17 PBIR log is schema-only: 29 files/five pages, no actual semantic-model binding/rendering | Describe generated assets only; capture authorized rendering, filters, model and refresh before claiming a working Power BI dashboard |
| Curated narrative of architecture, controls, limitations and dated test counts, with provider links | APPROVED_FOR_REVIEW | `CLAIM_EVIDENCE_MATRIX.md` provides bounded wording and references | Review prose/attribution and redact environment metadata; publish only after owner approval of exact content |

## Rights and security interpretation

Official sources checked on **2026-10-18**: [IMF terms](https://www.imf.org/external/terms.htm) returned 403 in the research tool, so no new clearance was established. [UN Comtrade redistribution guidance](https://uncomtrade.org/docs/re-dissemination-of-data/) retains limited-use exceptions and application/subscription ambiguity documented in the prior licensing draft; it does not prohibit all commercial use, and no reply or permission has been received here.

[Open-Meteo terms](https://open-meteo.com/en/terms) distinguish CC-BY data licensing from free-service access restricted to noncommercial use; promotional activity is listed among commercial examples. A portfolio is not automatically qualified for the free live service merely because it charges no fee. Review the actual proposed use; offline attribution and live API entitlement are separate questions. No paid account or terms acceptance was performed.

No root first-party LICENSE file was found. That is an owner licensing decision, not proof of infringement; a public repository should state intended reuse rights and separately preserve third-party notices. Existing UN/LOCODE/NGA/reference/schema permissions must not be inferred from other providers' terms.

The scanner records paths, categories, first matching line and count only, never candidate values. It covers working files including much ignored project data, reachable history blobs and bounded ZIP/WHL members. It skips specified environments/caches, binary decoding, over-limit files and encrypted members; nested archives are not recursively decoded. See `artifact-screening.json` for exact counts and omissions. Pattern screening cannot prove absence of credentials or private information. Candidate strings are not automatically active secrets; test values, public support addresses and placeholders need context. Do not print candidates or authenticate with them. Confirmed real credentials would require owner-controlled revocation/rotation and a separate publication plan.

## Sanitized screening results

Completed screen: **1,786 inventoried working files, 262 reachable historical blobs across six commits, 124 path/category findings and 56 recorded content omissions**. Findings comprise 114 local identity-metadata entries, six email-review entries, three credential-assignment entries and one signed/credential-URL review entry. These are path/category counts, not distinct secrets or people.

- `.env.example` and historical blobs `a8ad136e34a0a33c24fb91fc96b18c682fa59ade` / `75f9e6dee44e83bffdbef04a90e984b4c46a0750`: matched assignment patterns, but inspected sensitive assignments were blank. The heuristic crossed line whitespace; these findings do not establish exposed credentials.
- `tests/test_production_controls.py:232`: URL-pattern hit in a monkeypatched configuration test followed by an expected ValueError; retain as test-context review, not a confirmed live secret. No token value is reproduced here.
- `evidence/local-release-20261017-freshness-01/tests.xml`, `tests.log`, portable ZIP members and other logs include local host/user-path metadata. Git author/committer metadata contains email information. Owner approval or sanitized public copies are needed; identities are not printed here.
- Email findings in licensing documents include official provider contacts; those are distinct from personal Git metadata. Classify by context, not blanket deletion.
- No provider-token, private-key, JWT or private-network pattern hit was recorded. This is limited-pattern negative evidence, not a guarantee. Omitted DB/model/tar.gz/PDF/tool bodies and size-limited content remain NOT_ASSESSED for full sensitive-content review.

The first scanner invocation used slow per-object Git subprocesses and was interrupted (tool exit 1, no completed result). A separate invocation used batched Git object reads and completed with exit 0; its original logs were preserved. Freshness checker exit 0 confirms six valid recent-date responses only. No full test suite was run. Final manifest checks validate source binding and documentary hashes, not public redistribution permission.

## Smallest coherent demonstration

Present a source-led engineering case study: source contracts and lineage, fail-closed publication, replay/idempotency, same-run decision/audit consistency, local authenticated API, failure recovery and backup integrity. Show dated, sanitized evidence excerpts rather than complete raw archives. Describe maritime activity deviation as a DERIVED stress proxy, shipment/SLA interventions as SIMULATED scenarios, and forecasts as PREDICTED port-call research outputs. Do not claim measured waiting time, observed commercial SLA outcomes, production ML or executed cloud integration.

A locally runnable historical replay is a second step after fixture rights/security review. Until then, a coherent public architecture/code-review presentation is possible without exposing a live endpoint or redistributing records. Do not weaken freshness, replace dates or hide stale inputs for a more attractive demo. No new images are needed.

Existing Oct 17 local acceptance remains historical evidence for the matching source. Today's check verifies only six latest dates and artifact-review assertions. Public publication and production acceptance remain unapproved. A production service additionally needs the target/owner/identity/retention/monitoring/recovery/Power BI gates in `../licensing-readiness-20261017-162403/PRODUCTION_READINESS_GAPS.md`; these are not prerequisites for a carefully labelled static portfolio case study.
