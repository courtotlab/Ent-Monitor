#!/bin/bash
set -e

echo "Deploying Next.js Web Frontend to App Engine..."

# 1. Navigate to project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD/..")
cd "$PROJECT_ROOT/web"

# Ensure bun is installed (useful for Cloud Shell)
if ! command -v bun &> /dev/null; then
    echo "bun not found, installing..."
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
fi

# 2. Install and Build
echo "Installing dependencies and building Next.js..."
bun install
bun run build

# 3. Deploy
echo "Deploying to App Engine..."
gcloud app deploy app.yaml --quiet

echo "Web Deployment complete!"
