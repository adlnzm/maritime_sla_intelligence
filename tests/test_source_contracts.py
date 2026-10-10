import json
from datetime import date

import httpx
import pytest

from maritime.sources import Fetcher, SourceError, ingest_portwatch
from maritime.store import Store


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
