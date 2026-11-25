"""Grounded chat endpoint: cited answers from ingested documents plus simulated twin context."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.llm.base import LLMAdapter
from app.llm.factory import create_llm_adapter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["chat"])


def get_llm(settings: Annotated[Settings, Depends(get_settings)]) -> LLMAdapter:
    return create_llm_adapter(settings)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[LLMAdapter, Depends(get_llm)],
) -> ChatResponse:
    """Answer from retrieved evidence only. Answers are UNVERIFIED until verification exists."""
    return chat_service.answer(db, settings, adapter, payload)


@router.get("/chat/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str, db: Annotated[Session, Depends(get_db)]) -> ChatResponse:
    return chat_service.get_chat(db, chat_id)
