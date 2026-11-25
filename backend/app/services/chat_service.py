"""Stage 6 (ANSWER): grounded chat answers with server-built citations.

Pipeline: safety pre-screen -> twin context -> retrieval -> generation (adapter) ->
guardrails (evidence-ID validation, output safety screen) -> stored response.
The model never creates citations; the server builds them from retrieved chunk metadata.
Answers are UNVERIFIED until the independent verification engine exists.
"""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.llm.base import EvidenceItem, GenerationRequest, LLMAdapter
from app.models.chat import ChatRecord
from app.models.equipment import Equipment
from app.rag import safety
from app.rag.bm25 import make_excerpt, tokenize
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.equipment_service import get_equipment
from app.services.retrieval_service import RankedChunk, rank_chunks
from app.services.twin_context import TwinContext, build_twin_context

logger = logging.getLogger("zhero.chat")

BASE_CAVEATS = [
    "Informational support only. A qualified person is responsible for every maintenance decision.",
    "Digital-twin values are SIMULATED and are not real telemetry.",
]
UNVERIFIED_CAVEAT = "This answer has not yet been independently verified against the sources."
INSUFFICIENT_MESSAGE = (
    "I could not find enough evidence in the uploaded documents to answer this. I will not guess."
)


def _chunk_id(chunk_id: int) -> str:
    return f"CHK-{chunk_id:06d}"


def _evidence(ranked: list[RankedChunk]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            evidence_id=_chunk_id(r.chunk.id),
            document_id=f"DOC-{r.document.id:04d}",
            document_title=r.document.title,
            revision=r.document.revision,
            page_start=r.chunk.page_start,
            page_end=r.chunk.page_end,
            section=r.chunk.section,
            text=r.chunk.text,
        )
        for r in ranked
    ]


def _store(db: Session, payload: ChatRequest, body: dict) -> ChatResponse:
    record = ChatRecord(
        question=payload.question,
        equipment_id=payload.equipment_id,
        verification_status=body["verification_status"],
        response={},
    )
    db.add(record)
    db.flush()
    body = {**body, "chat_id": f"CHAT-{record.id:04d}", "created_at": datetime.now(UTC)}
    response = ChatResponse.model_validate(body)
    record.response = response.model_dump(mode="json")
    db.commit()
    return response


def _base_body(payload: ChatRequest, query: str, twin: TwinContext | None) -> dict:
    return {
        "question": payload.question,
        "equipment_id": payload.equipment_id,
        "answer": "",
        "verification_status": "INSUFFICIENT_INFORMATION",
        "claims": [],
        "citations": [],
        "twin_context_used": twin is not None,
        "twin_observations": [
            {"label": o.label, "detail": o.detail} for o in (twin.observations if twin else [])
        ],
        "caveats": list(BASE_CAVEATS),
        "next_information_needed": [],
        "abstention_reason": None,
        "retrieval_query": query,
        "retrieved_chunk_ids": [],
        "generator": None,
    }


def answer(
    db: Session, settings: Settings, adapter: LLMAdapter, payload: ChatRequest
) -> ChatResponse:
    started = time.perf_counter()
    payload = payload.model_copy(update={"question": payload.question.strip()})
    question = payload.question
    if not question:
        raise AppError(422, "validation_error", "Question must not be blank.")

    equipment: Equipment | None = None
    twin: TwinContext | None = None
    if payload.equipment_id:
        equipment = get_equipment(db, payload.equipment_id)  # 404 if unknown
        twin = build_twin_context(db, equipment)

    query = (
        f"{question} {twin.retrieval_hint}".strip() if twin and twin.retrieval_hint else question
    )
    body = _base_body(payload, query, twin)

    # 1. Safety pre-screen: hazardous requests never reach retrieval or the model.
    screened = safety.screen(question)
    if screened.blocked:
        body.update(
            verification_status="BLOCKED_FOR_SAFETY",
            answer=safety.SAFE_ALTERNATIVE,
            abstention_reason=f"Blocked by safety screen ({screened.reason}).",
        )
        _log(started, "blocked_pre", 0, 0)
        return _store(db, payload, body)

    # 2. Retrieval.
    ranked, _ = rank_chunks(
        db,
        query=query,
        top_k=payload.top_k or settings.rag_top_k,
        equipment_type=equipment.equipment_type if equipment else None,
        include_untyped=True,
    )
    body["retrieved_chunk_ids"] = [_chunk_id(r.chunk.id) for r in ranked]
    if not ranked:
        body.update(
            answer=INSUFFICIENT_MESSAGE,
            abstention_reason="No relevant passages were found in the ingested documents.",
            next_information_needed=["Upload a document that covers this topic."],
        )
        _log(started, "no_evidence", 0, 0)
        return _store(db, payload, body)

    # 3. Generation.
    evidence = _evidence(ranked)
    request = GenerationRequest(
        question=question,
        evidence=evidence,
        twin_observations=list(twin.observations) if twin else [],
    )
    try:
        result = adapter.generate(request)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - provider failures must not leak details
        logger.error("llm_error", extra={"error_type": type(exc).__name__})
        raise AppError(502, "llm_error", "The answer generator failed. Please try again.") from exc

    body["generator"] = {
        "provider": adapter.provider,
        "model": adapter.model,
        "is_mock": adapter.provider == "mock",
    }

    # 4. Guardrails: only claims backed by retrieved evidence survive.
    valid_ids = {e.evidence_id for e in evidence}
    kept = []
    dropped = 0
    for claim in result.claims:
        ids = [i for i in dict.fromkeys(claim.evidence_ids) if i in valid_ids]
        if claim.kind == "documented":
            if not ids:
                dropped += 1
                continue
        elif claim.kind == "simulation_observation":
            if twin is None:
                dropped += 1
                continue
            ids = []
        else:
            ids = []
        kept.append((claim, ids))

    documented = [k for k in kept if k[0].kind == "documented"]
    if result.abstain or not documented:
        body.update(
            answer=INSUFFICIENT_MESSAGE,
            abstention_reason=result.abstention_reason
            or "No claim could be tied to the retrieved evidence.",
            next_information_needed=result.next_information_needed
            or ["A document section that directly addresses the question."],
            caveats=BASE_CAVEATS + _generator_caveats(adapter, result.caveats),
        )
        if dropped:
            body["caveats"].append(f"{dropped} unsupported claim(s) were discarded.")
        _log(started, "insufficient", len(ranked), dropped)
        return _store(db, payload, body)

    # 5. Output safety screen.
    texts = [result.answer, *[c.text for c, _ in kept]]
    out = next((r for r in map(safety.screen, texts) if r.blocked), None)
    if out:
        body.update(
            verification_status="BLOCKED_FOR_SAFETY",
            answer=safety.SAFE_ALTERNATIVE,
            abstention_reason=f"Generated text blocked by safety screen ({out.reason}).",
        )
        _log(started, "blocked_post", len(ranked), dropped)
        return _store(db, payload, body)

    # 6. Server-built citations from retrieved chunk metadata only.
    by_id = {_chunk_id(r.chunk.id): r for r in ranked}
    tokens = tokenize(query)
    used: list[str] = list(dict.fromkeys(i for _, ids in kept for i in ids))
    citations = []
    for cid in used:
        r = by_id[cid]
        citations.append(
            {
                "evidence_id": cid,
                "document_id": f"DOC-{r.document.id:04d}",
                "document_title": r.document.title,
                "revision": r.document.revision,
                "page_start": r.chunk.page_start,
                "page_end": r.chunk.page_end,
                "section": r.chunk.section,
                "excerpt": make_excerpt(r.chunk.text, tokens),
            }
        )

    caveats = BASE_CAVEATS + [UNVERIFIED_CAVEAT] + _generator_caveats(adapter, result.caveats)
    cited_docs = {by_id[i].document.id: by_id[i].document for i in used}
    revisions = {d.revision for d in cited_docs.values() if d.revision}
    if len(cited_docs) > 1 and len(revisions) > 1:
        caveats.append("Cited documents have different revisions; check which applies.")
    if equipment and equipment.model:
        model = equipment.model.lower()
        if any(
            not d.model_applicability or model not in d.model_applicability.lower()
            for d in cited_docs.values()
        ):
            caveats.append(
                "Applicability of the cited document(s) to this equipment model is not confirmed."
            )
    if dropped:
        caveats.append(f"{dropped} unsupported claim(s) were discarded.")

    body.update(
        answer=result.answer,
        verification_status="UNVERIFIED",
        claims=[
            {
                "claim_id": f"C{n}",
                "text": claim.text,
                "evidence_ids": ids,
                "kind": claim.kind,
            }
            for n, (claim, ids) in enumerate(kept, start=1)
        ],
        citations=citations,
        caveats=caveats,
        next_information_needed=result.next_information_needed,
    )
    _log(started, "answered", len(ranked), dropped)
    return _store(db, payload, body)


def _generator_caveats(adapter: LLMAdapter, extra: list[str]) -> list[str]:
    notes = list(extra)
    if adapter.provider == "mock" and not notes:
        notes.append("Produced by a mock extractive generator, not a real language model.")
    return notes


def _log(started: float, outcome: str, retrieved: int, dropped: int) -> None:
    # IDs, counts and timings only: never question or answer text.
    logger.info(
        "chat",
        extra={
            "outcome": outcome,
            "retrieved": retrieved,
            "dropped_claims": dropped,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )


def get_chat(db: Session, chat_id: str) -> ChatResponse:
    prefix, _, number = chat_id.partition("-")
    if prefix != "CHAT" or not number.isdigit():
        raise NotFoundError(f"Chat '{chat_id}' not found.")
    record = db.get(ChatRecord, int(number))
    if record is None:
        raise NotFoundError(f"Chat '{chat_id}' not found.")
    return ChatResponse.model_validate(record.response)
