# Progress

Status of Newsroom Fleet against `Newsroom-Fleet-Winning-Design-Report.md`.
Last updated: 2026-08-16.

**Where we are:** the product runs locally end to end with zero API keys, and every
Google Cloud capability is now implemented behind its interface — ADK/Gemini desks,
Firestore, Pub/Sub, Model Armor, Gemma, Memory Bank, Cloud Run, Cloud Scheduler, and
OpenTelemetry. The evaluation harness produces scored metrics. What remains is
**running the deploy against a real project** and the recording/writing artifacts.

---

## Complete

### Backend — deterministic core (`backend/`)

| Area | What exists |
| --- | --- |
| Contracts | Versioned Pydantic v2 schemas: `Claim`, `Verdict`, `SecurityResult`, `EditorDecision`, `ClaimSnapshot`, `WatcherResult`, `EvidenceRef` (`domain/contracts.py`) |
| Masthead | Desk registry with agent versions, schema versions, and permissions — permissions *are* the evidence boundaries the router enforces (`domain/masthead.py`) |
| Routing policy | Claim type → required desks, deterministic and outside model control (`domain/routing.py`) |
| State machine | All 8 publication states with legal-transition enforcement (`domain/state_machine.py`) |
| Editor Gate | Deterministic policy over persisted verdicts; every canonical decision rule from the report appendix (`domain/policy.py`) |
| Desks | Claim extractor, source verifier, data checker, standards reviewer, verdict aggregator, corrections watcher (`desks/`) |
| Routing | Per-claim desk selection; each desk receives only the evidence view its registration permits (`orchestration/router.py`) |
| Runner | Concurrent review with timeout, bounded retry, idempotency keys, and explicit ERROR verdicts (`orchestration/runner.py`) |
| Screening | Quarantine happens before any desk sees a source (`security/screening.py`) |
| Persistence | SQLite repository behind a `Repository` protocol + append-only audit events (`persistence/`) |
| Memory | Approved house rules and correction precedents with provenance (`memory/store.py`) |
| Adapters | Deterministic authoritative data adapter with `v1`/`v2` datasets for the upstream-change demo (`adapters/`) |
| API | FastAPI: submit, read, audit, decisions, publish, re-review, recheck, dispose correction, runtime view, service endpoints, demo controls (`api/routes.py`) |
| Tests | **73 passing** — policy rules, state machine, screening, runner failure/timeout/idempotency, watcher, golden pipeline, API, PII parse, grounded source verifier, review pacing, request-storage opt-out |

### Google Cloud phase — implemented behind the interfaces

Each is an independent switch (`config.py`); `NRF_PRESET=cloud` flips all of them.
Every one degrades to its local implementation with a logged warning rather than
failing startup, and `GET /api/runtime` reports what was *actually* constructed.

| Capability | Implementation |
| --- | --- |
| **ADK + Gemini** | One `LlmAgent` per desk, no tools, no transfer, schema-constrained output. **Verified live on `gemini-3.6-flash`** — reproduces the fixture demo exactly (see Notes). Routing is read from the claim text, never from the model's label; live reviewer citations must resolve against the evidence they were handed, or the verdict is downgraded with `broken_locator` (`desks/live/`) || **Firestore** | Second `Repository` implementation. Transactional verdict idempotency; deliberately index-free (single equality filter, ordered in Python) so it works on an empty default database (`persistence/firestore.py`) |
| **Pub/Sub** | One message per claim × desk, ordering key per claim, existing idempotency keys carried through. Push subscription → `/api/internal/review-task`. All-or-nothing dispatch per claim; broker outage degrades to in-process and is audited (`orchestration/pubsub.py`, `orchestration/queue.py`) |
| **Model Armor** | Real detector behind `Screener`, filter results mapped to dispositions with an unknown-match fallback to quarantine. Outage falls back to the heuristic and stamps the result degraded (`security/model_armor.py`) |
| **Gemma (bonus model)** | Bounded PII classification at intake: five categories, strict JSON, abstention on unparseable output. Can only *add* a quarantine, never clear one (`security/pii.py`) |
| **Memory Bank** | Vertex AI Agent Engine behind `MemoryStore`. Writes happen only when an editor accepts a correction; facts without provenance are dropped on read (`memory/memory_bank.py`) |
| **Cloud Run** | Dockerfiles for backend and frontend; nginx same-origin proxy so no CORS in the demo |
| **Cloud Scheduler** | Hourly `POST /api/internal/recheck-all` over published articles — the watcher resumes with no operator present |
| **OpenTelemetry** | Spans across intake → screen → extract → per-claim → per-desk-attempt → gate → publish → watcher, exported to Cloud Trace. Every audit event carries its `trace_id` (`observability/tracing.py`) |
| **Identity on service endpoints** | Shared-secret header (Scheduler) or verified OIDC from an allowlisted service account (Pub/Sub push) |

### Product

- **Grounded Source Verifier** (`desks/live/grounded_source_verifier.py`) — a claim
  that cites no source is no longer an automatic abstain. The ladder mirrors the
  grounded Data Checker: attached sources first (search never overrides the
  reporter's evidence and never launders a quarantined one), Google Search second
  (screened research, handle-cited judgement, locator guard, approved-authority
  rule — a random page agreeing is downgraded to editor context, never
  verification), abstention third. Six offline tests pin the ladder in
  `tests/test_grounded_source_verifier.py`.
- **Submit-your-own-article UI** — headline, byline, body, and attached sources with a
  one-click `[source:…]` citation helper. Runs the same intake screening, extraction,
  routing, and gate as the golden article.
- **Runtime badges** — the top bar shows which implementation is really serving each
  interface; the Masthead shows the agent version actually constructed per desk.
- **Evaluation harness** — `uv run python -m newsroom_fleet.evaluation` scores extraction
  coverage, claim typing, verdict accuracy, evidence correctness, unsafe false
  verification, abstention quality, publish-gate integrity, injection recall and false
  positives, quarantine containment, and recovery. Writes `eval_results/report.{md,json}`.
  **Current run: all metrics 100%, unsafe false verifications 0.**

### Docs

- `ARCHITECTURE.md` — Mermaid diagram plus tables for models, agents and their evidence
  boundaries, Google Cloud services, trust boundaries, persisted records, failure behaviour.
- `README.md` — one-minute proof, switch table, reproduction steps, deploy, security and
  limitations.
- `deploy/setup_gcp.sh`, `deploy/deploy.sh` — provisioning and deployment.

### Demo path — verified in the browser end to end

1. Golden article submits → memo quarantined at intake → 5 claims → 11 verdicts → `human review`.
2. Reporter attempts publish → **403, gate refuses**: *"role 'reporter' has no publish authority"*
   and *"4 claim(s) unresolved and no editor decision recorded"*.
3. Editor resolves the 4 blocking verdicts with a safe revision → publish succeeds → `published`,
   numeric claims snapshotted.
4. Advance authoritative data → watcher drafts a material correction candidate (4.9 → 5.1) →
   editor accepts → back to `published`.
5. Crash the data checker → that claim becomes an ERROR verdict / `NEEDS_HUMAN` while the other
   desks finish → clear the failure → re-review replaces the ERROR with a real verdict.

---

## Pending

### Google Cloud

Project `project-7ca77fe6-7ea2-403d-92b`, region `asia-south1` (co-located with the
Firestore database that already existed there). **Every cloud action is recorded in
[`deploy/CLOUD_LEDGER.md`](deploy/CLOUD_LEDGER.md)** against a ₹10,000 budget.

- [x] Tier A+B provisioned: APIs, Artifact Registry, two Pub/Sub topics, three
      least-privilege service accounts (run / build / invoker), the service-token secret.
- [x] **Deployed and verified.** Editor desk and API live on Cloud Run
      (`asia-south1`, both scale-to-zero). `/api/runtime` resolves to
      `repository: firestore`, `queue: pubsub`, `tracing: cloud`.
- [x] Async proven on real infrastructure: submit returns `reviewing` with **0 verdicts**,
      Pub/Sub push delivers all 11, the article reaches `human_review` unattended.
      Reporter publish → 403. 39/39 audit events carry a `trace_id`. **0 composite
      Firestore indexes** needed. Scheduler job authenticates and runs.
- [ ] **Model Armor (Tier C)** — deliberately not provisioned. Per-unit price and
      `asia-south1` availability are unverified, and the heuristic screener already
      quarantines the planted memo. Fidelity upgrade, not a functional gap.
- [ ] **Memory Bank** — needs an Agent Engine instance with its own hourly cost. Not
      provisioned; file-backed memory already retrieves the precedent with provenance.

### Product gaps

- [ ] **Authentication** — identity is still a request field. The authorisation rule is
      genuinely server-side; the *authentication* is not. Either move it to a signed token
      or keep it as the stated limitation (it is currently stated in the README).
- [ ] **Live-mode evaluation run** — the harness scores fixture mode. Running it against
      `NRF_MODE=live` would produce the more interesting number, and costs API calls.
- [x] **Gemma PII pass verified live** against `gemma-4-26b-a4b-it`. The first
      live run exposed a real bug (see Notes). A planted personal phone + home
      email quarantines as `sensitive_data` with the Gemma version stamp; a
      clean news sentence passes with the pass recorded in the screener detail,
      so a silent outage can never read as "no PII found". Parse contract
      pinned offline in `tests/test_pii_parse.py`.

### Submission packaging

- [ ] Recorded unedited demo following the report's 9-step choreography.
- [ ] Public build article on why editorial independence needs information barriers.
- [ ] Social post — the quarantined memo or the failed publish attempt, not a product screenshot.
- [ ] Devpost submission fields.

---

## Notes

- `backend/pyproject.toml` pins pytest's `--basetemp` inside the repo; the machine-wide temp dir
  was not writable and every fixture-using test errored.
- The gate report still reads `human review` after publication. That is correct: an editorial
  decision *resolves* blocking verdicts, it never rewrites them. The UI says so explicitly.
- The evaluation harness caught a real extractor gap on its first run: comma-grouped figures
  ("812,000 trips") were typed `general` and never reached the Data Checker. Fixed in
  `domain/routing.py`; the pattern excludes bare integers so years stay out of it.
- **The first live run caught a worse one.** Gemini labelled *"the council voted 6-1"* as
  `numeric` and *"unemployment fell to 4.2 percent"* as `attribution` — both defensible
  readings of the prose, both wrong for routing. The figure went to the Source Verifier
  (no source to check) and the vote to the Data Checker (no adapter coverage). Every claim
  still blocked, so nothing unsafe escaped, but **the contradiction the whole case rests on
  was never found.** Routing now lives entirely in `domain/routing.classify`, reading
  signals out of the claim text; the model's label is a fallback used only when no signal
  fires. Both extractors share that one function. The second live run reproduces the
  fixture demo verdict for verdict.
- Live desks needed the timeout default raised: 5s is right for fixture desks and shorter
  than a single Gemini round trip, so every live desk would have timed out and escalated
  for a purely operational reason. `NRF_MODE=live` now defaults to 60s.
- Cloud dependencies live in an optional extra (`uv sync --extra cloud`). Fixture mode
  depends on none of them, and the app starts fine with the extra absent.
- **A user-submitted article found a real cross-article bug.** Claim ids
  (`clm_01`…) are unique per article, but the verdict slot — SQLite primary
  key, Firestore document id, the runner's idempotency pre-check, and the
  queue's idempotency key — was keyed `(claim_id, desk)` only. A second
  article minting the same claim ids silently inherited the first article's
  verdicts: those desks never ran (no audit event at all), and its aggregates
  overwrote the first article's rows. The gate still failed closed — the
  claims blocked as "no verdict on record" and nothing unsafe published —
  which is why it surfaced as missing reviews rather than a safety hole. The
  slot is now `(article_id, claim_id, desk)` everywhere, and
  `test_articles_with_repeated_claim_ids_do_not_share_verdict_slots` pins it.
- **Gemma 4 (a4b) is a thinking model, and that cost the PII pass its entire budget.**
  At `max_output_tokens: 200` every call returned thought parts only — `response.text`
  was `None`, `finish_reason: MAX_TOKENS` — so the classifier abstained on everything.
  The fail-safe held (escalate-only, abstention recorded), which made this a dead
  feature rather than a safety hole. A PII hit also reasons harder than a clean pass:
  1024 tokens still truncated mid-thought, 4096 completes with the one-line JSON.
  The budget is now 4096 and `_parse` falls back per brace-block so reasoning
  preamble around the JSON cannot break it.
- **A 12-claim live submission saturated the fleet.** `review_all` fired every
  claim's Gemini/search agents at once: the event loop crawled (a trivial list
  endpoint took 4.7s) and the review stalled behind the storm. Claim review is
  now bounded by a semaphore — **one claim at a time by default**
  (`NRF_REVIEW_CONCURRENCY`, raise for throughput). The desks within a claim
  still run concurrently. Sequential pacing also streams beautifully in the
  editor UI: the fleet visibly works down the claim list.
  `test_review_all_paces_claims_one_at_a_time_by_default` pins it.
- **Gemini request storage is opted out on every call.** The standard Gemini
  API stores GenerateContent requests by default "to help with debugging";
  opting out is a top-level `store: false` body field that google-genai 2.18.1
  does not yet model (verified live: the API parses and type-checks the field;
  the SDK rejects it on `GenerateContentConfig`). It travels instead through
  the SDK's documented `HttpOptions.extra_body` — merged into every request —
  and ADK's `Gemini(client_kwargs=...)`, so all desks, the search researcher,
  and the Gemma PII pass carry it. `NRF_GEMINI_STORE=true` opts back in for
  debugging with Google support; `/api/runtime` reports `gemini_store`.
