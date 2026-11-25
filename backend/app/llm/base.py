"""Provider-independent contract between the application and an answer generator.

The application builds ``GenerationRequest`` objects, adapters return ``GenerationResult``.
Adapters never see database objects and never decide citations: the server validates every
evidence ID a model returns and builds citation metadata itself.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

ClaimKind = Literal["documented", "simulation_observation", "unknown"]


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str  # e.g. CHK-000007
    document_id: str
    document_title: str
    revision: str | None
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str  # UNTRUSTED document text


@dataclass(frozen=True)
class TwinObservation:
    label: str
    detail: str  # always describes SIMULATED values


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    evidence: list[EvidenceItem]
    twin_observations: list[TwinObservation] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedClaim:
    text: str
    evidence_ids: list[str]
    kind: ClaimKind = "documented"


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    claims: list[GeneratedClaim]
    caveats: list[str] = field(default_factory=list)
    next_information_needed: list[str] = field(default_factory=list)
    abstain: bool = False
    abstention_reason: str | None = None


class LLMAdapter(Protocol):
    provider: str
    model: str

    def generate(self, request: GenerationRequest) -> GenerationResult: ...
