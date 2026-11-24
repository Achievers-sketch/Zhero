"""Document endpoints under /api/v1/documents (upload, ingest, inspect)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.document import (
    ChunkList,
    ChunkRead,
    DocumentList,
    DocumentRead,
    DocumentStatus,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=DocumentRead, status_code=201)
def upload_document(
    db: DbSession,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="PDF or TXT file")],
    title: Annotated[str | None, Form(max_length=200)] = None,
    source_note: Annotated[str | None, Form(max_length=512)] = None,
    publisher: Annotated[str | None, Form(max_length=128)] = None,
    manufacturer: Annotated[str | None, Form(max_length=128)] = None,
    equipment_type: Annotated[str | None, Form(max_length=32)] = "Ultrasound",
    model_applicability: Annotated[str | None, Form(max_length=128)] = None,
    revision: Annotated[str | None, Form(max_length=64)] = None,
) -> DocumentRead:
    """Validate and store a document. Call `/ingest` afterwards to parse and index it."""
    data = document_service.read_limited(file.file, settings.max_upload_mb * 1024 * 1024)
    document = document_service.create_document(
        db,
        settings,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        metadata={
            "title": title,
            "source_note": source_note,
            "publisher": publisher,
            "manufacturer": manufacturer,
            "equipment_type": equipment_type,
            "model_applicability": model_applicability,
            "revision": revision,
        },
    )
    return DocumentRead.model_validate(document)


@router.get("", response_model=DocumentList)
def list_documents(
    db: DbSession,
    status: DocumentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    items, total = document_service.list_documents(db, status=status, limit=limit, offset=offset)
    return DocumentList(
        items=[DocumentRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, db: DbSession) -> DocumentRead:
    """Document status, extraction warnings and chunk count."""
    return DocumentRead.model_validate(document_service.get_document(db, document_id))


@router.post("/{document_id}/ingest", response_model=DocumentRead)
def ingest_document(document_id: str, db: DbSession, settings: AppSettings) -> DocumentRead:
    """Parse, chunk and index a document. Idempotent: an ingested document is returned as is.

    Parse failures are reported through the document's `status` / `status_detail`.
    """
    return DocumentRead.model_validate(document_service.ingest_document(db, settings, document_id))


@router.get("/{document_id}/chunks", response_model=ChunkList)
def list_chunks(
    document_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChunkList:
    """Inspect the traceable chunks (page range, section, text) of a document."""
    items, total = document_service.list_chunks(db, document_id, limit=limit, offset=offset)
    return ChunkList(
        items=[ChunkRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )
