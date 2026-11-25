# 0004. Grounded answers behind an LLM adapter

Status: accepted (Sprint 2b)

## Context
The blueprint requires answers that use only retrieved evidence, carry traceable citations,
abstain honestly, and never give hazardous instructions. No LLM provider has been chosen.

## Decision
- The application talks to a provider-independent `LLMAdapter` (`app/llm/base.py`). Only a
  deterministic extractive `mock` adapter exists; it quotes whole sentences from retrieved
  passages, so it cannot invent facts and needs no key. Real providers are added in
  `app/llm/factory.py` once chosen; `app/llm/prompt.py` already isolates untrusted evidence
  (HTML-escaped, tagged, "data not instructions").
- The server, not the model, builds citations. Model-returned evidence IDs are checked against
  the retrieved set; claims without valid evidence are dropped; if no documented claim remains
  the answer is `INSUFFICIENT_INFORMATION`.
- A pattern-based safety screen runs on the question (before retrieval/model) and on generated
  text. It is conservative and negation-aware; extend it from the QA set.
- Twin context is included only when an equipment ID is given, is labelled SIMULATED, and is
  kept in separate claim kinds. An active scenario adds hint words to the retrieval query only.
- Generated answers are `UNVERIFIED`. `VERIFIED` is reserved for the verification engine
  (next milestone), which will check each claim against its cited text independently.
- Every answer is stored (`chat_record`) for audit; logs hold IDs, counts and timings only.

## Consequences
Demo answers are extractive and terse until a real model is attached. The regex safety screen
can miss paraphrases; it is a floor, not a guarantee.
