"""Stage 5 (RETRIEVE): ranked, filterable passages with full provenance.

Baseline: BM25 over chunks of ingested documents, rebuilt per query (fine for the MVP's
small corpus; revisit with a persistent index or pgvector hybrid search when it grows).
Retrieved text is untrusted data and must never be treated as instructions downstream.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document
from app.rag.bm25 import BM25Index, make_excerpt, tokenize
from app.schemas.document import SearchHit
from app.services.document_service import parse_document_id

logger = logging.getLogger("zhero.retrieval")


def search(
    db: Session,
    *,
    query: str,
    top_k: int,
    document_id: str | None = None,
    equipment_type: str | None = None,
    model_applicability: str | None = None,
) -> list[SearchHit]:
    started = time.perf_counter()
    statement = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ingested")
    )
    if document_id:
        statement = statement.where(Document.id == parse_document_id(document_id))
    if equipment_type:
        statement = statement.where(Document.equipment_type == equipment_type)
    if model_applicability:
        statement = statement.where(
            Document.model_applicability.icontains(model_applicability, autoescape=True)
        )
    rows = db.execute(statement.order_by(Chunk.document_id, Chunk.chunk_index)).all()

    query_tokens = tokenize(query)
    hits: list[SearchHit] = []
    if rows and query_tokens:
        index = BM25Index([tokenize(f"{c.section or ''}\n{c.text}") for c, _ in rows])
        scores = index.score(query_tokens)
        ranked = sorted(
            (i for i, score in enumerate(scores) if score > 0),
            key=lambda i: (-scores[i], rows[i][0].id),
        )[:top_k]
        for rank, i in enumerate(ranked, start=1):
            chunk, document = rows[i]
            hits.append(
                SearchHit(
                    rank=rank,
                    score=round(scores[i], 4),
                    chunk_id=f"CHK-{chunk.id:06d}",
                    document_id=f"DOC-{document.id:04d}",
                    document_title=document.title,
                    revision=document.revision,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section=chunk.section,
                    excerpt=make_excerpt(chunk.text, query_tokens),
                )
            )

    # Log IDs and scores only (no query text) so weak retrieval can be diagnosed safely.
    logger.info(
        "retrieval",
        extra={
            "query_chars": len(query),
            "candidates": len(rows),
            "returned": [(h.chunk_id, h.score) for h in hits],
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return hits
