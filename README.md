# Zhero

Intelligent Digital Twin & Evidence-Verified AI for Medical Equipment Maintenance.

Zhero is a **software-only** digital twin of an ultrasound machine plus a RAG assistant
that answers from approved technical manuals and verifies its own citations. All twin
readings and faults are **SIMULATED**; Zhero does not connect to real equipment and does
not replace qualified biomedical engineering judgement.

## Status

Phase 0 (setup): backend skeleton with a health endpoint. Equipment, simulator, RAG,
verification and dashboard are not built yet. See the build blueprint for the roadmap.

## Repository layout

```
backend/        FastAPI service (api, core, schemas, services, db, tests)
ai_engine/      RAG pipeline modules (placeholder)
digital_twin/   Simulator and scenarios (placeholder)
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
cp ../.env.example ../.env         # optional; defaults work for the health endpoint
uvicorn app.main:app --reload
```

- Health check: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI docs (development only): <http://127.0.0.1:8000/docs>

## Test and lint

```bash
cd backend
pytest
ruff check . && ruff format --check .
```

CI (`.github/workflows/ci.yml`) runs the same checks on pull requests and pushes to
`main` / `develop`.

## Conventions

- Secrets live in environment variables; only `.env.example` is committed.
- API errors use `{"error": {"code", "message", "request_id"}}`.
- Branch per issue (`feature/...`), pull request into `develop`.
- Consequential technology choices are recorded in `docs/decisions/`.
