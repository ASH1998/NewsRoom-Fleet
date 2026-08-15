# Cloud ledger

Every Google Cloud action taken for Newsroom Fleet, what it cost, and who approved it.

**Budget: ₹10,000.** Assumed FX **₹88 = $1** (≈ $113). All USD figures are list price;
INR is converted at that rate. Estimates are marked *(est.)* until a real bill confirms them.

**Rules of engagement**
1. No resource is created, modified, or deleted without explicit approval from Ashutosh,
   recorded in the Approval column.
2. Read-only calls (`describe`, `list`, `get`) cost nothing and are logged for the record
   but do not need approval.
3. Every approved action gets a row *before* it is run, and its actual cost filled in after.
4. Running total is updated on every row. If a row would take the total past ₹8,000
   (80%), stop and re-confirm.

---

## Account context

| Item | Value |
| --- | --- |
| Project | `project-7ca77fe6-7ea2-403d-92b` (number `775995990601`) |
| Billing | **Enabled** — `billingAccounts/014522-96D579-2D9DA5` |
| Shared with | **ByFeel** — this is the same project as the other submission |
| Active gcloud config | `byfeel-restricted`, impersonating `byfeel-local-dev@…` |
| Config used for this work | `default` (no impersonation) — the restricted SA cannot read the project |

> **Shared-project note.** Firestore's `(default)` database already exists and belongs to
> ByFeel. Newsroom Fleet's repository namespaces every collection under
> `newsroom_fleet_*` (`NRF_FIRESTORE_PREFIX`), so the two never touch the same documents.
> Nothing in this project is deleted or reset by Newsroom Fleet code except its own
> prefixed collections.

---

## Existing state (observed 2026-08-15, read-only)

| Resource | Status | Implication |
| --- | --- | --- |
| Firestore `(default)` | **Exists**, `asia-south1`, FIRESTORE_NATIVE | No creation needed. **Region is asia-south1**, so Cloud Run should deploy there too |
| `firestore.googleapis.com` | Enabled | — |
| `cloudtrace.googleapis.com` | Enabled | — |
| `run.googleapis.com` | **Disabled** | Needs enabling to deploy |
| `pubsub.googleapis.com` | **Disabled** | Needs enabling for the queue |
| `modelarmor.googleapis.com` | **Disabled** | Needs enabling for real screening |
| `aiplatform.googleapis.com` | **Disabled** | Only needed for Memory Bank / Vertex-hosted models |
| `cloudbuild`, `artifactregistry`, `cloudscheduler`, `secretmanager` | **Disabled** | Needed to build, deploy, schedule |
| Cloud Run services | None | — |
| Pub/Sub topics | None | — |

Gemini and Gemma run through `GOOGLE_API_KEY` (Gemini API), **not** Vertex AI, so they
are billed to that key and need no API enablement in this project.

---

## Ledger

| # | Date | Action | Type | Approved by | Est. cost | Actual | Running total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-08-15 | `gcloud projects describe`, `billing projects describe`, `services list`, `firestore databases list`, `run services list`, `pubsub topics list` | read-only | n/a | ₹0 | ₹0 | ₹0 |
| 2 | 2026-08-15 | `GET generativelanguage…/models` — verify the model IDs in `.env` | read-only | n/a | ₹0 | ₹0 | ₹0 |
| 3 | 2026-08-15 | `setup_gcp.sh` dry run, tiers A/B/C — describes only | read-only | n/a | ₹0 | ₹0 | ₹0 |
| 4 | 2026-08-15 | `deploy.sh` dry run | read-only | n/a | ₹0 | ₹0 | ₹0 |
| 5 | 2026-08-15 | Live-mode smoke run #1 — golden article through ADK desks, `gemini-3.6-flash` (~6 calls) | API call | Ashutosh | ₹1–2 | ₹1 *(est.)* | ₹1 |
| 6 | 2026-08-15 | Live-mode smoke run #2 — re-run after the routing fix (~7 calls) | API call | Ashutosh | ₹1–2 | ₹1 *(est.)* | ₹2 |

| 7 | 2026-08-15 | **Tier A+B provisioning** — `setup_gcp.sh TIER=AB APPLY=1` | create | Ashutosh | ₹0 one-off | ₹0 | ₹2 |

**Running total: ₹2 of ₹10,000** (Gemini API calls, billed to `GOOGLE_API_KEY`).

### Row 7 — resources created, verified by `audit_cloud.sh`

| Resource | Name | Standing cost |
| --- | --- | --- |
| APIs enabled | `run`, `cloudbuild`, `artifactregistry`, `pubsub`, `cloudscheduler`, `secretmanager` | ₹0 — enabling is free |
| Artifact Registry | `newsroom-fleet` (asia-south1, docker, currently 0 B) | ₹0 until images are pushed, then ~₹9/GB/mo |
| Pub/Sub topic | `newsroom-fleet-reviews` (7-day retention) | ₹0 — under the 10 GiB/mo free tier |
| Pub/Sub topic | `newsroom-fleet-reviews-dlq` (7-day retention) | ₹0 |
| Service account | `newsroom-fleet-run@…` — `datastore.user`, `cloudtrace.agent`, `pubsub.publisher`, `secretmanager.secretAccessor` | ₹0 |
| Service account | `newsroom-fleet-invoker@…` — no project roles; used as a push/scheduler identity only | ₹0 |
| Secret | `newsroom-fleet-service-token` (1 version, generated locally, never echoed) | **₹6/mo** |

Not created: Firestore (already existed), Model Armor (Tier C, not approved), Cloud Run
services and the Pub/Sub subscription (created by `deploy.sh`, row 8).

The backend service account is deliberately **not** a Pub/Sub subscriber — review work
arrives by push, so it holds no standing right to pull messages.

| 8 | 2026-08-15 | **Deploy attempt — FAILED.** Backend rejected at argument parsing; frontend build denied by IAM | create (failed) | Ashutosh | ₹0 | ₹0 | ₹2 |

### Row 8 — failed deploy, and two resources created without approval

**Nothing was deployed.** No Cloud Run service exists. But `gcloud run deploy --source`
provisions its own staging infrastructure before building, and in a non-interactive shell
its confirmation prompt defaults to yes. Two resources were created that I did not put in
front of you:

| Resource | Created by | Cost | Status |
| --- | --- | --- | --- |
| Artifact Registry `cloud-run-source-deploy` (asia-south1) | `gcloud run deploy --source`, auto-prompt | ₹0 — empty | **Awaiting your decision: delete, or keep** |
| GCS bucket `run-sources-project-…-asia-south1` | same | ₹0 — holds one ~KB source zip | **Awaiting your decision** |

Both are empty or near-empty and cost nothing measurable, but they were not approved and
are recorded here rather than quietly left in place.

**Three defects in my own scripts, now fixed:**

1. `--set-env-vars` used `^@^` as its delimiter while `NRF_SERVICE_ACCOUNTS` carries a
   service-account email. The `@` inside the email split the value and gcloud rejected the
   whole argument list. Delimiter is now `~`.
2. The script continued past the failed backend deploy and tried to create a Pub/Sub push
   subscription and a Scheduler job pointing at the literal string `https://<backend-url>`.
   Both were rejected by the API, which is the only reason no broken wiring exists. The
   backend deploy is now a `require` step that aborts the run.
3. The script printed **"Deployed."** and exited 0 after all of that. It now counts
   failures and exits non-zero with `INCOMPLETE`.

**The remaining blocker is real, not a script bug.** Cloud Build runs as
`775995990601-compute@developer.gserviceaccount.com`, which holds **no project roles at
all**, so it cannot read the source it was asked to build:

```
Error 403: 775995990601-compute@developer.gserviceaccount.com does not have
storage.objects.get access to …/run-sources-…/newsroom-fleet-desk/….zip
```

Fixing it means granting IAM, which needs approval.

| 9 | 2026-08-15 | Create `newsroom-fleet-build` service account + 3 build roles | create | Ashutosh | ₹0 | ₹0 | ₹2 |
| 10 | 2026-08-15 | Decision: keep `cloud-run-source-deploy` and the staging bucket | decision | Ashutosh | ₹0 | ₹0 | ₹2 |

### Row 9 — build identity

A dedicated identity rather than the project's shared Compute Engine default account or
the runtime account. `newsroom-fleet-build@…` holds exactly three roles:

| Role | Why |
| --- | --- |
| `roles/storage.objectUser` | Read the uploaded source zip from the staging bucket |
| `roles/artifactregistry.writer` | Push the built image |
| `roles/logging.logWriter` | Write build logs |

It cannot deploy, cannot read Firestore, and cannot publish to Pub/Sub. Conversely
`newsroom-fleet-run` — the identity the service actually runs as — **cannot push images**,
so a compromised runtime cannot rewrite the code it runs. That separation is the same
least-privilege argument the desks make about evidence, applied to the supply chain.

Both deploys now pass `--build-service-account`, so no build uses the shared default
account.

### Row 10 — the stray resources stay

`cloud-run-source-deploy` and `run-sources-…-asia-south1` are kept: the staging bucket is
required by any `--source` deploy and would be recreated regardless.

> **Correction.** I previously wrote that builds would be pinned to the `newsroom-fleet`
> repository so the stray one would stay empty. That was wrong. `gcloud run deploy
> --source` always publishes to `cloud-run-source-deploy` and has no flag to redirect it;
> only an explicit `gcloud builds submit --tag` would use a chosen repository. Actual
> state: `cloud-run-source-deploy` holds **324 MB** of images and `newsroom-fleet` is
> **empty and unused**. Cost is ~₹3/month either way. Left as is rather than restructuring
> the build for cosmetics; `newsroom-fleet` can be deleted whenever you like.

| # | Date | Action | Type | Approved by | Est. cost | Actual | Running total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 2026-08-15 | **Cloud Run deploy — succeeded.** `newsroom-fleet-api` + `newsroom-fleet-desk`, both `--min-instances=0` | create | Ashutosh | ₹0 one-off | ₹0 | ₹2 |
| 12 | 2026-08-15 | Pub/Sub push subscription `newsroom-fleet-reviews-push` (ordered, DLQ ×5) + Cloud Scheduler job `newsroom-fleet-recheck` (hourly) | create | Ashutosh | ₹0 | ₹0 | ₹2 |
| 13 | 2026-08-15 | End-to-end verification: golden article, publish denial, scheduler trigger | usage | Ashutosh | ₹0 | ₹0 | ₹2 |

**Running total: ₹2 of ₹10,000.** Recurring: **≈ ₹9/month** (₹3 image storage + ₹6 secret),
plus per-request Cloud Run charges that stay at ₹0 while traffic is inside the free tier.

### Row 11–13 — what is live and what was proved

| URL | |
| --- | --- |
| Editor desk | https://newsroom-fleet-desk-6dz7i3zaja-el.a.run.app |
| API | https://newsroom-fleet-api-6dz7i3zaja-el.a.run.app |
| Runtime view | https://newsroom-fleet-api-6dz7i3zaja-el.a.run.app/api/runtime |

`/api/runtime` reports `repository: firestore`, `queue: pubsub`, `tracing: cloud`,
`screener: heuristic`, `mode: fixture` — **resolved values**, so nothing is claiming a
cloud component it did not actually construct.

| Claim | Evidence |
| --- | --- |
| Asynchronous execution is real | Submit returned `state: reviewing` with **0 verdicts**; Pub/Sub push then delivered all 11, and the article advanced to `human_review` on its own |
| Idempotency survives the network hop | 5 `claim_dispatched` events carry real broker message IDs and keys like `clm_01:source_verifier` |
| The gate refuses server-side | Reporter publish → 403: *"role 'reporter' has no publish authority"* and *"4 claim(s) unresolved and no editor decision recorded"* |
| Screening precedes review | `leaked_memo` quarantined at intake; `clm_05` unsupported with `quarantined_source` |
| Every record is traceable | **39 of 39** audit events carry a `trace_id` |
| Firestore needs no index setup | **0 composite indexes** in the project — the design goal held against a real database |
| Scheduler identity works | `gcloud scheduler jobs run` accepted; the endpoint returns 401 without the token, 401 with a wrong one, 200 with the right one |

### Three defects the deployment exposed (all fixed, all fail-safe)

1. **Pub/Sub silently fell back to in-process.** `PubSubReviewQueue.__init__` called
   `get_topic()` to fail fast, but `roles/pubsub.publisher` grants *publish*, not *get* —
   a correctly-scoped identity 403'd its own health check. Removed the eager check rather
   than widen the role; the router already degrades and audits `queue_degraded`.
2. **The service token never matched.** Secret Manager payloads carry a trailing newline
   and gcloud on Windows adds `\r`; the Scheduler job stored `"…bKz4\r"`. Now stripped on
   both sides. The failure mode denied rather than allowed.
3. **The deploy script reported success after failing.** It printed "Deployed." and exited
   0 having deployed nothing. Now aborts on a failed backend deploy and exits non-zero.

Defects 1 and 2 were invisible in the deploy output and only showed up in `/api/runtime`
and a direct auth probe. That is the argument for the runtime view existing at all.

### What the live runs proved (rows 5–6)

Run #1 surfaced a real routing defect. The model labelled *"the council voted 6-1"* as
`numeric` and *"unemployment fell to 4.2 percent"* as `attribution` — both defensible
readings, both wrong for routing. The figure went to the Source Verifier (no source to
check) and the vote went to the Data Checker (no adapter coverage). Every claim still
blocked, so **nothing unsafe escaped**, but the contradiction the whole case rests on —
4.2 against the authority's 4.9 — was never found.

Fixed by moving routing entirely into `domain/routing.classify`, which reads signals from
the claim text; the model's label is now a fallback used only when no signal fires.
Run #2 reproduces the fixture demo exactly:

| Claim | Desk | Verdict |
| --- | --- | --- |
| council voted 6-1 | source_verifier | `verified`, cites `council_minutes#body` |
| unemployment 4.2 percent | data_checker | `contradicted`, cites `state-labor…#unemployment_rate` |
| "a thousand jobs" quote | source_verifier | `unsupported` — transcript says otherwise |
| charged → "is guilty" | standards_reviewer | `unsupported`, `legal_status_violation` |
| leaked memo | source_verifier | `unsupported`, `quarantined_source` |

Gate: `human_review`, 4 blocked claims — identical to fixture mode. The memo's injected
instruction influenced nothing.

Also fixed: the desk timeout defaulted to 5s, which every live Gemini call would have
exceeded. It now defaults to 60s when `NRF_MODE=live`.

### Model IDs confirmed available (row 2)

| Purpose | Model | Source |
| --- | --- | --- |
| Desk reasoning | `gemini-3.6-flash` | `GOOGLE_MODEL` in `.env` — confirmed live |
| (unused so far) | `gemini-3.5-flash-lite` | `GOOGLE_MODEL_LITE` in `.env` — confirmed live |
| Bonus model, intake PII | `gemma-4-26b-a4b-it` | Confirmed live. The `.env` default `gemma-3-12b-it` is **not** served; the A4B variant is the cheap end of the current Gemma family and right-sized for a five-category classifier |

---

## Awaiting approval

Nothing below has been run. Costs are list-price estimates; the recurring column assumes
the demo stays up for one month.

### Tier A — minimum to have a live URL (recommended)

| Item | Cost model | One-off *(est.)* | Monthly *(est.)* |
| --- | --- | --- | --- |
| Enable `run`, `cloudbuild`, `artifactregistry` | free to enable | ₹0 | ₹0 |
| Cloud Build — ~6 builds × ~5 min | 120 free min/day, then $0.003/min | ₹0 | ₹0 |
| Artifact Registry — 2 images ≈ 1.2 GB | $0.10/GB/month | ₹0 | **₹11** |
| Cloud Run backend — **scale to zero** | $0.000024/vCPU-s, $0.0000025/GiB-s, 2M req free | ₹0 | **₹0–40** |
| Cloud Run frontend (nginx) — scale to zero | same | ₹0 | **₹0–10** |
| Firestore reads/writes for demo traffic | 50k reads / 20k writes per day free | ₹0 | **₹0** |
| Cloud Trace spans | 2.5M spans/month free | ₹0 | **₹0** |
| **Tier A total** | | **₹0** | **≈ ₹20–60** |

> Deliberately **`--min-instances=0`**, not 1. A warm instance is ~₹4,100/month — 41% of
> the entire budget to avoid a 5–10 second cold start. Set `MIN_INSTANCES=1` for the hour
> you record the demo, then put it back.

### Tier B — the asynchronous and security proofs

| Item | Cost model | One-off *(est.)* | Monthly *(est.)* |
| --- | --- | --- | --- |
| Enable `pubsub`, `cloudscheduler`, `secretmanager` | free to enable | ₹0 | ₹0 |
| Pub/Sub — demo volume is a few hundred tiny messages | 10 GiB/month free | ₹0 | **₹0** |
| Cloud Scheduler — 1 hourly job | 3 jobs free per account | ₹0 | **₹0** |
| Secret Manager — 1 secret | $0.06/secret/month + $0.03/10k access | ₹0 | **₹6** |
| **Tier B total** | | **₹0** | **≈ ₹6** |

### Tier C — needs a price check before approval

| Item | Concern |
| --- | --- |
| **Model Armor** | Priced per unit of content screened; I have not verified the current rate or whether `asia-south1` is a supported location. **Do not approve until both are confirmed.** The heuristic screener already quarantines the planted memo, so this is a fidelity upgrade, not a functional gap. |
| **Vertex AI Memory Bank** | Requires an Agent Engine instance, which has its own hourly cost. Not needed for the demo — file-backed memory retrieves the precedent with provenance today. |
| **Gemini / Gemma (live mode)** | Billed to `GOOGLE_API_KEY`, not to this project, so it does not draw on this ₹10,000 unless that key bills here. One live review of the golden article ≈ 6 agent calls ≈ ₹1–3. Cheap, but confirm which billing account the key sits on. |

---

## Reconciliation

`./deploy/audit_cloud.sh` lists everything in the project whose name starts with
`newsroom-fleet`, plus the Firestore collections under the `newsroom_fleet_` prefix.
Run it to check reality against this ledger.
