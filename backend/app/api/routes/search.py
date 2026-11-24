"""Retrieval endpoint: ranked source passages with page and section provenance."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.document import SearchRequest, SearchResponse
from app.services import retrieval_service

router = APIRouter(tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    """Retrieve the most relevant passages from ingested documents (BM25 baseline).

    An empty `hits` list means no relevant evidence was found; callers must not invent any.
    """
    hits = retrieval_service.search(
        db,
        query=payload.query.strip(),
        top_k=payload.top_k or settings.rag_top_k,
        document_id=payload.document_id,
        equipment_type=payload.equipment_type,
        model_applicability=payload.model_applicability,
    )
    return SearchResponse(query=payload.query.strip(), hits=hits)
