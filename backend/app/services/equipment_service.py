"""Equipment business logic. Route handlers stay thin and call these functions."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.equipment import Component, Equipment
from app.schemas.equipment import (
    DEFAULT_COMPONENTS,
    ComponentCreate,
    EquipmentCreate,
    EquipmentUpdate,
)


def create_equipment(db: Session, payload: EquipmentCreate) -> Equipment:
    """Create an equipment profile with its components; reject duplicate IDs."""
    if db.get(Equipment, payload.equipment_id) is not None:
        raise ConflictError(f"Equipment '{payload.equipment_id}' already exists.")

    components = payload.components
    if components is None:
        components = [
            ComponentCreate(component_id=cid, name=name) for cid, name in DEFAULT_COMPONENTS
        ]
    if len({c.component_id for c in components}) != len(components):
        raise ConflictError("Component IDs must be unique within an equipment profile.")

    equipment = Equipment(
        id=payload.equipment_id,
        equipment_type=payload.equipment_type,
        manufacturer=payload.manufacturer,
        model=payload.model,
        serial_number=payload.serial_number,
        location_label=payload.location_label,
        commissioned_at=payload.commissioned_at,
        simulation_enabled=payload.simulation_enabled,
        status="operational",
        components=[
            Component(
                id=c.component_id,
                name=c.name,
                component_type=c.component_type,
                status=c.status,
                source_note=c.source_note,
            )
            for c in components
        ],
    )
    db.add(equipment)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent create of the same ID
        db.rollback()
        raise ConflictError(f"Equipment '{payload.equipment_id}' already exists.") from exc
    return equipment


def get_equipment(db: Session, equipment_id: str) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise NotFoundError(f"Equipment '{equipment_id}' not found.")
    return equipment


def list_equipment(
    db: Session,
    *,
    equipment_type: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Equipment], int]:
    query = select(Equipment)
    if equipment_type:
        query = query.where(Equipment.equipment_type == equipment_type)
    if status:
        query = query.where(Equipment.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Equipment.id).limit(limit).offset(offset)).all()
    return list(items), total


def update_equipment(db: Session, equipment_id: str, payload: EquipmentUpdate) -> Equipment:
    """Apply only the fields the client sent; never touches status or history."""
    equipment = get_equipment(db, equipment_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(equipment, field, value)
    db.commit()
    return equipment
