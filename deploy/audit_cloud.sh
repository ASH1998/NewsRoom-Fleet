#!/usr/bin/env bash
# Read-only inventory of everything Newsroom Fleet owns in the project.
#
# Creates nothing, changes nothing, costs nothing. Use it to reconcile
# deploy/CLOUD_LEDGER.md against what actually exists.
#
#   PROJECT_ID=… ./deploy/audit_cloud.sh
set -uo pipefail

PROJECT_ID="${PROJECT_ID:-$(grep -m1 '^PROJECT_ID=' "$(dirname "${BASH_SOURCE[0]}")/../.env" 2>/dev/null | cut -d= -f2)}"
: "${PROJECT_ID:?set PROJECT_ID or put it in .env}"

# The repo's active gcloud config impersonates a service account scoped to the
# other project, which cannot read this one. Bypass impersonation explicitly.
G=(gcloud --project "${PROJECT_ID}" --impersonate-service-account=)

echo "Project: ${PROJECT_ID}"
echo "Billing: $("${G[@]}" billing projects describe "${PROJECT_ID}" \
  --format='value(billingEnabled,billingAccountName)' 2>/dev/null || echo 'unreadable')"
echo

echo "== Enabled APIs (billable surface) =="
"${G[@]}" services list --enabled --format='value(config.name)' 2>/dev/null \
  | grep -E '^(run|firestore|pubsub|modelarmor|aiplatform|cloudtrace|cloudscheduler|secretmanager|artifactregistry|cloudbuild)\.' \
  | sort || echo "  (none readable)"
echo

echo "== Cloud Run services =="
"${G[@]}" run services list --format='table(metadata.name,status.url,spec.template.metadata.annotations["autoscaling.knative.dev/minScale"]:label=MIN)' 2>/dev/null \
  | grep -i newsroom || echo "  none"
echo

echo "== Artifact Registry repositories =="
"${G[@]}" artifacts repositories list --format='table(name,format,sizeBytes)' 2>/dev/null \
  | grep -i newsroom || echo "  none"
echo

echo "== Pub/Sub topics and subscriptions =="
"${G[@]}" pubsub topics list --format='value(name)' 2>/dev/null | grep -i newsroom || echo "  no topics"
"${G[@]}" pubsub subscriptions list --format='value(name)' 2>/dev/null | grep -i newsroom || echo "  no subscriptions"
echo

echo "== Cloud Scheduler jobs =="
"${G[@]}" scheduler jobs list --location="${REGION:-asia-south1}" --format='value(name,schedule,state)' 2>/dev/null \
  | grep -i newsroom || echo "  none"
echo

echo "== Model Armor templates =="
"${G[@]}" model-armor templates list --location="${REGION:-asia-south1}" --format='value(name)' 2>/dev/null \
  | grep -i newsroom || echo "  none"
echo

echo "== Service accounts =="
"${G[@]}" iam service-accounts list --format='value(email)' 2>/dev/null \
  | grep -i newsroom || echo "  none"
echo

echo "== Secrets =="
"${G[@]}" secrets list --format='value(name)' 2>/dev/null | grep -i newsroom || echo "  none"
echo

echo "== Firestore =="
"${G[@]}" firestore databases list --format='value(name,locationId,type)' 2>/dev/null || echo "  unreadable"
echo "  (Newsroom Fleet uses collections prefixed 'newsroom_fleet_'; ByFeel's data is untouched.)"
