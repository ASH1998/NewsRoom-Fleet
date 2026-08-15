#!/usr/bin/env bash
# Build and deploy Newsroom Fleet to Cloud Run, then wire the asynchronous parts.
#
# SAFETY: dry-run by default. Nothing is built or deployed until APPLY=1.
#
#   ./deploy/deploy.sh                    # show what would run
#   APPLY=1 ./deploy/deploy.sh            # build + deploy Cloud Run
#   APPLY=1 WIRE_ASYNC=1 ./deploy/deploy.sh   # also Pub/Sub push + Scheduler (needs Tier B)
#
# MODE=fixture (default) deploys the deterministic desks on real Google Cloud
# infrastructure — the configuration the recorded demo runs on. MODE=live swaps
# in the ADK/Gemini desks. Everything else is identical either way, which is the
# point of the switches: the fleet's behaviour is not a function of its plumbing.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# gcloud on Windows cannot read Git Bash's /f/... paths; --source needs a real
# Windows path. cygpath is present in Git Bash and absent elsewhere, which is
# exactly the condition we want to branch on.
if command -v cygpath >/dev/null 2>&1; then
  SRC_ROOT="$(cygpath -w "${REPO_ROOT}")"
else
  SRC_ROOT="${REPO_ROOT}"
fi
PROJECT_ID="${PROJECT_ID:-$(grep -m1 '^PROJECT_ID=' "${REPO_ROOT}/.env" 2>/dev/null | cut -d= -f2)}"
: "${PROJECT_ID:?set PROJECT_ID or put it in .env}"

REGION="${REGION:-asia-south1}"       # co-located with the existing Firestore database
MODE="${MODE:-fixture}"
APPLY="${APPLY:-0}"
WIRE_ASYNC="${WIRE_ASYNC:-0}"

# Scale to zero by default. A warm instance costs roughly ₹4,100/month — 41% of
# the whole budget — to avoid a 5-10 second cold start. Set MIN_INSTANCES=1 for
# the hour you record the demo, then put it back to 0.
MIN_INSTANCES="${MIN_INSTANCES:-0}"

TOPIC="${TOPIC:-newsroom-fleet-reviews}"
DLQ_TOPIC="${DLQ_TOPIC:-newsroom-fleet-reviews-dlq}"
SUBSCRIPTION="${SUBSCRIPTION:-newsroom-fleet-reviews-push}"
SCHEDULER_JOB="${SCHEDULER_JOB:-newsroom-fleet-recheck}"
SCHEDULE="${SCHEDULE:-0 * * * *}"
ARMOR_TEMPLATE="${ARMOR_TEMPLATE:-}"   # empty = keep the heuristic screener

BACKEND_SVC="${BACKEND_SVC:-newsroom-fleet-api}"
FRONTEND_SVC="${FRONTEND_SVC:-newsroom-fleet-desk}"
RUN_SA_EMAIL="newsroom-fleet-run@${PROJECT_ID}.iam.gserviceaccount.com"
INVOKER_SA_EMAIL="newsroom-fleet-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA_EMAIL="newsroom-fleet-build@${PROJECT_ID}.iam.gserviceaccount.com"
# --build-service-account wants the full resource path, not the bare email.
BUILD_SA_REF="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA_EMAIL}"

G=(gcloud --project "${PROJECT_ID}" --impersonate-service-account=)

FAILURES=0

run() {
  echo "  \$ $*"
  [[ "${APPLY}" == "1" ]] || return 0
  if ! "$@"; then
    FAILURES=$((FAILURES + 1))
    echo "  !! FAILED: $1 $2 $3"
    return 1
  fi
}

# A step whose failure makes everything after it meaningless.
require() {
  run "$@" || { echo; echo "ABORTED — see the error above. Nothing further was attempted."; exit 1; }
}

# Best-effort cleanup before a recreate. "Not found" is the expected outcome on
# a first deploy, so these must not count toward the failure tally.
try_run() {
  echo "  \$ $* (ignoring 'not found')"
  [[ "${APPLY}" == "1" ]] || return 0
  "$@" >/dev/null 2>&1 || true
}

if [[ "${APPLY}" != "1" ]]; then
  echo "*** DRY RUN — nothing will be built or deployed. Re-run with APPLY=1. ***"
fi
echo "project ${PROJECT_ID} · region ${REGION} · mode ${MODE} · min-instances ${MIN_INSTANCES}"
echo

# Which cloud components the deployed service actually turns on. Firestore and
# Cloud Trace only — Pub/Sub and Model Armor are added below, and only if the
# resources they need were approved and created.
QUEUE="inprocess"
SCREENER="heuristic"
[[ "${WIRE_ASYNC}" == "1" ]] && QUEUE="pubsub"
[[ -n "${ARMOR_TEMPLATE}" ]] && SCREENER="model_armor"

# Custom delimiter, and NOT '@': NRF_SERVICE_ACCOUNTS carries a service-account
# email, whose own '@' would split the value and make gcloud reject the whole
# argument list. '~' cannot appear in any of these values.
D='~'
ENV_VARS="NRF_MODE=${MODE}"
ENV_VARS="${ENV_VARS}${D}NRF_REPOSITORY=firestore"
ENV_VARS="${ENV_VARS}${D}NRF_TRACING=cloud"
ENV_VARS="${ENV_VARS}${D}NRF_QUEUE=${QUEUE}"
ENV_VARS="${ENV_VARS}${D}NRF_SCREENER=${SCREENER}"
ENV_VARS="${ENV_VARS}${D}NRF_MEMORY=file"
ENV_VARS="${ENV_VARS}${D}NRF_PII=off"
ENV_VARS="${ENV_VARS}${D}NRF_GCP_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS}${D}NRF_GCP_LOCATION=${REGION}"
ENV_VARS="${ENV_VARS}${D}NRF_PUBSUB_TOPIC=${TOPIC}"
ENV_VARS="${ENV_VARS}${D}NRF_PUBSUB_DLQ=${DLQ_TOPIC}"
ENV_VARS="${ENV_VARS}${D}NRF_SERVICE_ACCOUNTS=${INVOKER_SA_EMAIL}"
[[ -n "${ARMOR_TEMPLATE}" ]] && ENV_VARS="${ENV_VARS}${D}NRF_MODEL_ARMOR_TEMPLATE=${ARMOR_TEMPLATE}"

SECRETS=()
if [[ "${WIRE_ASYNC}" == "1" ]]; then
  SECRETS=(--set-secrets "NRF_SERVICE_TOKEN=newsroom-fleet-service-token:latest")
fi

echo "== backend (${BACKEND_SVC}) =="
# `require`, not `run`: the frontend's BACKEND_URL, the push subscription, and
# the scheduler job all point at this service. Continuing past a failed backend
# deploy is how a run ends up creating a subscription aimed at a placeholder URL.
require "${G[@]}" run deploy "${BACKEND_SVC}" \
  --source "${SRC_ROOT}/backend" \
  --region "${REGION}" \
  --service-account "${RUN_SA_EMAIL}" \
  --build-service-account "${BUILD_SA_REF}" \
  --allow-unauthenticated \
  --timeout 600 \
  --memory 1Gi \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances 4 \
  "${SECRETS[@]}" \
  --set-env-vars "^${D}^${ENV_VARS}"

BACKEND_URL="$("${G[@]}" run services describe "${BACKEND_SVC}" --region "${REGION}" \
  --format='value(status.url)' 2>/dev/null || echo '')"
if [[ "${APPLY}" == "1" && -z "${BACKEND_URL}" ]]; then
  echo "ABORTED — backend deployed but has no URL; refusing to wire anything to it."
  exit 1
fi
BACKEND_URL="${BACKEND_URL:-https://<backend-url>}"
echo "  backend: ${BACKEND_URL}"
echo

echo "== editor desk (${FRONTEND_SVC}) =="
run "${G[@]}" run deploy "${FRONTEND_SVC}" \
  --source "${SRC_ROOT}/frontend" \
  --region "${REGION}" \
  --build-service-account "${BUILD_SA_REF}" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "BACKEND_URL=${BACKEND_URL}"

FRONTEND_URL="$("${G[@]}" run services describe "${FRONTEND_SVC}" --region "${REGION}" \
  --format='value(status.url)' 2>/dev/null || echo 'https://<frontend-url>')"
echo

if [[ "${WIRE_ASYNC}" == "1" ]]; then
  echo "== Pub/Sub push subscription =="
  # Push (not pull) so review workers scale with Cloud Run and hold no standing
  # subscriber credential. Dead-lettering after 5 attempts bounds poison
  # messages; the claim's missing verdict then keeps the gate at NEEDS_HUMAN.
  try_run "${G[@]}" pubsub subscriptions delete "${SUBSCRIPTION}" --quiet
  run "${G[@]}" pubsub subscriptions create "${SUBSCRIPTION}" \
    --topic "${TOPIC}" \
    --push-endpoint "${BACKEND_URL}/api/internal/review-task" \
    --push-auth-service-account "${INVOKER_SA_EMAIL}" \
    --ack-deadline 120 \
    --enable-message-ordering \
    --dead-letter-topic "${DLQ_TOPIC}" \
    --max-delivery-attempts 5

  PROJECT_NUMBER="$("${G[@]}" projects describe "${PROJECT_ID}" \
    --format='value(projectNumber)' 2>/dev/null || echo '<project-number>')"
  PUBSUB_AGENT="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
  # Pub/Sub's own agent needs rights to move messages into the DLQ.
  run "${G[@]}" pubsub topics add-iam-policy-binding "${DLQ_TOPIC}" \
    --member="${PUBSUB_AGENT}" --role=roles/pubsub.publisher --quiet
  run "${G[@]}" pubsub subscriptions add-iam-policy-binding "${SUBSCRIPTION}" \
    --member="${PUBSUB_AGENT}" --role=roles/pubsub.subscriber --quiet
  echo

  echo "== Cloud Scheduler recheck (${SCHEDULE}) =="
  # The asynchrony proof: the watcher resumes published articles on a schedule,
  # from persisted snapshots, with no operator present. It drafts candidates for
  # an editor and can never publish one.
  try_run "${G[@]}" scheduler jobs delete "${SCHEDULER_JOB}" --location "${REGION}" --quiet
  # The token is read into a local variable and passed as a header. It is never
  # printed, so the dry run shows a placeholder.
  echo "  \$ gcloud scheduler jobs create http ${SCHEDULER_JOB} --location ${REGION}" \
       "--schedule '${SCHEDULE}' --uri ${BACKEND_URL}/api/internal/recheck-all" \
       "--http-method POST --headers x-newsroom-service-token=<secret> --attempt-deadline 600s"
  if [[ "${APPLY}" == "1" ]]; then
    # tr, not just $(): the payload carries a trailing newline and gcloud on
    # Windows adds a carriage return. Either one ends up stored verbatim in the
    # Scheduler job's header and silently fails to match.
    TOKEN="$("${G[@]}" secrets versions access latest --secret=newsroom-fleet-service-token | tr -d '\r\n')"
    "${G[@]}" scheduler jobs create http "${SCHEDULER_JOB}" \
      --location "${REGION}" \
      --schedule "${SCHEDULE}" \
      --uri "${BACKEND_URL}/api/internal/recheck-all" \
      --http-method POST \
      --headers "x-newsroom-service-token=${TOKEN}" \
      --attempt-deadline 600s \
      --description "Recheck published claims against authoritative data"
  fi
  echo
fi

if [[ "${APPLY}" == "1" && ${FAILURES} -gt 0 ]]; then
  echo "INCOMPLETE — ${FAILURES} step(s) failed. Read the errors above before recording"
  echo "anything in deploy/CLOUD_LEDGER.md; the deployment is not usable as it stands."
  exit 1
fi

if [[ "${APPLY}" == "1" ]]; then
  cat <<EOF
Deployed. Add every line above to deploy/CLOUD_LEDGER.md.

  Editor desk   ${FRONTEND_URL}
  API           ${BACKEND_URL}
  Runtime       ${BACKEND_URL}/api/runtime   <- which implementation is really serving
  Traces        https://console.cloud.google.com/traces/list?project=${PROJECT_ID}
  Firestore     https://console.cloud.google.com/firestore/databases/-default-/data?project=${PROJECT_ID}
  Cost check    ./deploy/audit_cloud.sh
EOF
else
  echo "Dry run complete. Nothing was built or deployed."
  echo "  APPLY=1 PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/deploy.sh"
fi
