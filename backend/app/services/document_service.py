"""Document upload, ingestion and lookup (RAG stages 1, 2 and 4).

Uploaded documents are untrusted data: they are validated, stored under generated
filenames outside any web root, and never executed or interpreted as instructions.
"""

import hashlib
import logging
import re
import time
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.base import utcnow
from app.models.document import Chunk, Document
from app.rag.chunking import chunk_pages, clean_pages
from app.rag.parsing import PARSER_VERSION, ParseError, parse_pdf, parse_txt

logger = logging.getLogger("zhero.documents")

_ALLOWED = {
    "pdf": {"application/pdf"},
    "txt": {"text/plain"},
}
_DOC_ID = re.compile(r"DOC-(\d{1,9})")


def parse_document_id(value: str) -> int:
    match = _DOC_ID.fullmatch(value)
    if match is None:
        raise NotFoundError(f"Document '{value}' not found.")
    return int(match.group(1))


def _safe_filename(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()[:255]
    if not name:
        raise AppError(422, "invalid_file", "A filename is required.")
    return name


def read_limited(stream: BinaryIO, max_bytes: int) -> bytes:
    """Read an upload, refusing anything larger than ``max_bytes``."""
    data = bytearray()
    while chunk := stream.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise AppError(413, "file_too_large", "The file exceeds the maximum upload size.")
    return bytes(data)


def _validate(filename: str, content_type: str | None, data: bytes) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in _ALLOWED:
        raise AppError(415, "unsupported_file_type", "Only PDF and TXT files are supported.")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in _ALLOWED[extension]:
        raise AppError(
            415, "unsupported_file_type", "File content type does not match its extension."
        )
    if not data:
        raise AppError(422, "invalid_file", "The file is empty.")
    if extension == "pdf" and b"%PDF-" not in data[:1024]:
        raise AppError(422, "invalid_file", "The file does not look like a PDF.")
    if extension == "txt" and b"\x00" in data:
        raise AppError(422, "invalid_file", "The file is not plain text.")
    return extension


def _storage_path(settings: Settings, storage_key: str) -> Path:
    base = Path(settings.upload_dir).resolve()
    path = (base / storage_key).resolve()
    if not path.is_relative_to(base):
        raise AppError(500, "storage_error", "Document storage error.")
    return path


def create_document(
    db: Session,
    settings: Settings,
    *,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    metadata: dict[str, str | None],
) -> Document:
    """Validate and store an upload (status ``uploaded``); ingestion is a separate step."""
    safe_name = _safe_filename(filename)
    extension = _validate(safe_name, content_type, data)
    digest = hashlib.sha256(data).hexdigest()

    existing = db.scalar(select(Document).where(Document.sha256 == digest))
    if existing is not None:
        raise ConflictError(f"This file was already uploaded as DOC-{existing.id:04d}.")

    stem = safe_name.rsplit(".", 1)[0]
    document = Document(
        title=(metadata.get("title") or stem)[:200],
        original_filename=safe_name,
        file_type=extension,
        size_bytes=len(data),
        sha256=digest,
        status="uploaded",
        warnings=[],
        chunk_count=0,
        source_note=metadata.get("source_note"),
        publisher=metadata.get("publisher"),
        manufacturer=metadata.get("manufacturer"),
        equipment_type=metadata.get("equipment_type"),
        model_applicability=metadata.get("model_applicability"),
        revision=metadata.get("revision"),
    )
    path: Path | None = None
    try:
        db.add(document)
        db.flush()  # assigns the document ID used in the storage path
        document.storage_key = f"DOC-{document.id:04d}/{uuid.uuid4().hex}.{extension}"
        path = _storage_path(settings, document.storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        db.commit()
    except IntegrityError as exc:  # concurrent upload of identical content
        db.rollback()
        raise ConflictError("This file was already uploaded.") from exc
    except OSError as exc:
        db.rollback()
        logger.error("document_store_failed", extra={"error_type": type(exc).__name__})
        raise AppError(500, "storage_error", "The file could not be stored.") from exc
    except Exception:
        db.rollback()
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return document


def get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, parse_document_id(document_id))
    if document is None:
        raise NotFoundError(f"Document '{document_id}' not found.")
    return document


def ingest_document(db: Session, settings: Settings, document_id: str) -> Document:
    """Parse, clean, chunk and store a document. Idempotent for already-ingested documents."""
    document = get_document(db, document_id)
    if document.status == "ingested":
        return document

    started = time.perf_counter()
    run_id = uuid.uuid4().hex
    document.ingestion_run_id = run_id
    document.parser_version = PARSER_VERSION
    document.warnings = []

    def finish(status: str, detail: str | None) -> Document:
        document.status = status
        document.status_detail = detail
        document.ingested_at = utcnow() if status == "ingested" else None
        db.commit()
        logger.info(
            "document_ingestion",
            extra={
                "document_id": f"DOC-{document.id:04d}",
                "status": status,
                "chunks": document.chunk_count,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return document

    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    document.chunk_count = 0

    try:
        path = _storage_path(settings, document.storage_key or "")
        data = path.read_bytes()
    except (OSError, AppError):
        return finish("failed", "The stored file could not be read.")
    if hashlib.sha256(data).hexdigest() != document.sha256:
        return finish("failed", "The stored file does not match its recorded checksum.")

    try:
        parsed = parse_pdf(data) if document.file_type == "pdf" else parse_txt(data)
    except ParseError as exc:
        return finish("failed", f"{exc.code}: {exc.message}")

    document.page_count = parsed.page_count
    document.warnings = parsed.warnings[:200]
    pages = clean_pages(parsed.pages)
    drafts = chunk_pages(
        pages, chunk_size=settings.rag_chunk_size, overlap=settings.rag_chunk_overlap
    )
    if not drafts:
        return finish(
            "empty",
            "No extractable text was found (blank or image-only document; OCR is not supported).",
        )

    db.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=d.index,
            page_start=d.page_start,
            page_end=d.page_end,
            section=d.section[:200] if d.section else None,
            text=d.text,
            char_count=len(d.text),
            ingestion_run_id=run_id,
        )
        for d in drafts
    )
    document.chunk_count = len(drafts)
    return finish("ingested", None)


def list_documents(
    db: Session, *, status: str | None, limit: int, offset: int
) -> tuple[list[Document], int]:
    query = select(Document)
    if status:
        query = query.where(Document.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Document.id).limit(limit).offset(offset)).all()
    return list(items), total


def list_chunks(
    db: Session, document_id: str, *, limit: int, offset: int
) -> tuple[list[Chunk], int]:
    document = get_document(db, document_id)
    query = select(Chunk).where(Chunk.document_id == document.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Chunk.chunk_index).limit(limit).offset(offset)).all()
    return list(items), total
