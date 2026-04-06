#!/bin/bash
# ProdigyAI — Cloud Run Deployment Script
set -e

echo "========================================="
echo "  ProdigyAI — Cloud Run Deployment"
echo "========================================="

PROJECT_ID=$(gcloud config get-value project)
REGION="${REGION:-us-central1}"
INSTANCE_NAME="${INSTANCE_NAME:-prodigy-ai-instance}"
SERVICE_NAME="prodigy-ai"

# Get Cloud SQL connection name
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --format="value(connectionName)")
echo "Cloud SQL Connection: $CONNECTION_NAME"

# Get the default VPC network and subnet
NETWORK="${NETWORK:-default}"
SUBNET="${SUBNET:-default}"

echo "Deploying to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""

# Build and deploy
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region=$REGION \
    --allow-unauthenticated \
    --port=8080 \
    --memory=1Gi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=1,TOOLBOX_URL=http://127.0.0.1:5000" \
    --network=$NETWORK \
    --subnet=$SUBNET \
    --vpc-egress=all-traffic

# Grant Cloud Run service account AlloyDB/Cloud SQL access
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

echo ""
echo "Granting IAM roles to service account: $SA"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA" \
    --role="roles/cloudsql.client" --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA" \
    --role="roles/aiplatform.user" --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo ""
echo "========================================="
echo "  Deployment Complete!"
echo "========================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
echo "IMPORTANT: Remove 0.0.0.0/0 from Cloud SQL authorized networks!"
echo "  gcloud sql instances patch $INSTANCE_NAME --clear-authorized-networks"
