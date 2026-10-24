"""Persisted weekly Silver and Gold contracts; no workflow decisions enter these layers."""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from maritime.governance import fingerprint
from maritime.models import stable_id

METHOD = "port-week-activity-v1"
REFERENCE_WEEKS = 8
MIN_REFERENCE_WEEKS = 4
FRESHNESS_DAYS = 10
THRESHOLDS = {"ELEVATED": 1.0, "HIGH": 2.0, "CRITICAL": 3.0}


def risk_level(z_score):
    if z_score is None:
        return "INSUFFICIENT_HISTORY"
    if not math.isfinite(z_score):
        raise ValueError("Risk input must be finite")
    for level in ("CRITICAL", "HIGH", "ELEVATED"):
        if abs(z_score) >= THRESHOLDS[level]:
            return level
    return "NORMAL"


class SilverWeek(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    port_id: str
    port_name: str
    country: str
    unlocode: str | None
    week_start: str
    week_end: str
    observed_days: int = Field(ge=0, le=7)
    expected_days: Literal[7] = 7
    observed_calls: float | None = Field(ge=0)
    weekly_calls: float | None = Field(ge=0)
    missing_dates: list[str]
    observation_dates: list[str]
    latest_observation: str | None
    source_latest_observation: str | None
    reference_mean: float | None
    reference_std: float | None
    reference_weeks: list[str]
    z_score: float | None
    completeness: float = Field(ge=0, le=1)
    quality_status: Literal["PASS", "INCOMPLETE"]
    classification: Literal["DERIVED", "SIMULATED"]
    source_lineage_ids: list[str]
    source_ids: list[str]
    input_sha256: str
    lineage_id: str
    methodology_version: Literal["port-week-activity-v1"] = METHOD
    run_id: str


class GoldWeek(SilverWeek):
    review_id: str
    gold_id: str
    risk_revision: str
    risk_level: str
    risk_drivers: list[str]
    freshness_status: Literal["FRESH", "STALE", "UNAVAILABLE"]
    freshness_age_days: int | None
    review_eligible: bool
    as_of: str
    observation_link: str
    simulated: bool


def weekly_silver(ports, activity, as_of, run_id):
    """Monday weeks; missing/partial weeks are never interpreted as zero calls.

    Baseline: up to eight immediately preceding complete calendar weeks, at
    least four required. z=(weekly_calls-reference_mean)/max(1, population_std).
    Both unusually high and low activity are stress proxies, not measured dwell.
    """
    by_port = defaultdict(dict)
    for row in activity:
        day = date.fromisoformat(row["date"])
        if day > as_of or day in by_port[row["port_id"]]:
            raise ValueError("Duplicate or future Silver observation")
        if row["classification"] not in {"OBSERVED", "SIMULATED"}:
            raise ValueError("Weekly input must be observed activity or declared simulation")
        by_port[row["port_id"]][day] = row
    output = []
    for port in ports:
        daily = by_port[port["port_id"]]
        if not daily:
            raise ValueError("Missing port activity")
        first = min(daily)
        start = first - timedelta(days=first.weekday())
        weeks = []
        while start <= as_of:
            days = [start + timedelta(days=i) for i in range(7)]
            records = [daily[day] for day in days if day in daily]
            complete = len(records) == 7
            prior = [w for w in weeks[-REFERENCE_WEEKS:] if w["quality_status"] == "PASS"]
            enough = len(prior) >= MIN_REFERENCE_WEEKS
            mean = statistics.mean(w["weekly_calls"] for w in prior) if enough else None
            std = statistics.pstdev(w["weekly_calls"] for w in prior) if enough else None
            observed = sum(r["vessel_calls"] for r in records) if records else None
            z = (observed - mean) / max(1, std) if complete and enough else None
            inputs = records + [
                daily[date.fromisoformat(day)] for w in prior for day in w["observation_dates"]
            ]
            row = SilverWeek(
                port_id=port["port_id"],
                port_name=port["name"],
                country=port["country"],
                unlocode=(port.get("unlocode") or "").replace(" ", "") or None,
                week_start=str(start),
                week_end=str(days[-1]),
                observed_days=len(records),
                observed_calls=observed,
                weekly_calls=observed if complete else None,
                missing_dates=[str(day) for day in days if day not in daily],
                observation_dates=[str(day) for day in days if day in daily],
                latest_observation=max((r["date"] for r in records), default=None),
                source_latest_observation=str(max(daily)),
                reference_mean=mean,
                reference_std=std,
                reference_weeks=[w["week_start"] for w in prior],
                z_score=z,
                completeness=len(records) / 7,
                quality_status="PASS" if complete else "INCOMPLETE",
                classification="SIMULATED"
                if any(r["classification"] == "SIMULATED" for r in inputs)
                else "DERIVED",
                source_lineage_ids=sorted({r["lineage_id"] for r in inputs}),
                source_ids=sorted({r["source_id"] for r in inputs}),
                input_sha256=fingerprint(
                    [{k: v for k, v in r.items() if k != "retrieved_at"} for r in inputs]
                ),
                lineage_id=stable_id(METHOD, port["port_id"], str(start), inputs),
                run_id=run_id,
            ).model_dump()
            weeks.append(row)
            start += timedelta(days=7)
        output.extend(weeks)
    return output


def weekly_gold(silver, as_of):
    output = []
    for item in silver:
        row = SilverWeek.model_validate(item).model_dump()
        latest = row["source_latest_observation"]
        age = (as_of - date.fromisoformat(latest)).days if latest else None
        fresh = "UNAVAILABLE" if age is None else "FRESH" if 0 <= age <= FRESHNESS_DAYS else "STALE"
        level = risk_level(row["z_score"]) if row["quality_status"] == "PASS" else "INCOMPLETE"
        review_id = stable_id(row["port_id"], row["week_start"], METHOD)
        revision = fingerprint(
            {
                "input": row["input_sha256"],
                "level": level,
                "method": METHOD,
                "quality": row["quality_status"],
            }
        )
        drivers = []
        if row["z_score"] is not None:
            drivers.append(
                "ABOVE_REFERENCE_ACTIVITY" if row["z_score"] >= 0 else "BELOW_REFERENCE_ACTIVITY"
            )
        if row["quality_status"] != "PASS":
            drivers.append("MISSING_OBSERVATIONS")
        if level == "INSUFFICIENT_HISTORY":
            drivers.append("INSUFFICIENT_REFERENCE_WEEKS")
        if fresh != "FRESH":
            drivers.append("SOURCE_NOT_FRESH")
        output.append(
            GoldWeek(
                **row,
                review_id=review_id,
                risk_revision=revision,
                gold_id=stable_id(review_id, revision),
                risk_level=level,
                risk_drivers=drivers,
                freshness_status=fresh,
                freshness_age_days=age,
                review_eligible=level in {"HIGH", "CRITICAL"} and fresh == "FRESH",
                as_of=str(as_of),
                simulated=row["classification"] == "SIMULATED",
                observation_link=f"/operations/observations/{review_id}?run_id={row['run_id']}",
            ).model_dump()
        )
    return output
