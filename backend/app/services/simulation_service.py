"""Digital-twin business logic: simulate, trigger faults, reset, query history.

All data produced here is SIMULATED. Faults and resets never delete history: events are
appended and active events are marked resolved.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.db.base import utcnow
from app.digital_twin import config
from app.digital_twin.simulator import generate_step
from app.models.equipment import Equipment
from app.models.twin import EquipmentEvent, Reading, TwinState
from app.services.equipment_service import get_equipment

# Components affected by each scenario when the client does not name one.
_STATUS_AFTER_FAULT = {"warning": "warning", "fault": "fault"}


def _load(db: Session, equipment_id: str) -> tuple[Equipment, TwinState]:
    """Load equipment and its twin state (creating state with a stored seed on first use)."""
    equipment = get_equipment(db, equipment_id)
    state = db.scalar(
        select(TwinState).where(TwinState.equipment_id == equipment_id).with_for_update()
    )
    if state is None:
        state = TwinState(equipment_id=equipment_id, seed=secrets.randbelow(2**32), step_index=0)
        db.add(state)
        db.flush()
    return equipment, state


def _require_enabled(equipment: Equipment) -> None:
    if not equipment.simulation_enabled:
        raise AppError(409, "simulation_disabled", "Simulation is disabled for this equipment.")


def _apply_fault(
    db: Session,
    equipment: Equipment,
    state: TwinState,
    scenario: str,
    component_id: str | None,
) -> EquipmentEvent:
    if state.active_scenario is not None:
        raise AppError(
            409,
            "fault_active",
            f"Scenario '{state.active_scenario}' is already active; reset it first.",
        )
    spec = config.SCENARIOS[scenario]
    by_id = {c.id: c for c in equipment.components}

    if scenario == "component_fault":
        target_id = component_id or spec.default_component_id
        if target_id not in by_id:
            if component_id is not None:
                raise NotFoundError(f"Component '{component_id}' not found on this equipment.")
            if not equipment.components:
                raise AppError(409, "no_component", "Equipment has no components to fault.")
            target_id = equipment.components[0].id
    else:
        target_id = spec.default_component_id
        if component_id is not None:
            raise AppError(
                422, "validation_error", "component_id is only valid for component_fault."
            )

    component = by_id.get(target_id)
    if component is not None:
        component.status = _STATUS_AFTER_FAULT[spec.severity]
    equipment.status = _STATUS_AFTER_FAULT[spec.severity]

    state.active_scenario = scenario
    state.scenario_started_step = state.step_index
    state.active_component_id = component.id if component else None

    event = EquipmentEvent(
        equipment_id=equipment.id,
        event_type="SIMULATED_FAULT",
        scenario=scenario,
        severity=spec.severity,
        description=spec.description,
        simulation=True,
        occurred_at=utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def trigger_fault(
    db: Session, equipment_id: str, scenario: str, component_id: str | None
) -> tuple[Equipment, TwinState, EquipmentEvent]:
    equipment, state = _load(db, equipment_id)
    _require_enabled(equipment)
    event = _apply_fault(db, equipment, state, scenario, component_id)
    db.commit()
    return equipment, state, event


def reset_fault(db: Session, equipment_id: str) -> tuple[Equipment, TwinState, EquipmentEvent]:
    """Clear the active scenario, restore normal status and record a reset event."""
    equipment, state = _load(db, equipment_id)
    _require_enabled(equipment)
    if state.active_scenario is None:
        raise AppError(409, "no_active_fault", "There is no active simulated fault to reset.")

    now = utcnow()
    previous = state.active_scenario
    open_events = db.scalars(
        select(EquipmentEvent).where(
            EquipmentEvent.equipment_id == equipment_id,
            EquipmentEvent.event_type == "SIMULATED_FAULT",
            EquipmentEvent.resolved_at.is_(None),
        )
    ).all()
    for open_event in open_events:
        open_event.resolved_at = now

    for component in equipment.components:
        component.status = "normal"
    equipment.status = "operational"
    state.active_scenario = None
    state.scenario_started_step = None
    state.active_component_id = None

    event = EquipmentEvent(
        equipment_id=equipment_id,
        event_type="SIMULATION_RESET",
        scenario=previous,
        severity="info",
        description=f"Simulated scenario '{previous}' was reset.",
        simulation=True,
        occurred_at=now,
        resolved_at=now,
    )
    db.add(event)
    db.commit()
    return equipment, state, event


def simulate(
    db: Session,
    equipment_id: str,
    *,
    steps: int,
    seed: int | None,
    scenario: str | None,
) -> tuple[Equipment, TwinState, EquipmentEvent | None, list[Reading]]:
    """Generate ``steps`` synthetic samples; optionally trigger a scenario first."""
    equipment, state = _load(db, equipment_id)
    _require_enabled(equipment)
    if seed is not None:
        state.seed = seed

    event = _apply_fault(db, equipment, state, scenario, None) if scenario else None

    now = utcnow()
    readings: list[Reading] = []
    for i in range(steps):
        index = state.step_index
        active = state.active_scenario
        values = generate_step(
            seed=state.seed,
            step_index=index,
            scenario=active,
            scenario_step=index - state.scenario_started_step if active else 0,
        )
        # Back-date so the newest sample in this call is "now".
        timestamp = now - timedelta(seconds=config.SIMULATION_INTERVAL_S * (steps - 1 - i))
        for variable, value in values.items():
            readings.append(
                Reading(
                    equipment_id=equipment_id,
                    variable=variable,
                    value=value,
                    unit=config.VARIABLES[variable].unit,
                    timestamp=timestamp,
                    simulation=True,
                    scenario_id=active,
                    step_index=index,
                )
            )
        state.step_index += 1
    db.add_all(readings)
    db.commit()
    return equipment, state, event, readings


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)  # naive timestamps are interpreted as UTC
    return value


def list_readings(
    db: Session,
    equipment_id: str,
    *,
    variable: str | None,
    start: datetime | None,
    end: datetime | None,
    order: str,
    limit: int,
    offset: int,
) -> tuple[list[Reading], int]:
    get_equipment(db, equipment_id)
    query = select(Reading).where(Reading.equipment_id == equipment_id)
    if variable:
        query = query.where(Reading.variable == variable)
    if start := _as_utc(start):
        query = query.where(Reading.timestamp >= start)
    if end := _as_utc(end):
        query = query.where(Reading.timestamp <= end)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    ordering = (
        (Reading.timestamp.desc(), Reading.id.desc())
        if order == "desc"
        else (Reading.timestamp, Reading.id)
    )
    items = db.scalars(query.order_by(*ordering).limit(limit).offset(offset)).all()
    return list(items), total


def list_events(
    db: Session, equipment_id: str, *, limit: int, offset: int
) -> tuple[list[EquipmentEvent], int]:
    get_equipment(db, equipment_id)
    query = select(EquipmentEvent).where(EquipmentEvent.equipment_id == equipment_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(EquipmentEvent.occurred_at.desc(), EquipmentEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total
