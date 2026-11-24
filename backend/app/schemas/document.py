"""Document, chunk and search schemas."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

DocumentStatus = Literal["uploaded", "ingested", "empty", "failed"]
DocumentIdStr = Annotated[str, Field(pattern=r"^DOC-\d{1,9}$")]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(exclude=True)
    title: str
    original_filename: str
    file_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    status_detail: str | None
    warnings: list[str]
    page_count: int | None
    chunk_count: int
    source_note: str | None
    publisher: str | None
    manufacturer: str | None
    equipment_type: str | None
    model_applicability: str | None
    revision: str | None
    uploaded_at: datetime
    ingested_at: datetime | None
    parser_version: str | None
    ingestion_run_id: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def document_id(self) -> str:
        return f"DOC-{self.id:04d}"


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(exclude=True)
    document_id_num: int = Field(exclude=True, validation_alias="document_id")
    chunk_index: int
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str
    char_count: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chunk_id(self) -> str:
        return f"CHK-{self.id:06d}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def document_id(self) -> str:
        return f"DOC-{self.document_id_num:04d}"


class ChunkList(BaseModel):
    items: list[ChunkRead]
    total: int
    limit: int
    offset: int


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=20)
    document_id: DocumentIdStr | None = None
    equipment_type: str | None = Field(default=None, max_length=32)
    model_applicability: str | None = Field(default=None, max_length=128)


class SearchHit(BaseModel):
    rank: int
    score: float
    chunk_id: str
    document_id: str
    document_title: str
    revision: str | None
    page_start: int | None
    page_end: int | None
    section: str | None
    excerpt: str


class SearchResponse(BaseModel):
    query: str
    retrieval_method: Literal["bm25"] = "bm25"
    hits: list[SearchHit]
