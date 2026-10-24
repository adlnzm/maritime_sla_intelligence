# PortWatch freshness investigation — 17 October 2026

## Confirmed cause and current availability

The 14 October freshness failure was supported by the source responses: all six required ports' raw `date` values ended on **2026-10-02**. Raw response SHA-256 checks passed; independently normalizing the 1,374 activity rows reproduced the report and persisted SQLite data-quality dates exactly. Age was `(2026-10-14 - 2026-10-02).days = 12`, exceeding the unchanged **10** day limit. There was no checkpoint or published-run pointer in the disposable failed run database.

The current service has advanced. Independent requests on **17 October** returned **2026-10-09 for every port**, age **8 days**; each port also had three rows in the inclusive 7–17 October freshness window. These probes used a new HTTP client with `Cache-Control: no-cache`, not the application's cache, and no lower/upper date filter on the descending latest-row query. All 14 metadata/item/latest/count requests returned HTTP 200. Raw bodies, exact query URLs, retrieval times, response headers and SHA-256 are in `diagnosis.json` and adjacent files.

This is upstream availability recovery, not a code correction that made old dates fresh. The old captured queries prove the service returned old observations; they cannot establish whether internal publisher processing or upstream caching caused the publication lag. No evidence supports a wrong endpoint, missed pagination page, local cache reuse or erroneous normalization of the actual date-only responses.

## Per-port evidence

Source observations are daily dates, not intraday event timestamps. Do not invent a time-of-day for them.

| Port | ID | Raw date in 14 Oct capture | Age on 14 Oct | Latest raw date in 17 Oct probe | Age on 17 Oct | Rows in fresh window |
|---|---|---|---:|---|---:|---:|
| Singapore | port1201 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |
| Rotterdam | port1114 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |
| Shanghai | port1188 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |
| Los Angeles–Long Beach | port664 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |
| New York–New Jersey | port815 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |
| Jebel Ali | port744 | 2026-10-02 | 12 | 2026-10-09 | 8 | 3 |

Original latest rows for Rotterdam, Shanghai, NY/NJ and Jebel Ali were retrieved at `2026-10-14T04:05:14.274318+00:00`; Singapore and LA/LB at `2026-10-14T04:05:19.181159+00:00`. Exact current retrieval timestamps are recorded per request in `diagnosis.json`; all are 17 October. Retrieval time never participates in observation age.

## Acquisition-to-gate trace

1. `configs/pipeline.json` names all six ports; `ingest_portwatch` queries the [IMF port reference layer](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0), verifies all configured names are returned, then uses their stable IDs.
2. Activity comes from [Daily_Ports_Data layer 0](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query). Its item `83b1bbc7b3354c5fb1f40673bb8f852e` is owned by `IMF-portwatch_imf_dataviz` and points to this service. Current layer metadata declares `date` as `esriFieldTypeDateOnly`/SQL date, UTC time reference, 1,000-record page size and pagination support.
3. Original query selected the six IDs, `date >= DATE '2026-02-16' AND date <= DATE '2026-10-14'`. It therefore did not exclude the required fresh dates. Count query returned 1,374; pages ordered by ObjectId returned 1,000 at offset 0 and 374 at offset 1,000. Their combined count matched exactly. Returned day maxima, not ObjectId ordering, determine freshness.
4. `Fetcher.get` always requests HTTP data and stores exact bytes under content-addressed Bronze filenames. Existing identical files are verified for mutation; they are not used as cached HTTP responses. `normalize_activity` preserves observation date separately from retrieval timestamp and raw checksum lineage.
5. A checkpoint can retain only earlier history outside the re-read revision window; the queried window is replaced, and checkpoint advancement occurs only after DQ passes. The original campaign used a unique new data directory and has no persisted checkpoint.
6. `quality.validate` schema-validates rows, rejects future dates, computes the maximum observation date independently for every canonical port, and fails missing dates or age greater than 10. It also checks continuous history and consistent latest days. Pipeline persists the DQ product and quarantine dispositions, then aborts before Silver/checkpoint/publication on failure. Raw maxima equal the persisted `latest_by_port` values in the failed SQLite database and report.

## Separate parser defect and narrowly scoped fix

Before editing, direct reproduction showed `2026-10-07garbage` accepted as `2026-10-07`, and `2026-10-07T00:30:00+03:00` incorrectly retained as October 7 instead of UTC October 6. This was caused by slicing the first ten characters. It could incorrectly cross a freshness boundary, but **did not cause the original failure**, whose source values were valid date-only strings.

Only application changes for this investigation:

- `src/maritime/sources.py`: validate complete ISO calendar dates; convert explicitly zoned timestamps to UTC before taking the date; retain epoch-millisecond support; fail closed on malformed, timezone-naive timestamp, boolean, null and nonfinite values. No retrieval-time substitution or threshold change.
- `tests/test_source_contracts.py`: 13 additional cases covering valid daily/epoch/offset dates, malformed input, exactly-ten-day acceptance, eleven-day rejection, and individual stale ports despite current retrieval times.

The diagnostic helper `evidence/diagnose_portwatch_freshness.py` and evidence/research files are supporting artifacts. No provider integrated, source registry changed, reset/clean/commit performed, or existing evidence overwritten.

## Commands and verification

| Command | Result |
|---|---|
| Initial diagnostic helper (14 Oct attempt) | Exit 1: helper assumed epoch values; actual raw dates were strings. No source requests reached. Helper corrected; no application data changed. |
| `python evidence/diagnose_portwatch_freshness.py` (17 Oct) | Exit 0; retained raw/hash/SQLite comparisons and 14 actual public HTTP 200 probes; all-six freshness PASS for 17 Oct. |
| `python -m ruff format src/maritime/sources.py tests/test_source_contracts.py` | Exit 0 |
| `python -m ruff check src/maritime/sources.py tests/test_source_contracts.py` | Exit 0 |
| `python -m pytest tests/test_source_contracts.py tests/test_governance.py tests/test_startup.py -q --junitxml=evidence/freshness-diagnosis-20261017-131acd0c/focused-tests.xml` | Exit 0; **31 passed**, zero failures; one Starlette/httpx deprecation warning. See focused-tests.log/XML. |
| `python scripts/production_release.py --output evidence/local-release-20261017-freshness-01 --live` | New complete campaign; inspect its final result/manifest and the companion final report for outcome, not this diagnosis alone. |

All Python commands used `.venv/Scripts/python.exe` with `PYTHONPATH=src` and `PYTHONUTF8=1`; the release runner records its own clean-environment commands. Docker startup was requested because the Linux engine was stopped. Source freshness is time-dependent: October 9 observations qualify on October 17 but will fail once older than ten days unless the publisher advances. The previous failed campaign remains failed. No production claim follows from fresh source observations or from the alternative-source research.
