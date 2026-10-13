#!/usr/bin/env bash
# =====================================================================
# HW3 -- Cloud Run deployment script (FILL IN THE BLANKS)
#
# This script deploys your containers to Cloud Run in five steps:
#   1. Store the service account key in Secret Manager
#   2. Deploy the FastAPI service
#   3. Read back the FastAPI service's public URL
#   4. Deploy the Streamlit service, pointed at that URL
#   5. Create a Cloud Scheduler job that calls the API every midnight
#
#
# Run it from this directory:
#   bash gcloud_command.sh
# =====================================================================
set -euo pipefail

# =====================================================================
# CONFIGURATION
#
# PROJECT_ID, REGION, ENV_FILE, LOCAL_KEY_FILE, the ports, the service names 
# are defined in config.sh, which you fill in separately. 
# `source` runs that file in this shell to set them.
#
# test_hw3.sh sources the same file.
#
# IMPORTANT : Do not redefine any of those values here.
# =====================================================================
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/config.sh"

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

# Confirm the source directories contain Dockerfiles.
for source_dir in api streamlit; do
  if [ ! -f "$SCRIPT_DIR/$source_dir/Dockerfile" ]; then
    echo "ERROR: Missing $SCRIPT_DIR/$source_dir/Dockerfile" >&2
    exit 1
  fi
done


# Confirm Scheduler's service account exists.

gcloud iam service-accounts describe "$SCHEDULER_SERVICE_ACCOUNT" \
  --project="$PROJECT_ID" >/dev/null

# =====================================================================
# STEP 1 -- put the service account key in Secret Manager.
#
# CloudRun mounts it from Secret Manager at runtime.
# =====================================================================
gcloud services enable \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com

# create secrets if it does not exist.
if ! gcloud secrets describe "$GCP_KEY_SECRET" >/dev/null 2>&1; then
  gcloud secrets create "$GCP_KEY_SECRET" --replication-policy=automatic
fi

# Add a new version of secret.
gcloud secrets versions add "$GCP_KEY_SECRET" --data-file="$LOCAL_KEY_FILE"

# Cloud Run source deploys run as the service account.
# Without secretAccessor on the secret, --set-secrets grants this.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" \
  --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding "$GCP_KEY_SECRET" \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor

# =====================================================================
# STEP 2 -- deploy the FastAPI service.
#
# '--source <dir>' tells Cloud Run to build the Dockerfile in that
# directory with Cloud Build, push the image, and deploy it. 
# =====================================================================
# TODO 6: which directory holds the FastAPI Dockerfile?
# TODO 7: which configuration variable holds the FastAPI port?
# TODO 8: which configuration variable holds the path to your .env file?

DEPLOY_ENV_FILE=$(mktemp)

# Remove the temporary settings file when this script exits.
trap 'rm -f "$DEPLOY_ENV_FILE"' EXIT

python3 - "$ENV_FILE" "$DEPLOY_ENV_FILE" \
  "$PROJECT_ID" "$SECRET_MOUNT_PATH" <<'PY'
import json
import sys

from dotenv import dotenv_values

source_path, output_path, project_id, key_path = sys.argv[1:]
settings = dotenv_values(source_path)

bucket_name = settings.get("GCP_BUCKET_NAME")
if not bucket_name:
    raise SystemExit("ERROR: GCP_BUCKET_NAME is missing from ENV_FILE.")

# Write YAML entries using JSON-quoted strings.
# This avoids copying the laptop credential path into Cloud Run.
deployment_settings = {
    "GCP_PROJECT_ID": project_id,
    "GCP_BUCKET_NAME": bucket_name,
    "GCP_SERVICE_ACCOUNT_KEY": key_path,
}

with open(output_path, "w", encoding="utf-8") as output:
    for name, value in deployment_settings.items():
        output.write(f"{name}: {json.dumps(value)}\n")
PY


gcloud run deploy "$API_SERVICE" \
  --source "$SCRIPT_DIR/api" \
  --region "$REGION" \
  --port="$API_PORT" \
  --allow-unauthenticated \
  --env-vars-file="$DEPLOY_ENV_FILE" \
  --set-secrets="$SECRET_MOUNT_PATH=$GCP_KEY_SECRET:latest"

# --env-vars-file just loaded GCP_SERVICE_ACCOUNT_KEY as the path on YOUR
# laptop, which does not exist inside the container. 
#
# TODO 9: which configuration variable holds the in-container path of
#          the mounted key?
gcloud run services update "$API_SERVICE" \
  --region "$REGION" \
  --update-env-vars=gcp_service_account_key="$SECRET_MOUNT_PATH"

# =====================================================================
# STEP 3 -- read back the API server's public URL (provided).
#
# A Cloud Run service answers on two hostnames: the
# SERVICE-PROJECTNUMBER.REGION.run.app form that 'gcloud run deploy'
# prints as "Service URL", and a SERVICE-HASH-uc.a.run.app alias.
# Both reach the same service, but status.url returns the alias --
# 'urls[0]' is the one the deploy output and the Cloud Console show.
# =====================================================================
API_SERVER_URL=$(gcloud run services describe "$API_SERVICE" \
  --region "$REGION" --format="value(urls[0])")
# Older gcloud releases don't expose 'urls'; fall back to the alias.
if [ -z "$API_SERVER_URL" ]; then
  API_SERVER_URL=$(gcloud run services describe "$API_SERVICE" \
    --region "$REGION" --format="value(status.url)")
fi
# Without this check an empty URL silently propagates into the webapp's
# API_SERVICE_URL and the scheduler's --uri, which would cause errors.
if [ -z "$API_SERVER_URL" ]; then
  echo "ERROR: could not resolve the URL for Cloud Run service" \
       "'$API_SERVICE' in $REGION." >&2
  exit 1
fi
echo "$API_SERVICE deployed at $API_SERVER_URL"

# =====================================================================
# STEP 4 -- deploy the Streamlit service, pointed at the API server.
# =====================================================================
# TODO 10: which directory holds the Streamlit Dockerfile?
# TODO 11: which configuration variable holds the Streamlit port?
gcloud run deploy "$WEBAPP_SERVICE" \
  --source ./streamlit \
  --region "$REGION" \
  --port="$WEBAPP_PORT" \
  --allow-unauthenticated \
  --env-vars-file="$DEPLOY_ENV_FILE" \
  --set-secrets="$SECRET_MOUNT_PATH=$GCP_KEY_SECRET:latest"

# TODO 12: streamlit/user_definition.py exposes API_SERVICE_URL, so the
#          dashboard container gets the API server's address too. Which
#          shell variable set in STEP 3 holds that URL?
#          DO NOT HARDCODE. Cloud Run only assigns the URL once the
#          service exists, which is why STEP 3 reads it back.
gcloud run services update "$WEBAPP_SERVICE" \
  --region "$REGION" \
  --update-env-vars=gcp_service_account_key="$SECRET_MOUNT_PATH",API_SERVICE_URL="$API_SERVER_URL"

WEBAPP_URL=$(gcloud run services describe "$WEBAPP_SERVICE" \
  --region "$REGION" --format="value(urls[0])")
echo "$WEBAPP_SERVICE deployed at $WEBAPP_URL"

# =====================================================================
# STEP 5 -- schedule the daily search.
#
# Cloud Scheduler sends an HTTP POST to the API server's URL on a scheule.
# =====================================================================
# create or update based on whether the job already exists.
if gcloud scheduler jobs describe "$SCHEDULER_JOB" \
     --location="$REGION" >/dev/null 2>&1; then
  SCHEDULER_ACTION=update
else
  SCHEDULER_ACTION=create
fi

# TODO 13: the full URL Cloud Scheduler should POST to. 
#          Combine the API server's URL with the endpoint in
#          fastapi/extract_save_data.py
 gcloud scheduler jobs "$action" http "$job_name" \
    --location="$REGION" \
    --schedule="$schedule" \
    --time-zone="$SCHEDULER_TIME_ZONE" \
    --uri="${API_SERVER_URL}${endpoint}" \
    --http-method=POST \
    --oidc-service-account-email="$SCHEDULER_SERVICE_ACCOUNT" \
    --oidc-token-audience="$API_SERVER_URL" \
    --attempt-deadline=900s


configure_schedule \
  "$CMS_SCHEDULER_JOB" \
  "$CMS_SCHEDULE" \
  "$CMS_PATH"

configure_schedule \
  "$HCAI_SCHEDULER_JOB" \
  "$HCAI_SCHEDULE" \
  "$HCAI_PATH"

configure_schedule \
  "$SCRAPE_SCHEDULER_JOB" \
  "$SCRAPE_SCHEDULE" \
  "$SCRAPE_PATH"

echo
echo "Done."
echo "  API:       $API_SERVER_URL"
echo "  Dashboard: $WEBAPP_URL"
echo "  Scheduler: $SCHEDULER_JOB ($SCHEDULE)"
