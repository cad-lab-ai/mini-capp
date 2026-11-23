from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Model):
    source: str = Field(min_length=1, max_length=2000)
    observed_at: str = Field(min_length=1, max_length=100)
    status: Literal["confirmed", "assumed", "unknown"] = "unknown"


class Resource(Model):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=300)
    kind: Literal["general", "equipment", "workplace", "tooling", "material", "capability", "quality", "subcontractor"]
    availability: Literal["available", "unavailable", "requires_preparation", "requires_purchase", "unknown"] = "unknown"
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: Evidence


class Operation(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    resource_ids: list[str] = Field(default_factory=list, max_length=100)
    setups: list[str] = Field(default_factory=list, max_length=100)
    transitions: list[str] = Field(default_factory=list, max_length=200)
    control: list[str] = Field(default_factory=list, max_length=100)
    time_minutes: float | None = Field(default=None, ge=0)
    time_source: str | None = None


class ProcessPlan(Model):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=300)
    part_revision: str = Field(min_length=1, max_length=300)
    drawing_source: str = Field(min_length=1, max_length=2000)
    passport_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    material: str = Field(min_length=1, max_length=1000)
    blank: str = Field(min_length=1, max_length=1000)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    open_questions: list[str] = Field(default_factory=list, max_length=100)
    operations: list[Operation] = Field(default_factory=list, max_length=500)
    status: Literal["draft"] = "draft"
