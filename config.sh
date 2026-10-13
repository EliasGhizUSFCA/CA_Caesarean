# =====================================================================
# HW3 shared configuration -- FILL IN THE TODOs
#
# This file is SOURCED by both gcloud_command.sh and test_hw3.sh 
# to set environment variables:
#
#   source "$(dirname "$0")/config.sh"
#
# so you fill these values in ONCE to run the .sh files
# =====================================================================

# TODO 1: your GCP_PROJECT_ID.
PROJECT_ID="some-random-project-data"

# TODO 2: the region to deploy into, e.g. "us-west1". 
# Cloud Run and Cloud Scheduler must be in the same region.
REGION="us-west1"

# TODO 3: absolute path to your .env file. 
# Cloud Run reads this at
# deploy time to set GCP_PROJECT_ID, VERTEX_AI_PROJECT_ID,
# SEARCH_ENGINE_ID, GCP_BUCKET_NAME and GCP_SERVICE_ACCOUNT_KEY 
# inside the containers.
ENV_FILE="/Users/narayanpoudel/Desktop/DSAI/Fall01/data_acquisition/homeworks/homework3/.env"

SCHEDULER_SERVICE_ACCOUNT="example2@some-random-project-data.iam.gserviceaccount.com"

# TODO 4: absolute path to your service account JSON key on your laptop
# (the file GCP_SERVICE_ACCOUNT_KEY points at for local development).
LOCAL_KEY_FILE="/Users/narayanpoudel/.ssh/some-random-project-data-35a8a1c0745e.json"

# TODO 5: the ports your two Dockerfiles EXPOSE. 
# These must match your Dockerfiles exactly.
API_PORT="8000"
WEBAPP_PORT="8501"

# ---------------------------------------------------------------------
# Provided -- no need to change anything below this line.
# ---------------------------------------------------------------------

# Secret Manager holds the key, and we need to mount it.
GCP_KEY_SECRET=hw3-gcp-key
SECRET_MOUNT_PATH=/run/secrets/gcp_key

# Cloud Run service names.
API_SERVICE=hospital-api-server
WEBAPP_SERVICE=hospital-webapp

# Cloud Run service names
API_SERVICE="hospital-api"
WEBAPP_SERVICE="hospital-dashboard"

# Monthly collection schedules
SCHEDULER_TIME_ZONE="America/Los_Angeles"

CMS_SCHEDULER_JOB="collect-cms"
CMS_PATH="/cms-hospitals"
CMS_SCHEDULE="0 6 1 1,4,7,10 *"

HCAI_SCHEDULER_JOB="collect-hcai"
HCAI_PATH="/hcai"
HCAI_SCHEDULE="15 6 1 1,4,7,10 *"

SCRAPE_SCHEDULER_JOB="collect-scraped-hospitals"
SCRAPE_LIMIT="25"
SCRAPE_PATH="/scrape-hospitals"
SCRAPE_SCHEDULE="30 6 1 1,4,7,10 *"


# =====================================================================
# Validation 
# =====================================================================
for _hw3_var in PROJECT_ID REGION ENV_FILE LOCAL_KEY_FILE API_PORT \
                WEBAPP_PORT; do
  if [ -z "${!_hw3_var}" ]; then
    echo "ERROR: $_hw3_var is empty - fill in TODOs in config.sh" \
         "before running this script." >&2
    exit 1
  fi
done
unset _hw3_var

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: ENV_FILE '$ENV_FILE' does not exist." >&2
  exit 1
fi
if [ ! -f "$LOCAL_KEY_FILE" ]; then
  echo "ERROR: LOCAL_KEY_FILE '$LOCAL_KEY_FILE' does not exist." >&2
  exit 1
fi
