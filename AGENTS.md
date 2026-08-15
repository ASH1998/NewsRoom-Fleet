# AGENTS.md — Newsroom Fleet

Newsroom Fleet is an institutional multi-agent verification system for local newsrooms
(Fortified Enterprise Fleet, All Things Agentic Hackathon). The source of truth for
product intent is `Newsroom-Fleet-Winning-Design-Report.md` (same content as the PDF).

## Hard constraints

- **Everything installs inside this repo dir.** No global pip/npm installs.
- Python: **uv + pyproject**. The uv project lives in `backend/` (`backend/pyproject.toml`,
  `backend/.venv`). Use `uv sync` / `uv run` from `backend/`, never `pip install`.
- Frontend: **node** (Vite + React + TS + Tailwind) in `frontend/`. Deps stay in
  `frontend/node_modules`. Use `npm` (no global packages).
- Google Cloud (ADK/Gemini, Firestore, Pub/Sub, Model Armor, Gemma, Memory Bank,
  Cloud Run, Cloud Scheduler, Cloud Trace) is **implemented behind interfaces**, each
  as an independent switch in `config.py`. Cloud deps live in the `cloud` optional
  extra and are imported lazily; fixture mode must keep working with the extra absent.
  **Do not add GCP SDK calls outside those interface implementations** — constructing
  a cloud component happens in `bootstrap.py` and nowhere else, and every one must
  degrade to its local implementation with a logged warning rather than fail startup.

## Architecture invariant

The publication decision is a **deterministic policy evaluation over persisted verdict
state** — never a free-form model recommendation. Missing evidence, disagreement,
quarantine, low confidence, or worker failure can never become `VERIFIED`.
See the state machine and canonical decision rules in the design report appendix.

## Structure

- `backend/src/newsroom_fleet/` — Python package
  - `config.py` — component switches (mode/repository/screener/queue/memory/tracing/pii)
  - `bootstrap.py` — the only place cloud components are constructed
  - `domain/` — contracts, publication state machine, editor-gate policy, Masthead
    registry, deterministic claim→desk routing table
  - `desks/` — specialist desks with enforced evidence boundaries; `desks/live/` holds
    the ADK/Gemini implementations of the same protocols
  - `orchestration/` — policy router, async runner (timeout/retry/idempotency),
    review queue protocol + Pub/Sub implementation, the FleetService pipeline
  - `persistence/` — repository protocol, SQLite and Firestore impls, audit events
  - `security/` — intake screening (heuristic + Model Armor), Gemma PII pass
  - `adapters/` — authoritative data adapters (deterministic fixtures)
  - `memory/` — approved standards + corrections precedents (file / Memory Bank)
  - `observability/` — OpenTelemetry spans; no-op when tracing is off
  - `evaluation/` — curated suite + scored metric harness
  - `api/` — FastAPI app and routes
  - `fixtures/` — golden demo article + authoritative fixture data + house rules
- `backend/tests/` — pytest
- `frontend/` — Vite + React + TS + Tailwind editor UI
- `deploy/` — Google Cloud provisioning (`setup_gcp.sh`) and deployment (`deploy.sh`)

## Commands

- Backend install: `cd backend && uv sync` (add `--extra cloud` for the Google stack)
- Backend dev server: `cd backend && uv run uvicorn newsroom_fleet.api.app:app --reload`
- Backend tests: `cd backend && uv run pytest`
- Scored evaluation: `cd backend && uv run python -m newsroom_fleet.evaluation`
- Lint/format: `cd backend && uv run ruff check . && uv run ruff format .`
- Frontend install: `cd frontend && npm install`
- Frontend dev: `cd frontend && npm run dev`
- Deploy: `PROJECT_ID=… REGION=… ./deploy/setup_gcp.sh` then `./deploy/deploy.sh`

## Conventions

- Pydantic v2 models for all agent output contracts; versioned schema names.
- Every verdict carries `agent_version`, evidence locators, and retrieval metadata.
- Audit events are append-only; policy denies — it never mutates verdicts.
- Routing, aggregation, and the gate are deterministic code. A model may classify or
  judge evidence; it may never decide which desks review a claim or whether to publish.
- A live desk's citation must resolve against the evidence it was handed, or the verdict
  is downgraded. Never let an unvalidated locator support a verification.
- Keep it simple: fixture mode must run with zero API keys, zero network, zero cloud.
