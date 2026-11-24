"""Digital-twin API schemas. Every payload states simulation=true (blueprint FR-03)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.digital_twin.config import ScenarioId
from app.schemas.equipment import ComponentRead, EquipmentStatus

Seed = Annotated[int, Field(ge=0, lt=2**32)]


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: int = Field(default=1, ge=1, le=100)
    # Supply a seed for reproducible values; otherwise the stored per-equipment seed is used.
    seed: Seed | None = None
    # Optionally trigger an allow-listed scenario before simulating.
    scenario: ScenarioId | None = None


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioId
    component_id: str | None = Field(default=None, max_length=64)


class ReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_id: int = Field(validation_alias="id")
    equipment_id: str
    variable: str
    value: float
    unit: str
    timestamp: datetime
    simulation: Literal[True]
    scenario_id: str | None
    step_index: int


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(exclude=True)
    equipment_id: str
    event_type: str
    scenario: str | None
    severity: str
    description: str
    simulation: Literal[True]
    occurred_at: datetime
    resolved_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def event_id(self) -> str:
        return f"EVT-{self.id:04d}"


class TwinStatus(BaseModel):
    equipment_id: str
    simulation: Literal[True] = True
    status: EquipmentStatus
    active_scenario: str | None
    components: list[ComponentRead]
    event: EventRead | None = None


class SimulateResponse(TwinStatus):
    readings: list[ReadingRead]


class ReadingList(BaseModel):
    simulation: Literal[True] = True
    items: list[ReadingRead]
    total: int
    limit: int
    offset: int


class EventList(BaseModel):
    simulation: Literal[True] = True
    items: list[EventRead]
    total: int
    limit: int
    offset: int
