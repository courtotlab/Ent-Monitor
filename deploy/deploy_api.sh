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

# 3. Deploy
echo "Deploying to App Engine..."
gcloud app deploy deploy/app.yaml --quiet

echo "API Deployment complete!"
