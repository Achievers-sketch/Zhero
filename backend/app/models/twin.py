"""Digital-twin tables: readings, events and per-equipment simulation state.

Readings and events carry ``simulation`` with a CHECK constraint forcing it true: in the
MVP there is no real telemetry, so the database itself refuses non-simulated rows.
Drop the constraint deliberately (with a migration) if real data is ever introduced.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow

# BigInteger PKs need to be plain INTEGER on SQLite for autoincrement to work.
_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class TwinState(Base):
    """Simulation cursor and active scenario for one equipment profile."""

    __tablename__ = "twin_state"

    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True
    )
    seed: Mapped[int] = mapped_column(BigInteger)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    active_scenario: Mapped[str | None] = mapped_column(String(32))
    scenario_started_step: Mapped[int | None] = mapped_column(Integer)
    active_component_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Reading(Base):
    __tablename__ = "reading"
    __table_args__ = (
        CheckConstraint("simulation", name="ck_reading_simulation_true"),
        Index("ix_reading_equipment_timestamp", "equipment_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"))
    variable: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    simulation: Mapped[bool] = mapped_column(Boolean, default=True)
    scenario_id: Mapped[str | None] = mapped_column(String(32))
    step_index: Mapped[int] = mapped_column(Integer)


class EquipmentEvent(Base):
    __tablename__ = "equipment_event"
    __table_args__ = (CheckConstraint("simulation", name="ck_equipment_event_simulation_true"),)

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    scenario: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(256))
    simulation: Mapped[bool] = mapped_column(Boolean, default=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
