import hashlib
import json
from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Classification(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    ANTICIPATED = "ANTICIPATED"
    SIMULATED = "SIMULATED"
    PREDICTED = "PREDICTED"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*values) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()[:24]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source_id: str
    classification: Classification
    retrieved_at: datetime
    lineage_id: str

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("UTC-aware retrieval timestamp required")
        return value.astimezone(timezone.utc)


class Port(Record):
    port_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    unlocode: str | None = None


class Activity(Record):
    port_id: str
    date: date
    vessel_calls: float = Field(ge=0)


class Route(Record):
    route_id: str
    origin: str
    destination: str
    distance_nm: float = Field(gt=0)
    transit_hours: float = Field(gt=0)
    available: bool = True
    valid_from: date
    valid_to: date | None = None
    geometry: dict | None = None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(accept|reject|override)$")
    action: str | None = Field(
        default=None, pattern="^(NO_ACTION|REROUTE|ALTERNATE_PORT|EXPEDITE|PRIORITIZE)$"
    )
    reason: str = Field(min_length=5, max_length=2000)
    operator: str = Field(min_length=1, max_length=100)


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    decision_id: str
    actual_action: str = Field(pattern="^(NO_ACTION|REROUTE|ALTERNATE_PORT|EXPEDITE|PRIORITIZE)$")
    actual_delay_hours: float = Field(ge=0)
    actual_loss: float = Field(ge=0)
    classification: Classification
    evidence: str = Field(min_length=5)
