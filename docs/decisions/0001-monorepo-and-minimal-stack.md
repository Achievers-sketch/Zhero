# ADR 0001: Monorepo and minimal starting stack

- Status: accepted
- Date: 2026-11-24

## Context

The blueprint recommends a FastAPI backend, PostgreSQL + pgvector, and a
Next.js dashboard, and warns against extra infrastructure (Redis, Kubernetes,
multiple agents) without a measured need.

## Decision

- One monorepo with `backend/`, `frontend/web/`, `ai_engine/`, `digital_twin/`,
  `evaluation/`, `docs/`. Only `backend/` has code so far; the others are
  placeholders for later phases.
- Backend: Python + FastAPI + pydantic-settings. No database or AI dependency
  yet; those arrive with the milestones that need them (Sprint 1 day 4 for the
  database).
- Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`.
- `/api/v1/health` reports `database: "not_configured"` until a database is
  connected, so it never claims a health it has not checked.
- OpenAPI docs are served only when `APP_ENV=development`.

## Open decisions (from blueprint section 17)

Reference equipment model, permitted manual, LLM provider, embedding location,
pgvector hosting, upload limits and the hackathon deadline are still undecided.
