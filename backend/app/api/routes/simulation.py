"""Digital-twin endpoints under /api/v1/equipment/{id}. All data is SIMULATED."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.twin import EquipmentEvent, TwinState
from app.schemas.equipment import ComponentRead
from app.schemas.twin import (
    EventList,
    EventRead,
    FaultRequest,
    ReadingList,
    ReadingRead,
    SimulateRequest,
    SimulateResponse,
    TwinStatus,
)
from app.services import simulation_service

router = APIRouter(prefix="/equipment/{equipment_id}", tags=["digital twin (simulated)"])

DbSession = Annotated[Session, Depends(get_db)]


def _status(
    equipment: Equipment, state: TwinState, event: EquipmentEvent | None = None
) -> dict[str, object]:
    return {
        "equipment_id": equipment.id,
        "status": equipment.status,
        "active_scenario": state.active_scenario,
        "components": [ComponentRead.model_validate(c) for c in equipment.components],
        "event": EventRead.model_validate(event) if event else None,
    }


@router.post("/simulate", response_model=SimulateResponse)
def simulate(
    equipment_id: str, db: DbSession, payload: SimulateRequest | None = None
) -> SimulateResponse:
    """Generate the next simulation step(s). Responses always carry simulation=true."""
    payload = payload or SimulateRequest()
    equipment, state, event, readings = simulation_service.simulate(
        db, equipment_id, steps=payload.steps, seed=payload.seed, scenario=payload.scenario
    )
    return SimulateResponse(
        **_status(equipment, state, event),
        readings=[ReadingRead.model_validate(r) for r in readings],
    )


@router.post("/faults", response_model=TwinStatus, status_code=201)
def trigger_fault(equipment_id: str, payload: FaultRequest, db: DbSession) -> TwinStatus:
    """Trigger an allow-listed simulated fault scenario."""
    equipment, state, event = simulation_service.trigger_fault(
        db, equipment_id, payload.scenario, payload.component_id
    )
    return TwinStatus(**_status(equipment, state, event))


@router.post("/reset", response_model=TwinStatus)
def reset_fault(equipment_id: str, db: DbSession) -> TwinStatus:
    """Reset the active simulated fault. History is preserved; a reset event is recorded."""
    equipment, state, event = simulation_service.reset_fault(db, equipment_id)
    return TwinStatus(**_status(equipment, state, event))


@router.get("/readings", response_model=ReadingList)
def list_readings(
    equipment_id: str,
    db: DbSession,
    variable: str | None = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReadingList:
    """Time-series of simulated readings. `from`/`to` are ISO 8601 (naive values mean UTC)."""
    items, total = simulation_service.list_readings(
        db,
        equipment_id,
        variable=variable,
        start=start,
        end=end,
        order=order,
        limit=limit,
        offset=offset,
    )
    return ReadingList(
        items=[ReadingRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events", response_model=EventList)
def list_events(
    equipment_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventList:
    """Event history, newest first."""
    items, total = simulation_service.list_events(db, equipment_id, limit=limit, offset=offset)
    return EventList(
        items=[EventRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )
