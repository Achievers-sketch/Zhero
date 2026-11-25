"""Stage 5 (RETRIEVE): ranked, filterable passages with full provenance.

Baseline: BM25 over chunks of ingested documents, rebuilt per query (fine for the MVP's
small corpus; revisit with a persistent index or pgvector hybrid search when it grows).
Retrieved text is untrusted data and must never be treated as instructions downstream.
"""

import logging
import time
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document
from app.rag.bm25 import BM25Index, make_excerpt, tokenize
from app.schemas.document import SearchHit
from app.services.document_service import parse_document_id

logger = logging.getLogger("zhero.retrieval")


@dataclass(frozen=True)
class RankedChunk:
    rank: int
    score: float
    chunk: Chunk
    document: Document


def rank_chunks(
    db: Session,
    *,
    query: str,
    top_k: int,
    document_id: str | None = None,
    equipment_type: str | None = None,
    model_applicability: str | None = None,
    include_untyped: bool = False,
) -> tuple[list[RankedChunk], int]:
    """Return ``(ranked chunks, candidate count)``. ``include_untyped`` also matches documents
    whose equipment_type is unset (used by chat, where a general manual may still apply)."""
    started = time.perf_counter()
    statement = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ingested")
    )
    if document_id:
        statement = statement.where(Document.id == parse_document_id(document_id))
    if equipment_type:
        condition = Document.equipment_type == equipment_type
        if include_untyped:
            condition = or_(condition, Document.equipment_type.is_(None))
        statement = statement.where(condition)
    if model_applicability:
        statement = statement.where(
            Document.model_applicability.icontains(model_applicability, autoescape=True)
        )
    rows = db.execute(statement.order_by(Chunk.document_id, Chunk.chunk_index)).all()

    query_tokens = tokenize(query)
    ranked_rows: list[RankedChunk] = []
    if rows and query_tokens:
        index = BM25Index([tokenize(f"{c.section or ''}\n{c.text}") for c, _ in rows])
        scores = index.score(query_tokens)
        order = sorted(
            (i for i, score in enumerate(scores) if score > 0),
            key=lambda i: (-scores[i], rows[i][0].id),
        )[:top_k]
        ranked_rows = [
            RankedChunk(rank, round(scores[i], 4), rows[i][0], rows[i][1])
            for rank, i in enumerate(order, start=1)
        ]

    # Log IDs and scores only (no query text) so weak retrieval can be diagnosed safely.
    logger.info(
        "retrieval",
        extra={
            "query_chars": len(query),
            "candidates": len(rows),
            "returned": [(f"CHK-{r.chunk.id:06d}", r.score) for r in ranked_rows],
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return ranked_rows, len(rows)


def search(
    db: Session,
    *,
    query: str,
    top_k: int,
    document_id: str | None = None,
    equipment_type: str | None = None,
    model_applicability: str | None = None,
) -> list[SearchHit]:
    ranked, _ = rank_chunks(
        db,
        query=query,
        top_k=top_k,
        document_id=document_id,
        equipment_type=equipment_type,
        model_applicability=model_applicability,
    )
    query_tokens = tokenize(query)
    return [
        SearchHit(
            rank=r.rank,
            score=r.score,
            chunk_id=f"CHK-{r.chunk.id:06d}",
            document_id=f"DOC-{r.document.id:04d}",
            document_title=r.document.title,
            revision=r.document.revision,
            page_start=r.chunk.page_start,
            page_end=r.chunk.page_end,
            section=r.chunk.section,
            excerpt=make_excerpt(r.chunk.text, query_tokens),
        )
        for r in ranked
    ]
