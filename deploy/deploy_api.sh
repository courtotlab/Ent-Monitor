#!/bin/bash
set -e

echo "Deploying FastAPI Backend to App Engine..."

# 1. Navigate to project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD/..")
cd "$PROJECT_ROOT"

# Ensure uv is installed (useful for Cloud Shell)
if ! command -v uv &> /dev/null; then
    echo "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Export dependencies for App Engine (requires requirements.txt)
echo "Exporting uv dependencies to requirements.txt..."
uv pip compile pyproject.toml -o requirements.txt

# 3. Enable Required Google Cloud APIs
echo "Ensuring required GCP APIs are enabled..."
gcloud services enable artifactregistry.googleapis.com cloudbuild.googleapis.com

# 4. Deploy
echo "Deploying to App Engine..."
# Copy app.yaml to root so gcloud uploads the whole repository, not just the deploy/ folder
cp deploy/app.yaml ./app.yaml
gcloud app deploy app.yaml --quiet
rm ./app.yaml

echo "API Deployment complete!"
