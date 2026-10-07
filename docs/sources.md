# Sources and classification

The machine-readable inventory is `configs/sources.json`; contracts are in `models.py` and adapter
required-field lists. Every HTTP response is retained with SHA-256, URL, timestamp, status,
latency, retries and available ETag. A public response is evidence of what the publisher reported,
not a claim that the publisher's estimates are direct onboard measurements.

| Source | Adapter | Role / classification |
|---|---|---|
| [IMF PortWatch](https://portwatch.imf.org/) | ArcGIS REST pagination | Port references and reported daily calls, OBSERVED |
| [NGA WPI](https://msi.nga.mil/Publications/WPI) | configurable official CSV download | Port reference and reconciliation, OBSERVED |
| [UNECE UN/LOCODE](https://unlocode.unece.org/publications/) | configurable release ZIP | Location code reconciliation, OBSERVED |
| Public route provider | configurable GeoJSON | Source geometry with explicit provenance; DERIVED reference routes |
| [Open-Meteo archive](https://open-meteo.com/en/docs/historical-weather-api) | JSON daily wind reanalysis | DERIVED; reanalysis combines observations and models |

IMF item IDs: port database `acc668d199d1472abaaf2467133d4ca4`, daily activity
`83b1bbc7b3354c5fb1f40673bb8f852e`. Source URLs are configurable rather than scattered constants.
PortWatch combines some port complexes: “Los Angeles-Long Beach”, “New York-New Jersey”. Missing
configured ports fail ingestion; there is no fuzzy-name guessing in the pipeline.

Official download locations and formats can change. Set WPI/UNLOCODE `download_url` to the
publisher's current release; preserve a dataset version in the registry. The WPI adapter expects
official named CSV fields; UN/LOCODE expects its 12-column release CSV layout inside ZIP.
Invalid formats fail the optional adapter and are reported. No optional reference is claimed
validated merely because an adapter exists. WPI coordinate matching is reference evidence;
UN/LOCODE code presence is the implemented critical cross-source reconciliation when configured.

Five classifications are preserved:

- OBSERVED: received directly from a real publisher (with publisher estimation caveats).
- DERIVED: deterministic transformation or explicitly identified reference reanalysis.
- ANTICIPATED: grounded but unconfirmed external disruption signal.
- SIMULATED: invented operational scenario, assumed topology, or modeled intervention outcome.
- PREDICTED: trained statistical forecast with a model version.

Attribution and source terms remain applicable. The free Open-Meteo endpoint is intended for
non-commercial use; configure licensed access for commercial workloads as required by its terms.
UNECE publishes under CC BY 4.0. Review IMF and NGA distribution conditions before redistributing
large archives or combining with commercial data. A retained sample does not imply live freshness.
