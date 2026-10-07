"""Seeded Monte Carlo counterfactuals use shared draws for paired comparisons."""

from datetime import datetime, timedelta, timezone

import numpy as np

from maritime.intelligence import alternate_paths, nautical_distance, path_hours
from maritime.models import stable_id

ACTIONS = ("NO_ACTION", "REROUTE", "ALTERNATE_PORT", "EXPEDITE", "PRIORITIZE")


def shipments(graph, count, seed, as_of):
    rng = np.random.default_rng(seed)
    nodes = sorted(graph.nodes)
    if len(nodes) < 2:
        raise ValueError("At least two connected ports required")
    result = []
    for i in range(count):
        origin, destination = map(str, rng.choice(nodes, 2, replace=False))
        paths = alternate_paths(graph, origin, destination, 1)
        if not paths:
            raise ValueError(f"No feasible route for {origin} -> {destination}")
        planned = path_hours(graph, paths[0])
        buffer = float(rng.uniform(6, 48))
        start = datetime.combine(as_of, datetime.min.time(), timezone.utc)
        result.append(
            {
                "shipment_id": stable_id(seed, as_of, i),
                "origin": origin,
                "destination": destination,
                "route": paths[0],
                "planned_transit_hours": planned,
                "planned_delivery": (start + timedelta(hours=planned)).isoformat(),
                "promised_delivery": (start + timedelta(hours=planned + buffer)).isoformat(),
                "sla_buffer_hours": buffer,
                "priority": int(rng.integers(1, 4)),
                "cargo_value": float(rng.uniform(10000, 250000)),
                "current_state": "PLANNED",
                "classification": "SIMULATED",
                "source_id": "synthetic_shipments_v1",
                "lineage_id": stable_id(seed, sorted(graph.edges), as_of),
                "seed": seed,
            }
        )
    return result


def evaluate(graph, shipment, assumptions, seed, draws=512):
    if draws < 32:
        raise ValueError("At least 32 draws required")
    rng = np.random.default_rng(int(stable_id(seed, shipment["shipment_id"]), 16))
    sigma = assumptions["delay_sigma"]
    noise = rng.lognormal(-(sigma**2) / 2, sigma, draws)
    base_path = shipment["route"]
    options = alternate_paths(graph, shipment["origin"], shipment["destination"], 5)
    reroutes = [p for p in options if p != base_path]
    route = (
        min(
            reroutes,
            key=lambda p: (
                path_hours(graph, p)
                + sum(graph.nodes[n]["stress_score"] for n in p) * assumptions["stress_delay_hours"]
            ),
        )
        if reroutes
        else None
    )
    destination = graph.nodes[shipment["destination"]]
    alternates = []
    for node in sorted(graph.nodes):
        if node in {shipment["origin"], shipment["destination"]}:
            continue
        # Alternate discharge must be in the destination country and within 300 nm.
        candidate = graph.nodes[node]
        if (
            candidate["country"] == destination["country"]
            and nautical_distance(candidate, destination) <= 300
        ):
            candidate_paths = alternate_paths(graph, shipment["origin"], node, 1)
            alternates.extend(candidate_paths)
    alternate = min(alternates, key=lambda p: path_hours(graph, p)) if alternates else None
    results = []
    for action in ACTIONS:
        path = (
            route if action == "REROUTE" else alternate if action == "ALTERNATE_PORT" else base_path
        )
        feasible = path is not None and all(graph.has_edge(a, b) for a, b in zip(path, path[1:]))
        scenario_id = stable_id(shipment["shipment_id"], action, seed, "cf-v1")
        common = {
            "scenario_id": scenario_id,
            "shipment_id": shipment["shipment_id"],
            "action": action,
            "feasible": feasible,
            "classification": "SIMULATED",
            "lineage_id": shipment["lineage_id"],
            "methodology": "paired lognormal simulation v1",
            "assumptions": assumptions,
            "draws": draws,
            "route": path,
        }
        if not feasible:
            results.append({**common, "reason": "No feasible alternative in current network"})
            continue
        transit = path_hours(graph, path)
        stress_delay = (
            sum(graph.nodes[n]["stress_score"] for n in path) * assumptions["stress_delay_hours"]
        )
        cost = 0.0
        if action == "EXPEDITE":
            transit *= 0.85
            cost = assumptions["expedite_cost"]
        elif action == "PRIORITIZE":
            stress_delay *= 0.7
            cost = assumptions["prioritize_cost"] * shipment["priority"]
        elif action == "REROUTE":
            cost = assumptions["reroute_cost"]
        elif action == "ALTERNATE_PORT":
            cost = assumptions["alternate_port_cost"]
            transit += assumptions["alternate_last_mile_hours"]
        delay = np.maximum(0, transit + stress_delay * noise - shipment["planned_transit_hours"])
        breach = delay > shipment["sla_buffer_hours"]
        probability = float(np.mean(breach))
        penalty = (
            shipment["cargo_value"] * assumptions["late_penalty_fraction"] * shipment["priority"]
        )
        loss = probability * penalty
        expected = float(np.mean(delay))
        planned_date = datetime.fromisoformat(shipment["planned_delivery"])
        results.append(
            {
                **common,
                "expected_delay_hours": expected,
                "delay_p10": float(np.quantile(delay, 0.1)),
                "delay_p50": float(np.quantile(delay, 0.5)),
                "delay_p90": float(np.quantile(delay, 0.9)),
                "breach_probability": probability,
                "monte_carlo_standard_error": float(
                    np.sqrt(probability * (1 - probability) / draws)
                ),
                "breach_indicator": expected > shipment["sla_buffer_hours"],
                "expected_delivery": (planned_date + timedelta(hours=expected)).isoformat(),
                "planned_delivery": shipment["planned_delivery"],
                "sla_buffer_hours": shipment["sla_buffer_hours"],
                "operational_cost": cost,
                "expected_loss": loss,
                "total_expected_cost": cost + loss,
                "priority": shipment["priority"],
                "cargo_exposure": shipment["cargo_value"],
                "explanation": f"P(delay > {shipment['sla_buffer_hours']:.2f}h) from {draws} assumed draws; expected loss = probability x cargo value x penalty fraction x priority. Not a learned probability.",
            }
        )
    return results


def rank(outcomes):
    feasible = [o for o in outcomes if o["feasible"]]
    if not feasible:
        raise ValueError("No feasible action")
    baseline = next(o for o in feasible if o["action"] == "NO_ACTION")
    ranked = sorted(feasible, key=lambda o: (o["total_expected_cost"], o["action"]))
    best = ranked[0]
    return {
        "decision_id": stable_id(best["shipment_id"], "decision-v1"),
        "shipment_id": best["shipment_id"],
        "recommended_action": best["action"],
        "scenario_id": best["scenario_id"],
        "ranked_alternatives": [o["scenario_id"] for o in ranked],
        "expected_benefit": baseline["total_expected_cost"] - best["total_expected_cost"],
        "expected_delay_avoided": baseline["expected_delay_hours"] - best["expected_delay_hours"],
        "breach_reduction": baseline["breach_probability"] - best["breach_probability"],
        "decision_score": -best["total_expected_cost"],
        "expected_loss": best["expected_loss"],
        "expected_delay_hours": best["expected_delay_hours"],
        "breach_probability": best["breach_probability"],
        "decision_confidence": None,
        "confidence_status": "UNVALIDATED_SCENARIO_ASSUMPTIONS",
        "rationale": "Lowest feasible operational cost plus simulated expected late-delivery penalty; human review required.",
        "classification": "SIMULATED",
        "lineage_id": best["scenario_id"],
        "status": "PENDING_REVIEW",
    }
