"""Stored chat answers, so every answer can be audited and re-read by ID."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow

_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ChatRecord(Base):
    __tablename__ = "chat_record"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    equipment_id: Mapped[str | None] = mapped_column(String(64), index=True)
    verification_status: Mapped[str] = mapped_column(String(32))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
