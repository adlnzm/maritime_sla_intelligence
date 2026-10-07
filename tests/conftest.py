import json
from datetime import date, timedelta

import pytest

from maritime.intelligence import scenario_routes


@pytest.fixture
def bundle():
    """Entirely simulated algorithm fixture; never presented as real observations."""
    common = {
        "source_id": "test_fixture",
        "classification": "SIMULATED",
        "retrieved_at": "2026-10-07T00:00:00+00:00",
        "lineage_id": "test-fixture-v1",
    }
    ports = [
        {
            "port_id": p,
            "name": p,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "unlocode": None,
            **common,
        }
        for p, country, lat, lon in [
            ("A", "AA", 1, 100),
            ("B", "BB", 5, 110),
            ("C", "BB", 5.5, 110.5),
            ("D", "DD", 20, 120),
        ]
    ]
    as_of = date(2026, 10, 7)
    activity = []
    for p in ports:
        for i in range(90):
            calls = 40 + i % 7
            if i == 84:
                calls = 43  # Normal day immediately before the five-day disruption.
            if p["port_id"] == "B" and i >= 85:
                calls = 5
            activity.append(
                {
                    "port_id": p["port_id"],
                    "date": str(as_of - timedelta(days=89 - i)),
                    "vessel_calls": calls,
                    **common,
                }
            )
    return {"ports": ports, "activity": activity, "as_of": str(as_of)}


@pytest.fixture
def fixture_path(tmp_path, bundle):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


@pytest.fixture
def config():
    from maritime.pipeline import load_json

    return load_json("configs/pipeline.json")


@pytest.fixture
def routes(bundle, config):
    return scenario_routes(
        bundle["ports"], date.fromisoformat(bundle["as_of"]), config["scenario_assumptions"]
    )
