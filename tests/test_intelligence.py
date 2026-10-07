from datetime import date

import pytest

from maritime.intelligence import (
    alternate_paths,
    congestion,
    latest_states,
    network_state,
    propagate,
)
from maritime.quality import validate
from maritime.scenarios import evaluate, rank, shipments


def test_dq_rejects_corrupt_data(bundle, routes):
    good, report = validate(bundle["ports"], bundle["activity"], routes, date(2026, 10, 7))
    assert report["status"] == "PASS"
    bundle["ports"][0]["latitude"] = 91
    bundle["activity"].append(bundle["activity"][0])
    bundle["activity"][1]["classification"] = "FAKE"
    bundle["activity"][2]["vessel_calls"] = -1
    _, bad = validate(bundle["ports"], bundle["activity"], routes, date(2026, 10, 7))
    assert bad["status"] == "FAIL"
    assert bad["duplicate_rate"] > 0
    assert bad["referential_integrity_rate"] < 1
    assert bad["schema_status"] == "FAIL"


def test_no_future_leakage_and_proxy_persistence(bundle):
    history = congestion(bundle["activity"])
    state = next(s for s in latest_states(history) if s["port_id"] == "B")
    assert state["category"] in {"HIGH", "CRITICAL"}
    assert state["persistence_days"] == 5
    assert state["classification"] == "SIMULATED"
    earlier = [r for r in bundle["activity"] if r["date"] < "2026-10-07"]
    assert congestion(earlier) == [r for r in history if r["date"] < "2026-10-07"]


def test_network_closure_and_temporal_propagation(bundle, routes):
    states = latest_states(congestion(bundle["activity"]))
    graph, _ = network_state(bundle["ports"], routes, states, date(2026, 10, 7))
    assert len(alternate_paths(graph, "A", "B")) == 3
    assert all(e["depth"] == 0 for e in propagate(graph, states, horizon_hours=1))
    exposure = propagate(graph, states)
    assert all(e["arrival_hours"] <= 720 for e in exposure)
    assert all(len(e["path"]) == len(set(e["path"])) for e in exposure)
    closed, edges = network_state(
        bundle["ports"],
        routes,
        states,
        date(2026, 10, 7),
        [{"port_id": "B", "closed": True, "valid_from": "2026-10-06", "valid_to": "2026-10-08"}],
    )
    assert not alternate_paths(closed, "A", "B")
    assert any(not e["available"] for e in edges)


def test_scenarios_reproducible_and_counterfactuals(bundle, routes, config):
    graph, _ = network_state(
        bundle["ports"], routes, latest_states(congestion(bundle["activity"])), date(2026, 10, 7)
    )
    sample = shipments(graph, 10, 17, date(2026, 10, 7))
    assert sample == shipments(graph, 10, 17, date(2026, 10, 7))
    for shipment in sample:
        results = evaluate(graph, shipment, config["scenario_assumptions"], 17)
        assert results == evaluate(graph, shipment, config["scenario_assumptions"], 17)
        assert len(results) == 5
        by_action = {r["action"]: r for r in results}
        assert (
            by_action["EXPEDITE"]["breach_probability"]
            <= by_action["NO_ACTION"]["breach_probability"]
        )
        assert (
            by_action["PRIORITIZE"]["expected_delay_hours"]
            <= by_action["NO_ACTION"]["expected_delay_hours"]
        )
        assert rank(results)["expected_benefit"] >= 0
        assert all(r["classification"] == "SIMULATED" for r in results)
        for result in results:
            if result["feasible"]:
                assert 0 <= result["breach_probability"] <= 1
                assert result["delay_p10"] <= result["delay_p50"] <= result["delay_p90"]


def test_freshness_and_future_fail(bundle, routes):
    _, dq = validate(bundle["ports"], bundle["activity"], routes, date(2027, 1, 1))
    assert dq["freshness_status"] == "FAIL"
    bundle["activity"][0]["date"] = "2030-01-01"
    _, dq = validate(bundle["ports"], bundle["activity"], routes, date(2026, 10, 7))
    assert any(e["check"] == "future_observation" for e in dq["errors"])


def test_insufficient_history_blocks_network(bundle, routes):
    states = latest_states(congestion(bundle["activity"][:5]))
    with pytest.raises(ValueError, match="Insufficient"):
        network_state(bundle["ports"][:1], [], states, date(2026, 10, 7))
