# Zhero

Intelligent Digital Twin & Evidence-Verified AI for Medical Equipment Maintenance.

Zhero is a **software-only** digital twin of an ultrasound machine plus a RAG assistant
that answers from approved technical manuals and verifies its own citations. All twin
readings and faults are **SIMULATED**; Zhero does not connect to real equipment and does
not replace qualified biomedical engineering judgement.

## Status

Phase 1-2 (foundation and digital twin) in progress: health endpoint, PostgreSQL schema
with Alembic migrations, the equipment API, and a deterministic simulator with fault
scenarios, reset, readings and event history. Phase 3 (RAG) has started: document upload,
PDF/TXT ingestion with page-level chunks, a BM25 retrieval baseline, and grounded chat answers
(`POST /chat`) using a deterministic mock generator behind an LLM adapter. Answers are
UNVERIFIED: the verification engine, embeddings, a real LLM provider and the dashboard are not
built yet.

## Repository layout

```
backend/        FastAPI service (api, core, schemas, services, db, digital_twin, tests)
ai_engine/      RAG pipeline modules (placeholder)
evaluation/     Datasets and metrics (placeholder)
frontend/web/   Next.js dashboard (placeholder)
docs/           Architecture notes and decision records
```

## Run the backend locally

Requires Python 3.11+ (developed on 3.13).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd .. && docker compose up -d db && cd backend   # local PostgreSQL (pgvector image)
cp ../.env.example .env            # DATABASE_URL must match docker-compose.yml, see below
alembic upgrade head               # create tables
uvicorn app.main:app --reload
```

The compose database uses user/password/db `zhero` / `zhero_local_password` / `zhero`, so set:

```
DATABASE_URL=postgresql+psycopg://zhero:zhero_local_password@localhost:5432/zhero
```

No Docker? For local development you can use SQLite instead:
`DATABASE_URL=sqlite:///./zhero_dev.db` (then `alembic upgrade head`). Use PostgreSQL when you
need to match the final setup.

Without `DATABASE_URL`, the health endpoint reports `database: not_configured` and
database-backed endpoints return `503 database_unavailable`.

- Health check: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI docs (development only): <http://127.0.0.1:8000/docs>

## Test and lint

```bash
cd backend
pytest                                   # in-memory SQLite
TEST_DATABASE_URL=postgresql+psycopg://zhero:zhero_local_password@localhost:5432/zhero pytest   # real Postgres (drops/creates tables: use a scratch DB)
ruff check . && ruff format --check .
```

CI (`.github/workflows/ci.yml`) runs the same checks on pull requests and pushes to
`main` / `develop`.

## Conventions

- Secrets live in environment variables; only `.env.example` is committed.
- Equipment API: `POST/GET /api/v1/equipment`, `GET/PATCH /api/v1/equipment/{id}` (see `/docs`).
- Digital twin API (all data is SIMULATED): `POST /equipment/{id}/simulate`, `/faults`, `/reset`,
  `GET /equipment/{id}/readings`, `/events`. Scenarios: `cooling_degradation`,
  `power_instability`, `component_fault`. Pass `seed` to `simulate` for reproducible values.
- Documents API: `POST /documents` (multipart PDF/TXT upload, max `MAX_UPLOAD_MB`),
  `POST /documents/{id}/ingest` (idempotent), `GET /documents`, `GET /documents/{id}`,
  `GET /documents/{id}/chunks`; `POST /search` returns ranked passages with document, page,
  section and score. Original files are stored under `UPLOAD_DIR` (git-ignored) with generated
  names; uploaded text is treated as untrusted data.
- Chat API: `POST /chat {question, equipment_id?}` retrieves evidence, screens for hazardous
  requests, generates via the adapter selected by `LLM_PROVIDER` (default `mock`, no key needed),
  and returns claims, server-built citations, SIMULATED twin observations and caveats.
  `GET /chat/{chat_id}` re-reads a stored answer. Statuses: `UNVERIFIED`,
  `INSUFFICIENT_INFORMATION`, `BLOCKED_FOR_SAFETY` (never `VERIFIED` yet).
- `docs/equipment_research/PLACEHOLDER_demo_ultrasound_manual.txt` is a SYNTHETIC document for
  testing and demos. It is not a real manual; replace it with a permitted source before real use.
- Simulator thresholds are illustrative assumptions in `backend/app/digital_twin/config.py`,
  not manufacturer limits.
- API errors use `{"error": {"code", "message", "request_id"}}`.
- Branch per issue (`feature/...`), pull request into `develop`.
- Consequential technology choices are recorded in `docs/decisions/`.
