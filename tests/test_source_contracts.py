import json
from datetime import date

import httpx
import pytest

from maritime.sources import Fetcher, SourceError, ingest_portwatch
from maritime.store import Store


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-10-09", "2026-10-09"),
        ("2026-10-07T00:30:00+03:00", "2026-10-06"),
        ("2026-10-06T23:30:00-03:00", "2026-10-07"),
        ("2026-10-09T00:00:00Z", "2026-10-09"),
        (1791504000000, "2026-10-09"),
    ],
)
def test_observation_dates_are_parsed_completely_in_utc(value, expected):
    from maritime.sources import normalize_activity

    row = {
        "date": value,
        "portid": "test",
        "portcalls": 1,
        "_metadata": {"retrieved_at": "2026-10-17T00:00:00Z", "checksum": "test"},
    }
    assert normalize_activity([row])[0]["date"] == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-07garbage",
        "2026-02-30",
        "2026-10-07T01:00:00",
        None,
        True,
        float("nan"),
        float("inf"),
    ],
)
def test_malformed_observation_dates_fail_closed(value):
    from maritime.sources import normalize_activity

    with pytest.raises(SourceError, match="Invalid PortWatch observation date"):
        normalize_activity([{"date": value}])


def test_freshness_uses_each_ports_observation_not_retrieval(bundle, routes):
    import copy
    from datetime import timedelta

    from maritime.quality import validate

    as_of = date.fromisoformat(bundle["as_of"]) + timedelta(days=10)
    activity = copy.deepcopy(bundle["activity"])
    for row in activity:
        row["retrieved_at"] = as_of.isoformat() + "T12:00:00Z"
    _, boundary = validate(bundle["ports"], activity, routes, as_of, freshness_days=10)
    assert boundary["freshness_status"] == "PASS"
    # Each individual missing latest observation must fail, even if peers are fresh.
    for port in bundle["ports"]:
        stale = [
            r
            for r in activity
            if not (r["port_id"] == port["port_id"] and r["date"] == bundle["as_of"])
        ]
        _, result = validate(bundle["ports"], stale, routes, as_of, freshness_days=10)
        assert {e["port_id"] for e in result["errors"] if e["check"] == "freshness"} == {
            port["port_id"]
        }
    _, old = validate(
        bundle["ports"], activity, routes, as_of + timedelta(days=1), freshness_days=10
    )
    assert {e["port_id"] for e in old["errors"] if e["check"] == "freshness"} == {
        p["port_id"] for p in bundle["ports"]
    }


def test_pagination_and_arcgis_errors(tmp_path):
    def transport(request):
        offset = int(request.url.params["resultOffset"])
        return httpx.Response(
            200,
            json={
                "features": [{"attributes": {"portid": str(offset)}}],
                "exceededTransferLimit": offset == 0,
            },
        )

    fetch = Fetcher(tmp_path, httpx.Client(transport=httpx.MockTransport(transport)))
    source = {
        "source_id": "test",
        "source_url": "https://example.org",
        "required_fields": ["portid"],
    }
    assert len(fetch.arcgis(source, "1=1")) == 2
    bad = Fetcher(
        tmp_path,
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"error": {"code": 400}})
            )
        ),
    )
    with pytest.raises(SourceError, match="ArcGIS contract"):
        bad.arcgis(source, "1=1")


def test_incremental_replaces_revisions_and_deleted_rows(tmp_path):
    """Mock transport tests revision mechanics; this is not production observation evidence."""
    from maritime.pipeline import load_json

    registry = load_json("configs/sources.json")
    config = load_json("configs/pipeline.json")
    config["port_names"] = ["Test Port"]
    store = Store(tmp_path)
    requests = []
    meta = {"retrieved_at": "2026-10-07T00:00:00Z", "checksum": "test"}

    class Adapter:
        def arcgis(self, source, where):
            requests.append(where)
            if source["source_id"] == "portwatch_ports":
                return [
                    {
                        "portid": "test-port",
                        "portname": "Test Port",
                        "country": "Test",
                        "lat": 1,
                        "lon": 1,
                        "LOCODE": None,
                        "_metadata": meta,
                    }
                ]
            return [
                {"portid": "test-port", "date": "2026-10-06", "portcalls": 7, "_metadata": meta}
            ]

    _, activity, checkpoint = ingest_portwatch(
        Adapter(), registry, config, store, date(2026, 10, 7)
    )
    stale = {**activity[0], "date": "2026-10-05", "vessel_calls": 999}
    store.set_metadata(checkpoint[0], [stale, {**activity[0], "vessel_calls": 999}])
    _, revised, _ = ingest_portwatch(Adapter(), registry, config, store, date(2026, 10, 7))
    assert len(revised) == 1 and revised[0]["vessel_calls"] == 7
    assert "2026-09-22" in requests[-1]


def test_numeric_evidence_is_numeric(tmp_path):
    import numpy as np

    from maritime.pipeline import write_json

    path = tmp_path / "metrics.json"
    write_json(path, {"count": np.int64(3), "rate": np.float64(0.5), "ok": np.bool_(True)})
    assert json.loads(path.read_text()) == {"count": 3, "rate": 0.5, "ok": True}
