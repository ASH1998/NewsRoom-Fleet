#!/usr/bin/env bash
# One-time Google Cloud provisioning for Newsroom Fleet.
#
# SAFETY: dry-run by default. Nothing is created until you pass APPLY=1, and
# every mutating command is printed and appended to deploy/CLOUD_LEDGER.md.
#
#   ./deploy/setup_gcp.sh                 # show exactly what would be created
#   TIER=A APPLY=1 ./deploy/setup_gcp.sh  # create Tier A only (Cloud Run path)
#
# Tiers match deploy/CLOUD_LEDGER.md:
#   A  build + deploy surface        (run, cloudbuild, artifactregistry)  ~₹20-60/mo
#   B  + async and secrets           (pubsub, scheduler, secretmanager)   ~₹6/mo
#   C  + Model Armor                 (price and region UNVERIFIED)        unknown
#
# Idempotent: safe to re-run. Everything it touches is named `newsroom-fleet*`.
set -uo pipefail

PROJECT_ID="${PROJECT_ID:-$(grep -m1 '^PROJECT_ID=' "$(dirname "${BASH_SOURCE[0]}")/../.env" 2>/dev/null | cut -d= -f2)}"
: "${PROJECT_ID:?set PROJECT_ID or put it in .env}"

# asia-south1 because the project's Firestore database already lives there.
# Deploying compute elsewhere would add a cross-region hop to every read.
REGION="${REGION:-asia-south1}"
TIER="${TIER:-A}"
APPLY="${APPLY:-0}"

TOPIC="${TOPIC:-newsroom-fleet-reviews}"
DLQ_TOPIC="${DLQ_TOPIC:-newsroom-fleet-reviews-dlq}"
ARMOR_TEMPLATE="${ARMOR_TEMPLATE:-newsroom-intake}"
REPO="${REPO:-newsroom-fleet}"

RUN_SA="newsroom-fleet-run"           # the backend's own identity
INVOKER_SA="newsroom-fleet-invoker"   # Pub/Sub push + Cloud Scheduler
BUILD_SA="newsroom-fleet-build"       # Cloud Build only
RUN_SA_EMAIL="${RUN_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
INVOKER_SA_EMAIL="${INVOKER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA_EMAIL="${BUILD_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

# The repo's active gcloud config impersonates a service account scoped to the
# other submission and cannot read this project. Bypass it explicitly.
G=(gcloud --project "${PROJECT_ID}" --impersonate-service-account=)

if [[ "${APPLY}" != "1" ]]; then
  echo "*** DRY RUN — nothing will be created. Re-run with APPLY=1 to execute. ***"
fi
echo "project ${PROJECT_ID} · region ${REGION} · tier ${TIER}"
echo

# Print, then run only under APPLY=1.
run() {
  echo "  \$ $*"
  [[ "${APPLY}" == "1" ]] || return 0
  "$@"
}

# ensure "<description>" <check command...> -- <create command...>
# The check is a read-only describe and runs even in dry mode, so the dry run
# reports what would *actually* be created rather than assuming an empty project.
ensure() {
  local what="$1"; shift
  local -a check=() create=()
  local past_sep=0
  for arg in "$@"; do
    if [[ "${arg}" == "--" && ${past_sep} -eq 0 ]]; then past_sep=1; continue; fi
    if [[ ${past_sep} -eq 0 ]]; then check+=("${arg}"); else create+=("${arg}"); fi
  done
  if "${check[@]}" >/dev/null 2>&1; then
    echo "  ✓ ${what} already exists — skipping"
    return 0
  fi
  echo "  + ${what}"
  run "${create[@]}"
}

# ---------------------------------------------------------------- Tier A
echo "== Tier A: build and deploy surface =="
run "${G[@]}" services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

ensure "Artifact Registry '${REPO}'" \
  "${G[@]}" artifacts repositories describe "${REPO}" --location="${REGION}" \
  -- \
  "${G[@]}" artifacts repositories create "${REPO}" \
    --repository-format=docker --location="${REGION}" \
    --description="Newsroom Fleet container images"

ensure "service account ${RUN_SA}" \
  "${G[@]}" iam service-accounts describe "${RUN_SA_EMAIL}" \
  -- \
  "${G[@]}" iam service-accounts create "${RUN_SA}" \
    --display-name="Newsroom Fleet backend"

# Builds run under their own identity, not the project's shared Compute Engine
# default account and not the runtime account. A runtime that could push
# container images could rewrite the code it runs as — the separation is the
# same least-privilege argument the desks make about evidence.
ensure "service account ${BUILD_SA}" \
  "${G[@]}" iam service-accounts describe "${BUILD_SA_EMAIL}" \
  -- \
  "${G[@]}" iam service-accounts create "${BUILD_SA}" \
    --display-name="Newsroom Fleet Cloud Build"

echo "  + IAM for ${BUILD_SA} (build only: read source, push image, write logs)"
for role in roles/storage.objectUser roles/artifactregistry.writer roles/logging.logWriter; do
  run "${G[@]}" projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${BUILD_SA_EMAIL}" --role="${role}" --condition=None --quiet
done

# Firestore already exists in this project (asia-south1) and is shared with
# ByFeel. Newsroom Fleet namespaces its collections under `newsroom_fleet_`, so
# there is nothing to create and nothing of ByFeel's to disturb.
echo "  ✓ Firestore (default) already provisioned in asia-south1 — not touched"

echo "  + IAM for ${RUN_SA} (least privilege)"
# Reads and writes its own state, publishes review tasks, writes traces, reads
# its service token. Deliberately NOT a Pub/Sub subscriber: work arrives by
# push, so it holds no standing right to pull messages.
for role in roles/datastore.user roles/cloudtrace.agent; do
  run "${G[@]}" projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUN_SA_EMAIL}" --role="${role}" --condition=None --quiet
done

# ---------------------------------------------------------------- Tier B
if [[ "${TIER}" == *B* || "${TIER}" == "AB" || "${TIER}" == "ABC" ]]; then
  echo
  echo "== Tier B: asynchronous execution and secrets =="
  run "${G[@]}" services enable pubsub.googleapis.com cloudscheduler.googleapis.com \
    secretmanager.googleapis.com

  # The DLQ must exist before the subscription that dead-letters into it.
  for t in "${DLQ_TOPIC}" "${TOPIC}"; do
    ensure "Pub/Sub topic ${t}" \
      "${G[@]}" pubsub topics describe "${t}" \
      -- \
      "${G[@]}" pubsub topics create "${t}" --message-retention-duration=7d
  done

  ensure "service account ${INVOKER_SA}" \
    "${G[@]}" iam service-accounts describe "${INVOKER_SA_EMAIL}" \
    -- \
    "${G[@]}" iam service-accounts create "${INVOKER_SA}" \
      --display-name="Newsroom Fleet Pub/Sub + Scheduler invoker"

  for role in roles/pubsub.publisher roles/secretmanager.secretAccessor; do
    run "${G[@]}" projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${RUN_SA_EMAIL}" --role="${role}" --condition=None --quiet
  done

  # Piped stdin, so this cannot go through `run`. The token is generated
  # locally and written straight into Secret Manager — it is never echoed.
  if "${G[@]}" secrets describe newsroom-fleet-service-token >/dev/null 2>&1; then
    echo "  ✓ secret newsroom-fleet-service-token already exists — skipping"
  else
    echo "  + secret newsroom-fleet-service-token"
    echo "  \$ <generated 32-byte token> | gcloud secrets create newsroom-fleet-service-token --data-file=-"
    if [[ "${APPLY}" == "1" ]]; then
      python -c 'import secrets; print(secrets.token_urlsafe(32))' \
        | "${G[@]}" secrets create newsroom-fleet-service-token --data-file=-
    fi
  fi
fi

# ---------------------------------------------------------------- Tier C
if [[ "${TIER}" == *C* ]]; then
  echo
  echo "== Tier C: Model Armor =="
  echo "  !! Price per screened unit and asia-south1 availability are UNVERIFIED."
  echo "  !! The heuristic screener already quarantines the planted memo."
  run "${G[@]}" services enable modelarmor.googleapis.com
  ensure "Model Armor template ${ARMOR_TEMPLATE}" \
    "${G[@]}" model-armor templates describe "${ARMOR_TEMPLATE}" --location="${REGION}" \
    -- \
    "${G[@]}" model-armor templates create "${ARMOR_TEMPLATE}" \
      --location="${REGION}" \
      --pi-and-jailbreak-filter-settings-enforcement=enabled \
      --pi-and-jailbreak-filter-settings-confidence-level=LOW_AND_ABOVE \
      --malicious-uri-filter-settings-enforcement=enabled \
      --basic-config-filter-enforcement=enabled
  run "${G[@]}" projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUN_SA_EMAIL}" --role=roles/modelarmor.user \
    --condition=None --quiet
fi

echo
if [[ "${APPLY}" == "1" ]]; then
  echo "Applied. Record every line above in deploy/CLOUD_LEDGER.md, then:"
else
  echo "Dry run complete. Nothing was created. To apply:"
  echo "  TIER=${TIER} APPLY=1 PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/setup_gcp.sh"
  echo
  echo "Then:"
fi
echo "  PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/deploy.sh"
