# Canonical Hamad Port coverage

Read-only public-source queries on **2026-10-22** confirmed **Hamad Port**, Qatar, ISO3 **QAT**, canonical PortWatch **port2026**, source LOCODE **QA HMD** (normalized **QAHMD**), latitude 25.0199084210527, longitude 51.6189139089543. Hamada in Japan, Ras Laffan, AlRuwais and Doha-Umm Said were excluded; no similarly named record was substituted.

The reference query searched Qatar, Hamad, Doha and QAHMD. Daily activity was queried by the exact confirmed `portid = 'port2026'`. The source reported **2,846 observations**, from **2019-01-01 through 2026-10-16**. The latest observation was **six days old** on verification, within the unchanged ten-day freshness threshold. The latest daily sample includes a reported zero on October 16; it was not filled or fabricated.

Raw responses: `hamad-reference.json`, `hamad-activity-range.json`, `hamad-activity-latest.json`. `canonical-queries.json` records full query URLs/parameters, retrieval UTC and SHA-256. The count/range are source statistics; only the latest 14 observations were retained for the daily fixture, not a complete download of 2,846 rows. The freshness statement is dated and is not a guarantee of future source freshness or a new product run.

`configs/pipeline.json` includes Hamad Port with `port_ids.Hamad Port = port2026`. `ingest_portwatch` rejects a conflicting canonical ID. `normalize_ports` normalizes spaces in LOCODE while preserving raw Bronze input. `configs/workflow.json` selects `focus_port_id=port2026`. The Hamad reporting view uses this configuration; other ports remain available in the portfolio.

`test_canonical_hamad_reference_activity_and_id_pin` joins the retained genuine reference and activity samples, checks the date/ID/LOCODE contract, runs ingestion against an isolated adapter boundary, and rejects an incorrect canonical ID. Synthetic weekly fixtures exercise full baseline/risk/workflow behavior separately; they are never represented as observed Hamad risk or shipment labels. No unrestricted acquisition pipeline was executed.

Sources: [PortWatch reference service](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) and [daily activity service](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0).
