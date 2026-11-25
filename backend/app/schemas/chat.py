"""Chat (grounded answer) API schemas.

``verification_status`` is never VERIFIED here: the independent verification engine does not
exist yet, so generated answers are UNVERIFIED and every claim's support_status is UNVERIFIED.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VerificationStatus = Literal["UNVERIFIED", "INSUFFICIENT_INFORMATION", "BLOCKED_FOR_SAFETY"]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    equipment_id: str | None = Field(default=None, max_length=64)
    top_k: int | None = Field(default=None, ge=1, le=10)


class ClaimRead(BaseModel):
    claim_id: str
    text: str
    evidence_ids: list[str]
    kind: Literal["documented", "simulation_observation", "unknown"]
    support_status: Literal["UNVERIFIED"] = "UNVERIFIED"


class CitationRead(BaseModel):
    evidence_id: str  # chunk ID
    document_id: str
    document_title: str
    revision: str | None
    page_start: int | None
    page_end: int | None
    section: str | None
    excerpt: str


class TwinObservationRead(BaseModel):
    label: str
    detail: str
    simulation: Literal[True] = True


class GeneratorInfo(BaseModel):
    provider: str
    model: str
    is_mock: bool


class ChatResponse(BaseModel):
    chat_id: str
    question: str
    equipment_id: str | None
    answer: str
    verification_status: VerificationStatus
    claims: list[ClaimRead]
    citations: list[CitationRead]
    twin_context_used: bool
    twin_observations: list[TwinObservationRead]
    caveats: list[str]
    next_information_needed: list[str]
    abstention_reason: str | None
    retrieval_query: str
    retrieved_chunk_ids: list[str]
    generator: GeneratorInfo | None
    created_at: datetime
