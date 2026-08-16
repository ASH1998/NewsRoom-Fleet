# Newsroom Fleet

**Newsroom Fleet gives a five-person local newsroom the institutional checks of a national masthead.**

Independent editorial agents reconstruct the missing verification, standards, security, and
corrections functions of a large newsroom — while final judgment stays human and every
decision stays auditable. It is an enforced publication-control system, not a generic
fact-checker: a draft is decomposed into claims, bounded evidence is routed to specialist
desks, unresolved or unsafe claims block publication, approval is reserved for an editor,
and published cases resume when authoritative data changes.

> **Invariant:** missing evidence, disagreement, quarantine, low confidence, or worker
> failure can never become `VERIFIED`. The publication decision is a deterministic policy
> evaluation over persisted verdict state — never a free-form model recommendation.

**Live:** [editor desk](https://newsroom-fleet-desk-6dz7i3zaja-el.a.run.app) ·
[API](https://newsroom-fleet-api-6dz7i3zaja-el.a.run.app/docs) ·
[what's actually serving](https://newsroom-fleet-api-6dz7i3zaja-el.a.run.app/api/runtime)

Running on Cloud Run in `asia-south1` with Firestore, Pub/Sub, and Cloud Trace. Both
services scale to zero, so the first request after an idle period takes a few seconds.

- `ARCHITECTURE.md` — every model, agent, Google service, trust boundary, and persisted record
- `deploy/CLOUD_LEDGER.md` — every cloud action taken, with its cost
- `Newsroom-Fleet-Winning-Design-Report.md` — the design report this is built against

## One-minute proof

```bash
cd backend && uv sync && uv run python -m newsroom_fleet.evaluation
```

No API keys, no network, no cloud. It runs the curated suite and prints a scored
report — the number that matters is **unsafe false verifications: 0**.

| Metric | What it measures |
| --- | --- |
| extraction coverage / claim typing | Labelled claims the extractor produced, and typed correctly |
| verdict accuracy | Desk verdicts matching explicit ground truth |
| evidence correctness | The cited locator really points at the evidence that settles the claim |
| **unsafe false verification** | High-risk claims verified that should have blocked. **Target: 0** |
| abstention quality | Missing or out-of-scope evidence produces abstention, not a guess |
| publish gate integrity | The gate refuses under failure, disagreement, reporter identity, and unresolved approval |
| injection quarantine / false positives | Hostile sources quarantined; benign sources left alone |
| quarantine containment | No verdict cites a quarantined source |
| recovery | Duplicate delivery is idempotent; a healed desk replaces its `ERROR` verdict |

## Architecture

```
submit ──▶ Gateway + screening ──▶ Claim Extractor ──▶ Policy router
              │ quarantine              │ atomic claims      │ minimum evidence per desk
              ▼                         ▼                    ▼
        SecurityResult            Claim records      Source Verifier │ Data Checker │ Standards Reviewer
                                                            │ signed structured verdicts
                                                            ▼
                                              Verdict Aggregator (verdict matrix)
                                                            ▼
                                              Editor Gate (deterministic policy)
                                                            ▼
                                     editor decision → PUBLISHED → Corrections Watcher

        across all stages: persistence (SQLite / Firestore), memory (approved
        standards + precedents), append-only audit trail, OpenTelemetry spans
```

Enterprise pillars map to newsroom terms: agent registry → **Masthead**, policy
enforcement → **Editor Gate**, persistent memory → **Corrections Ledger**,
observability → **Article Audit Trail**.

Every cloud-bound capability sits behind an interface with a local implementation,
and each is an **independent switch**. The recorded demo runs deterministic desks on
real Firestore, Pub/Sub, Model Armor, and Cloud Trace; the same deployment reviews a
fresh article with ADK agents on Gemini by flipping one variable.

| Interface | Local (default) | Google Cloud | Switch |
| --- | --- | --- | --- |
| Desks | fixture (deterministic) | ADK + Gemini 2.5 Flash | `NRF_MODE=live` |
| `Repository` | SQLite | Firestore | `NRF_REPOSITORY=firestore` |
| `ReviewQueue` | asyncio | Pub/Sub + push worker | `NRF_QUEUE=pubsub` |
| `Screener` | heuristic detector | Model Armor | `NRF_SCREENER=model_armor` |
| PII pass | off | Gemma 3 | `NRF_PII=gemma` |
| `MemoryStore` | JSON file | Vertex AI Memory Bank | `NRF_MEMORY=memory_bank` |
| Tracing | off | Cloud Trace | `NRF_TRACING=cloud` |
| Claim pacing | one claim at a time | N concurrent claims | `NRF_REVIEW_CONCURRENCY=N` |

`NRF_PRESET=cloud` sets all of them at once. `GET /api/runtime` reports what was
*actually* constructed, so a component that fell back to its local implementation
is never advertised as running on Google Cloud.

## Repo layout

- `backend/` — Python (uv project): domain contracts, desks, orchestration, persistence,
  screening, FastAPI service, fixtures, evaluation harness, tests
- `frontend/` — Vite + React + TS + Tailwind editor UI
- `deploy/` — Google Cloud provisioning and deployment scripts

## Quickstart

Everything installs inside this directory. No global installs.

```powershell
# Backend (Python 3.13, uv)
cd backend
uv sync
uv run pytest                                        # golden-path + safety tests
uv run python -m newsroom_fleet.evaluation           # scored evaluation report
uv run uvicorn newsroom_fleet.api.app:app --reload   # http://127.0.0.1:8000/docs

# Frontend (node)
cd frontend
npm install
npm run dev                                          # http://127.0.0.1:5173
```

Open the editor desk, press **Load golden article**, and the nine-step demo below runs
against the local fleet. **Submit a draft** puts your own article through the same
pipeline — the fixture is one input, not the path.

## Reproducing the golden article

The planted article contains an incorrect public statistic, a source-mismatched quote,
charged-described-as-guilty wording, a leaked memo carrying indirect prompt injection,
and (later) an upstream value change.

| Planted condition | Expected system behavior |
| --- | --- |
| Incorrect public statistic (4.2 vs 4.9) | Data Checker contradicts with an authoritative locator |
| Misquoted statement | Source Verifier marks unsupported |
| Charged described as guilty | Standards Reviewer raises a high-risk wording flag |
| Prompt injection in leaked memo | Screening quarantines the source before any desk sees it |
| Worker failure | Claim becomes `NEEDS_HUMAN` while other work completes |
| Upstream value changes | Watcher drafts a correction candidate (never auto-corrects) |

Demo choreography, all reproducible in the UI:

1. Submit the golden article → memo quarantined at intake → 5 claims → 11 verdicts → `human review`.
2. As **reporter**, attempt publish → **403**: *"role 'reporter' has no publish authority"* and
   *"4 claim(s) unresolved and no editor decision recorded"*.
3. Crash a desk (top bar) and reload → that claim becomes an `ERROR` verdict / `NEEDS_HUMAN`
   while every other desk finishes. Clear the failure → **Re-review** replaces it with a real verdict.
4. Open the memo in the draft panel → its hidden instruction, the quarantine decision, and its
   absence from every reviewer's evidence.
5. As **editor**, resolve the blocking verdicts with a safe revision → publish succeeds →
   `published`, numeric claims snapshotted.
6. **Advance data** → run the watcher → a material correction candidate (4.9 → 5.1) in house
   style → accept → the correction is appended, never rewriting the story.

## Deploying to Google Cloud

Both scripts are **dry-run by default** — they print exactly what they would create and
change nothing until you pass `APPLY=1`.

```bash
./deploy/setup_gcp.sh                      # show what would be provisioned
TIER=AB APPLY=1 ./deploy/setup_gcp.sh      # APIs, registry, Pub/Sub, service accounts, secret
APPLY=1 WIRE_ASYNC=1 ./deploy/deploy.sh    # build, deploy, push subscription, scheduler
./deploy/audit_cloud.sh                    # read-only inventory of what exists
```

Provisioning is tiered so cost is opt-in: **A** is the build and deploy surface, **B**
adds Pub/Sub, Cloud Scheduler and Secret Manager, **C** adds Model Armor. Cloud Run
defaults to `--min-instances=0`; a warm instance costs far more than the cold start is
worth outside a recording session.

`PROJECT_ID` and the model IDs are read from `.env` (gitignored). Add `MODE=live` to
`deploy.sh` for ADK/Gemini desks, or `NRF_MEMORY_BANK_ENGINE=projects/…/reasoningEngines/…`
to back memory with Vertex AI Memory Bank.

Every action taken against Google Cloud — including read-only checks — is recorded with
its cost in [`deploy/CLOUD_LEDGER.md`](deploy/CLOUD_LEDGER.md).

## Security & limitations

**Controls**

- Intake screening (Model Armor, or a local heuristic detector) runs on the draft body and
  every source **before** orchestration. A quarantined source's content is dropped at the
  router — reviewers receive only its screening metadata, so an injected instruction never
  enters a reviewer's context.
- A live desk may only cite a locator it was given. An unrecognised locator rejects the
  citation and downgrades the verdict, so a hallucinated citation cannot support a
  verification.
- Least privilege: the backend service account holds Firestore, Pub/Sub **publish**,
  Vertex AI, Model Armor, and Trace roles — it is deliberately not a Pub/Sub subscriber.
- `/api/internal/*` requires a shared-secret header (Cloud Scheduler) or a verified OIDC
  token from an allowlisted service account (Pub/Sub push). Neither endpoint can approve
  a publication.
- Degradation fails safe: a screening outage falls back to the local detector and stamps
  the result degraded; it never treats unscreened content as clean.
- **Gemini request storage is opted out on every call.** By default, GenerateContent
  (standard Gemini API) requests are stored server-side to help with debugging; the
  fleet sets `store: false` per request on every live call (desks, search researcher,
  Gemma PII pass), so a newsroom's drafts and sources are not retained by Google. To
  enable retention for observability/debugging, run with `NRF_GEMINI_STORE=true` —
  `GET /api/runtime` reports `gemini_store` either way.

**Limitations, stated plainly**

- **Identity is a request field, not an authenticated session.** The reporter/editor
  toggle is a demo affordance. The *authorisation* rule is genuinely server-side, but
  production needs a signed token — this is the one gap between the demo and a deployable
  newsroom tool.
- No universal truth detection. The system verifies whether a cited source supports a
  statement, checks selected figures against explicit adapters, and flags defined standards
  risks. That is all it claims.
- Standards output is **editorial risk routed to an editor**, not legal advice and not a
  libel verdict.
- Authoritative coverage is limited to the configured adapters. Anything outside them is
  abstained on, never estimated.
- No autonomous publishing, ever. The Editor Gate fails closed: it denies, and never
  mutates verdicts.
