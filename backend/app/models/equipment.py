"""Equipment and component tables.

Readings and events are added with the simulator milestone.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    equipment_type: Mapped[str] = mapped_column(String(32), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    location_label: Mapped[str | None] = mapped_column(String(128))
    commissioned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), index=True, default="operational")
    simulation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    components: Mapped[list["Component"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
        order_by="Component.id",
    )


class Component(Base):
    __tablename__ = "component"

    # Component IDs (e.g. CMP-001) are unique per equipment, so the key is composite.
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    component_type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="normal")
    source_note: Mapped[str | None] = mapped_column(String(256))

    equipment: Mapped[Equipment] = relationship(back_populates="components")
