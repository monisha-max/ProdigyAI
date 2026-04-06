#!/bin/bash
# ProdigyAI — Cloud SQL Setup Script
# Creates Cloud SQL instance, database, and schema

set -e

echo "========================================="
echo "  ProdigyAI — Cloud SQL Setup"
echo "========================================="

# Get project config
PROJECT_ID=$(gcloud config get-value project)
REGION="${REGION:-us-central1}"
INSTANCE_NAME="${INSTANCE_NAME:-prodigy-ai-instance}"
DB_NAME="prodigyai"
DB_USER="postgres"
DB_PASSWORD="${DB_PASSWORD:-prodigyai123}"

echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Instance: $INSTANCE_NAME"
echo "Database: $DB_NAME"
echo ""

# Enable APIs
echo "[1/6] Enabling required APIs..."
gcloud services enable sqladmin.googleapis.com \
                       aiplatform.googleapis.com \
                       run.googleapis.com \
                       cloudbuild.googleapis.com \
                       --quiet

# Create Cloud SQL instance
echo "[2/6] Creating Cloud SQL PostgreSQL instance (this takes ~5 minutes)..."
gcloud sql instances create $INSTANCE_NAME \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=$REGION \
    --root-password=$DB_PASSWORD \
    --storage-size=10GB \
    --storage-auto-increase \
    --availability-type=zonal \
    --quiet || echo "Instance may already exist, continuing..."

# Enable public IP for testing
echo "[3/6] Enabling public IP access for testing..."
gcloud sql instances patch $INSTANCE_NAME \
    --authorized-networks=0.0.0.0/0 \
    --quiet || echo "Network config may already exist, continuing..."

# Create database
echo "[4/6] Creating database..."
gcloud sql databases create $DB_NAME \
    --instance=$INSTANCE_NAME \
    --quiet || echo "Database may already exist, continuing..."

# Get the instance IP
INSTANCE_IP=$(gcloud sql instances describe $INSTANCE_NAME --format="value(ipAddresses[0].ipAddress)")
echo "Instance IP: $INSTANCE_IP"

# Run schema
echo "[5/6] Running schema setup..."
gcloud sql connect $INSTANCE_NAME --database=$DB_NAME --user=$DB_USER < schema.sql

# Write .env files
echo "[6/6] Writing configuration files..."

cat > ../prodigy_ai/.env << EOF
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GOOGLE_CLOUD_LOCATION=$REGION
EOF

cat > ../.env << EOF
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GOOGLE_CLOUD_LOCATION=$REGION
TOOLBOX_URL=http://127.0.0.1:5000
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=$INSTANCE_IP
DB_NAME=$DB_NAME
EOF

# Update tools.yaml with actual values
sed -i.bak \
    -e "s/\${PROJECT_ID}/$PROJECT_ID/g" \
    -e "s/\${REGION}/$REGION/g" \
    -e "s/\${INSTANCE_NAME}/$INSTANCE_NAME/g" \
    -e "s/\${DB_USER}/$DB_USER/g" \
    -e "s/\${DB_PASSWORD}/$DB_PASSWORD/g" \
    ../tools.yaml
rm -f ../tools.yaml.bak

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Instance IP: $INSTANCE_IP"
echo "Database:    $DB_NAME"
echo "User:        $DB_USER"
echo ""
echo "Next steps:"
echo "  1. cd .."
echo "  2. Download toolbox: curl -O https://storage.googleapis.com/genai-toolbox/v0.23.0/linux/amd64/toolbox && chmod +x toolbox"
echo "  3. Start toolbox:    ./toolbox --tools-file=tools.yaml"
echo "  4. In another terminal: python main.py"
echo ""
echo "IMPORTANT: Remove 0.0.0.0/0 from authorized networks before production!"
