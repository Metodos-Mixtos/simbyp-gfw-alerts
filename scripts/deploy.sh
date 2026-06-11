#!/bin/bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-bosques-bogota-416214}"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-gfw-weekly-alerts}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-gfw-weekly-alerts-trigger}"
REPOSITORY_IMAGE="${REPOSITORY_IMAGE:-gcr.io/${PROJECT_ID}/${JOB_NAME}}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sa-bosques-app@${PROJECT_ID}.iam.gserviceaccount.com}"
INSTANCE_CONNECTION_NAME="${INSTANCE_CONNECTION_NAME:-${PROJECT_ID}:us-central1:simbyp-users-db}"

# Weekly schedule: Mondays 8:00 AM Bogota
SCHEDULE="${SCHEDULE:-0 8 * * 1}"
TIME_ZONE="${TIME_ZONE:-America/Bogota}"

# Runtime settings
CPU="${CPU:-1}"
MEMORY="${MEMORY:-2Gi}"
TASK_TIMEOUT="${TASK_TIMEOUT:-30m}"
MAX_RETRIES="${MAX_RETRIES:-2}"

# Non-secret env vars used by the pipeline
OUTPUTS_BASE_PATH="${OUTPUTS_BASE_PATH:-gs://reportes-simbyp/reportes_gfw}"
INPUTS_PATH="${INPUTS_PATH:-gs://material-estatico-sdp/SIMBYP_DATA}"
GCP_PROJECT_VALUE="${GCP_PROJECT_VALUE:-${PROJECT_ID}}"

echo "=========================================="
echo "Deploying SIMBYP GFW Alerts Cloud Run Job"
echo "=========================================="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Job: ${JOB_NAME}"
echo "Image: ${REPOSITORY_IMAGE}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo "Cloud SQL Instance: ${INSTANCE_CONNECTION_NAME}"
echo ""

echo "1) Setting gcloud project..."
gcloud config set project "${PROJECT_ID}"

echo "2) Building container image..."
gcloud builds submit --tag "${REPOSITORY_IMAGE}" .

echo "3) Creating or updating Cloud Run Job..."
if gcloud run jobs describe "${JOB_NAME}" --region "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  ACTION="update"
  GCLOUD_JOB_CMD="update"
else
  ACTION="create"
  GCLOUD_JOB_CMD="create"
fi

echo "   Job action: ${ACTION}"
gcloud run jobs "${GCLOUD_JOB_CMD}" "${JOB_NAME}" \
  --image "${REPOSITORY_IMAGE}" \
  --region "${REGION}" \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --max-retries "${MAX_RETRIES}" \
  --task-timeout "${TASK_TIMEOUT}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --add-cloudsql-instances "${INSTANCE_CONNECTION_NAME}" \
  --set-secrets GFW_USERNAME=GFW_USERNAME:latest,GFW_PASSWORD=GFW_PASSWORD:latest,ALIAS=ALIAS:latest,EMAIL=EMAIL:latest,ORG=ORG:latest,DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars OUTPUTS_BASE_PATH="${OUTPUTS_BASE_PATH}",INPUTS_PATH="${INPUTS_PATH}",GCP_PROJECT="${GCP_PROJECT_VALUE}" \
  --project "${PROJECT_ID}"

echo "4) Ensuring invoker permission for service account..."
gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --region "${REGION}" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role "roles/run.invoker" \
  --project "${PROJECT_ID}" >/dev/null

echo "5) Creating or updating Cloud Scheduler trigger..."
SCHEDULER_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

if gcloud scheduler jobs describe "${SCHEDULER_JOB_NAME}" --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_JOB_NAME}" \
    --location "${REGION}" \
    --schedule "${SCHEDULE}" \
    --time-zone "${TIME_ZONE}" \
    --uri "${SCHEDULER_URI}" \
    --http-method POST \
    --oauth-service-account-email "${SERVICE_ACCOUNT}" \
    --project "${PROJECT_ID}"
else
  gcloud scheduler jobs create http "${SCHEDULER_JOB_NAME}" \
    --location "${REGION}" \
    --schedule "${SCHEDULE}" \
    --time-zone "${TIME_ZONE}" \
    --uri "${SCHEDULER_URI}" \
    --http-method POST \
    --oauth-service-account-email "${SERVICE_ACCOUNT}" \
    --project "${PROJECT_ID}"
fi

echo "6) Deployment summary"
echo "   Cloud Run Job: ${JOB_NAME}"
echo "   Scheduler Job: ${SCHEDULER_JOB_NAME}"
echo "   Execute now: gcloud run jobs execute ${JOB_NAME} --region ${REGION} --project ${PROJECT_ID}"
echo ""
echo "Deployment completed successfully!"