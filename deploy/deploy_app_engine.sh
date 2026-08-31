#!/bin/bash
set -e

echo "Deploying Next.js Web Frontend to App Engine..."

# 1. Navigate to project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD/..")
cd "$PROJECT_ROOT/web"

# 2. Deploy to App Engine (Google will automatically run npm install and npm run build)
echo "Deploying to App Engine..."
gcloud app deploy app.yaml --quiet

echo "Web Deployment complete!"
