"""Document and chunk tables (RAG stages 1, 2 and 4)."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow

_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(8))  # pdf | txt
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_key: Mapped[str | None] = mapped_column(String(256))  # never exposed by the API

    # uploaded | ingested | empty | failed
    status: Mapped[str] = mapped_column(String(16), index=True, default="uploaded")
    status_detail: Mapped[str | None] = mapped_column(String(512))
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # Provenance metadata (blueprint: record source, revision and applicability).
    source_note: Mapped[str | None] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(128))
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    equipment_type: Mapped[str | None] = mapped_column(String(32), index=True)
    model_applicability: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[str | None] = mapped_column(String(64))

    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ingested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    parser_version: Mapped[str | None] = mapped_column(String(128))
    ingestion_run_id: Mapped[str | None] = mapped_column(String(32))


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
        Index("ix_chunk_document", "document_id"),
    )

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        _PK_TYPE,
        ForeignKey("document.id", ondelete="CASCADE"),
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)  # null for plain text
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    ingestion_run_id: Mapped[str] = mapped_column(String(32))
