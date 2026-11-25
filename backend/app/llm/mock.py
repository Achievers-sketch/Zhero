"""Deterministic extractive "model" for development, tests and demos (no API key needed).

It does not understand language: it picks the sentences of the retrieved passages that best
match the question and returns them verbatim, each attributed to the passage it came from.
That makes it safe by construction (it cannot invent facts) and lets the whole pipeline be
exercised end to end. Swap in a real provider via the adapter factory.
"""

import re

from app.llm.base import GeneratedClaim, GenerationRequest, GenerationResult
from app.rag.bm25 import tokenize

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n\s*\n")
MAX_CLAIMS = 5
MAX_PER_PASSAGE = 2
MIN_SENTENCE_CHARS = 15
_TWIN_LABELS = {
    "Equipment status",
    "Active simulated scenario",
    "Simulated reading outside demo band",
}


def _is_whole_sentence(sentence: str) -> bool:
    return sentence[0].isupper() or sentence[0].isdigit()


class MockExtractiveAdapter:
    provider = "mock"
    model = "mock-extractive-v1"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        wanted = set(tokenize(request.question))
        claims: list[GeneratedClaim] = []
        seen: set[str] = set()

        for item in request.evidence:
            # Re-join hard-wrapped lines, then keep only whole sentences: chunk boundaries can
            # cut a sentence in half, and a fragment must never be quoted as a claim.
            sentences = [
                " ".join(s.split())
                for s in _SENTENCE_SPLIT.split(item.text)
                if len(s.strip()) >= MIN_SENTENCE_CHARS
            ]
            sentences = [s for s in sentences if _is_whole_sentence(s)]
            scored = sorted(
                ((len(wanted & set(tokenize(s))), index, s) for index, s in enumerate(sentences)),
                key=lambda t: (-t[0], t[1]),
            )
            taken = 0
            for score, _, sentence in scored:
                key = " ".join(sentence.lower().split())
                if score == 0 or key in seen:
                    continue
                seen.add(key)
                claims.append(GeneratedClaim(sentence, [item.evidence_id], "documented"))
                taken += 1
                if taken >= MAX_PER_PASSAGE or len(claims) >= MAX_CLAIMS:
                    break
            if len(claims) >= MAX_CLAIMS:
                break

        if not claims:
            return GenerationResult(
                answer="",
                claims=[],
                abstain=True,
                abstention_reason=(
                    "The retrieved passages did not contain a sentence that answers the question."
                ),
                next_information_needed=[
                    "A document section that directly addresses the question."
                ],
            )

        answer = "Based on the retrieved documents: " + " ".join(c.text for c in claims)
        twin = [o for o in request.twin_observations if o.label in _TWIN_LABELS]
        if twin:
            answer += " Simulation context (SIMULATED data, not real telemetry): " + "; ".join(
                o.detail for o in twin
            )
        return GenerationResult(
            answer=answer,
            claims=claims,
            caveats=[
                "This answer was produced by a mock extractive generator (no real language "
                "model): it quotes matching sentences from the retrieved passages."
            ],
        )
