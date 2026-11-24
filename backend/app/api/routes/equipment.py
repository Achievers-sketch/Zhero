"""Equipment endpoints under /api/v1/equipment."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentList,
    EquipmentRead,
    EquipmentStatus,
    EquipmentUpdate,
)
from app.services import equipment_service

router = APIRouter(prefix="/equipment", tags=["equipment"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=EquipmentRead, status_code=201)
def create_equipment(payload: EquipmentCreate, db: DbSession) -> EquipmentRead:
    """Create an ultrasound equipment profile (software simulation only)."""
    return EquipmentRead.model_validate(equipment_service.create_equipment(db, payload))


@router.get("", response_model=EquipmentList)
def list_equipment(
    db: DbSession,
    equipment_type: str | None = None,
    status: EquipmentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EquipmentList:
    items, total = equipment_service.list_equipment(
        db, equipment_type=equipment_type, status=status, limit=limit, offset=offset
    )
    return EquipmentList(
        items=[EquipmentRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: str, db: DbSession) -> EquipmentRead:
    return EquipmentRead.model_validate(equipment_service.get_equipment(db, equipment_id))


@router.patch("/{equipment_id}", response_model=EquipmentRead)
def update_equipment(equipment_id: str, payload: EquipmentUpdate, db: DbSession) -> EquipmentRead:
    """Update editable metadata. Status and event history are not editable here."""
    return EquipmentRead.model_validate(
        equipment_service.update_equipment(db, equipment_id, payload)
    )
