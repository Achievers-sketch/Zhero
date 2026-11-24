"""Equipment and component API schemas (blueprint sections 7 and 10)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EquipmentStatus = Literal["operational", "warning", "fault", "unknown"]
ComponentStatus = Literal["normal", "warning", "fault", "unknown"]

EQUIPMENT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$"


class ComponentCreate(BaseModel):
    component_id: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    component_type: str | None = Field(default=None, max_length=64)
    status: ComponentStatus = "normal"
    source_note: str | None = Field(default=None, max_length=256)


class ComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    component_id: str = Field(validation_alias="id")
    name: str
    component_type: str | None
    status: ComponentStatus
    source_note: str | None


# Default components from the blueprint's proposed ultrasound profile.
DEFAULT_COMPONENTS: list[tuple[str, str]] = [
    ("CMP-001", "Power subsystem"),
    ("CMP-002", "Cooling subsystem"),
    ("CMP-003", "Probe/transducer"),
    ("CMP-004", "Display/control subsystem"),
]


class EquipmentCreate(BaseModel):
    """Create an ultrasound profile. Manufacturer/model stay null unless a real model is chosen."""

    equipment_id: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    equipment_type: Literal["Ultrasound"] = "Ultrasound"
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    location_label: str | None = Field(default=None, max_length=128)
    commissioned_at: datetime | None = None
    simulation_enabled: bool = True
    # Omit to get the four default components; pass [] for none.
    components: list[ComponentCreate] | None = None


class EquipmentUpdate(BaseModel):
    """Editable metadata only. Status and history are changed by the twin, not by PATCH."""

    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    location_label: str | None = Field(default=None, max_length=128)
    commissioned_at: datetime | None = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    equipment_id: str = Field(validation_alias="id")
    equipment_type: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    location_label: str | None
    commissioned_at: datetime | None
    status: EquipmentStatus
    simulation_enabled: bool
    components: list[ComponentRead]
    created_at: datetime
    updated_at: datetime


class EquipmentList(BaseModel):
    items: list[EquipmentRead]
    total: int
    limit: int
    offset: int
