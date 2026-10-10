"""Deterministic activity proxy and time-bounded graph exposure, methodology v1."""

import math
from itertools import islice

import networkx as nx
import pandas as pd

from maritime.models import stable_id, utcnow


def congestion(activity, baseline_days=56, min_history=28):
    frame = pd.DataFrame(activity).sort_values(["port_id", "date"])
    results = []
    for port_id, group in frame.groupby("port_id"):
        group = group.copy()
        group.index = pd.to_datetime(group["date"])
        # Calendar rolling windows, prior observations only; no future leakage.
        series = group["vessel_calls"].astype(float)
        baseline = series.rolling(
            f"{baseline_days}D", closed="left", min_periods=min_history
        ).mean()
        std = series.rolling(f"{baseline_days}D", closed="left", min_periods=min_history).std(
            ddof=0
        )
        persistence = 0
        previous_date = None
        for idx, (day, row) in enumerate(group.iterrows()):
            mean = baseline.iloc[idx]
            enough = not pd.isna(mean)
            z = (row["vessel_calls"] - mean) / max(1.0, std.iloc[idx]) if enough else None
            magnitude = abs(z) if enough else 0
            category = (
                (
                    "CRITICAL"
                    if magnitude >= 3
                    else "HIGH"
                    if magnitude >= 2
                    else "ELEVATED"
                    if magnitude >= 1
                    else "NORMAL"
                )
                if enough
                else "INSUFFICIENT_HISTORY"
            )
            consecutive = previous_date is not None and (day - previous_date).days == 1
            persistence = (
                (persistence + 1 if consecutive else 1) if enough and magnitude >= 1 else 0
            )
            prior = series[
                (series.index < day) & (series.index >= day - pd.Timedelta(days=baseline_days))
            ]
            classification = "SIMULATED" if row["classification"] == "SIMULATED" else "DERIVED"
            results.append(
                {
                    "state_id": stable_id(port_id, row["date"], "congestion-v1"),
                    "port_id": port_id,
                    "date": row["date"],
                    "current_activity": float(row["vessel_calls"]),
                    "baseline": float(mean) if enough else None,
                    "z_score": float(z) if enough else None,
                    "deviation_fraction": float((row["vessel_calls"] - mean) / max(1.0, mean))
                    if enough
                    else None,
                    "percentile": float((prior <= row["vessel_calls"]).mean()) if enough else None,
                    "history_records": len(prior),
                    "persistence_days": persistence,
                    "category": category,
                    "stress_score": min(1.0, magnitude / 3) if enough else None,
                    "trend": "ABOVE_BASELINE"
                    if enough and z > 0
                    else "BELOW_BASELINE"
                    if enough
                    else "UNKNOWN",
                    "evidence_coverage": min(1.0, len(prior) / baseline_days),
                    "methodology": "activity-deviation proxy for port stress/congestion; v1",
                    "classification": classification,
                    "lineage_id": row["lineage_id"],
                    "source_id": row["source_id"],
                    "valid_from": row["date"],
                    "valid_to": row["date"],
                }
            )
            previous_date = day
    return results


def latest_states(history):
    latest = {}
    for row in history:
        if row["port_id"] not in latest or row["date"] > latest[row["port_id"]]["date"]:
            latest[row["port_id"]] = row
    return list(latest.values())


def nautical_distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3440.065 * 2 * math.asin(min(1, math.sqrt(hav)))


def scenario_routes(ports, as_of, assumptions):
    """Explicit simulated connectivity. Great-circle distances are NOT navigable sea lanes."""
    rows = []
    for a in ports:
        for b in ports:
            if a == b:
                continue
            distance = max(1, nautical_distance(a, b) * assumptions["distance_factor"])
            rows.append(
                {
                    "route_id": stable_id(a["port_id"], b["port_id"], "assumed-route-v1"),
                    "origin": a["port_id"],
                    "destination": b["port_id"],
                    "distance_nm": distance,
                    "transit_hours": distance / assumptions["speed_knots"],
                    "available": True,
                    "valid_from": as_of.isoformat(),
                    "valid_to": None,
                    "geometry": None,
                    "source_id": "scenario_topology_v1",
                    "classification": "SIMULATED",
                    "retrieved_at": utcnow(),
                    "lineage_id": stable_id(a["lineage_id"], b["lineage_id"], assumptions),
                }
            )
    return rows


def network_state(ports, routes, states, as_of, disruptions=()):
    graph = nx.DiGraph(as_of=as_of.isoformat())
    stress = {s["port_id"]: s for s in states}
    closed = {
        d["port_id"]
        for d in disruptions
        if d.get("closed") and d["valid_from"] <= as_of.isoformat() <= d["valid_to"]
    }
    for port in ports:
        state = stress[port["port_id"]]
        if state["stress_score"] is None:
            raise ValueError(f"Insufficient baseline for {port['port_id']}")
        graph.add_node(
            port["port_id"], **port, stress_score=state["stress_score"], state_id=state["state_id"]
        )
    edges = []
    for route in routes:
        valid = route["valid_from"] <= as_of.isoformat() and (
            route.get("valid_to") is None or as_of.isoformat() <= route["valid_to"]
        )
        available = (
            route["available"]
            and valid
            and route["origin"] not in closed
            and route["destination"] not in closed
        )
        score = max(
            stress[route["origin"]]["stress_score"], stress[route["destination"]]["stress_score"]
        )
        edge = {
            **route,
            "available": available,
            "stress_score": score,
            "as_of": as_of.isoformat(),
            "state_id": stable_id(route["route_id"], as_of, score, available),
            "classification": "SIMULATED"
            if route["classification"] == "SIMULATED"
            or any(
                stress[p]["classification"] == "SIMULATED"
                for p in (route["origin"], route["destination"])
            )
            else "DERIVED",
            "weight": route["transit_hours"] * (1 + score * 0.25),
        }
        edges.append(edge)
        if available:
            graph.add_edge(route["origin"], route["destination"], **edge)
    return graph, edges


def propagate(graph, states, horizon_hours=720, decay=0.65, max_depth=4):
    if not 0 <= decay <= 1 or horizon_hours <= 0:
        raise ValueError("Invalid propagation assumptions")
    results = []
    for state in states:
        if state["category"] not in {"HIGH", "CRITICAL"}:
            continue
        origin = state["port_id"]
        frontier = [(origin, 0, 0.0, state["stress_score"], [origin])]
        best = {origin: [(state["stress_score"], 0.0)]}
        while frontier:
            node, depth, elapsed, exposure, path = frontier.pop(0)
            results.append(
                {
                    "origin": origin,
                    "port_id": node,
                    "depth": depth,
                    "arrival_hours": elapsed,
                    "exposure_score": exposure,
                    "propagation_confidence": decay**depth,
                    "confidence_type": "ASSUMED_ATTENUATION_NOT_CALIBRATED",
                    "path": path,
                    "classification": "SIMULATED"
                    if state["classification"] == "SIMULATED"
                    or any(e["classification"] == "SIMULATED" for _, _, e in graph.edges(data=True))
                    else "DERIVED",
                    "input_classifications": sorted(
                        {e["classification"] for _, _, e in graph.edges(data=True)}
                    ),
                    "lineage_id": state["state_id"],
                    "as_of": graph.graph["as_of"],
                    "methodology": "bounded directed exposure v1; not observed cargo movement",
                }
            )
            if depth >= max_depth:
                continue
            for successor in sorted(graph.successors(node)):
                arrival = elapsed + graph[node][successor]["transit_hours"]
                next_exposure = exposure * decay
                if (
                    successor not in path
                    and arrival <= horizon_hours
                    and not any(
                        score >= next_exposure and at <= arrival
                        for score, at in best.get(successor, [])
                    )
                ):
                    best.setdefault(successor, []).append((next_exposure, arrival))
                    frontier.append(
                        (successor, depth + 1, arrival, next_exposure, path + [successor])
                    )
    return results


def alternate_paths(graph, origin, destination, limit=3):
    try:
        return list(
            islice(nx.shortest_simple_paths(graph, origin, destination, weight="weight"), limit)
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def path_hours(graph, path):
    return sum(graph[a][b]["transit_hours"] for a, b in zip(path, path[1:]))


def geojson(ports, states, edges):
    by_port = {p["port_id"]: p for p in ports}
    features = []
    for s in states:
        port = by_port[s["port_id"]]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [port["longitude"], port["latitude"]]},
                "properties": {**s, "name": port["name"]},
            }
        )
    for edge in edges:
        # Only verified source geometry is mapped; no misleading land-crossing lines.
        if edge.get("geometry"):
            features.append(
                {
                    "type": "Feature",
                    "geometry": edge["geometry"],
                    "properties": {k: v for k, v in edge.items() if k != "geometry"},
                }
            )
    return {"type": "FeatureCollection", "features": features}
