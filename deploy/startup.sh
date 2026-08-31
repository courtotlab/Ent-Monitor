#!/bin/bash
set -e

# 1. System Dependencies
echo -e "\n[1/5] Installing system dependencies and Docker..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv docker.io docker-compose curl nano

# 2. Install uv
echo -e "\n[2/5] Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 3. Virtual Environment
echo -e "\n[3/5] Setting up Python dependencies..."
# Navigate to the project root (assuming startup.sh is run from the project root or deployment folder)
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD/..")
cd "$PROJECT_ROOT"

# Increase network timeout and explicitly route cache to the 100GB drive
export UV_HTTP_TIMEOUT=120
export UV_CACHE_DIR=/mnt/data/uv_cache
mkdir -p $UV_CACHE_DIR
uv sync

# 4. Environment Variables
echo -e "\n[4/5] Checking .env configuration..."
if [ ! -f .env ]; then
  echo ".env file not found! Opening nano so you can paste your API keys..."
  sleep 2
  nano .env
else
  echo ".env file found."
fi

# 5. Database Setup
echo -e "\n[5/6] Spinning up Docker containers..."
cd deploy
sudo docker-compose up -d

echo "Waiting for PostgreSQL to initialize..."
sleep 20

# 6. Seed Database
echo "Seeding database with anchors and creators..."
cd "$PROJECT_ROOT"
$HOME/.local/bin/uv run python database/002_seed_anchors.py
$HOME/.local/bin/uv run python database/003_seed_creators.py

echo -e "\n[6/6] Configuring Background Jobs (Crontab)..."

# Create a temporary crontab file
CRON_FILE=$(mktemp)

# Write out current crontab
crontab -l > $CRON_FILE 2>/dev/null || true

# Add jobs if they don't exist
if ! grep -q "layers.ingestion.orchestrator" "$CRON_FILE"; then
  # --- SOCIAL MEDIA INGESTION: 01:00 UTC (staggered to avoid overlap) ---
  echo "0 1 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator tiktok >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE
  echo "15 1 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator instagram >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE
  echo "30 1 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator youtube >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE
  echo "45 1 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator reddit >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE

  # --- GOOGLE TRENDS INGESTION: 03:00 UTC ---
  echo "0 3 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator gtrends >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE

  # --- GDELT NEWS INGESTION: 06:00 UTC ---
  echo "0 6 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.ingestion.orchestrator gdelt >> $PROJECT_ROOT/layers/ingestion/ingestion.log 2>&1" >> $CRON_FILE
fi

if ! grep -q "preprocess.orchestrator" "$CRON_FILE"; then
  # --- PREPROCESSING: 08:00 UTC ---
  echo "0 8 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.preprocess.orchestrator >> $PROJECT_ROOT/layers/preprocess/preprocess.log 2>&1" >> $CRON_FILE
fi

if ! grep -q "analysis.core.orchestrator" "$CRON_FILE"; then
  # --- FULL AGENTIC LOOP: 12:00 UTC ---
  echo "0 12 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python -m layers.analysis.core.orchestrator >> $PROJECT_ROOT/layers/analysis/analysis.log 2>&1" >> $CRON_FILE
fi

if ! grep -q "velocity_monitor.py" "$CRON_FILE"; then
  # Check 1: 5 hours after agentic loop (12:00 UTC + 5h = 17:00 UTC)
  echo "0 17 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python jobs/velocity_monitor.py >> $PROJECT_ROOT/jobs/velocity.log 2>&1" >> $CRON_FILE
  # Check 2: 10 hours after agentic loop (12:00 UTC + 10h = 22:00 UTC) → deactivates should_monitor after this
  echo "0 22 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python jobs/velocity_monitor.py >> $PROJECT_ROOT/jobs/velocity.log 2>&1" >> $CRON_FILE
fi

if ! grep -q "lifecycle_monitor.py" "$CRON_FILE"; then
  # Lifecycle decay check: midnight UTC every day
  echo "0 0 * * * cd $PROJECT_ROOT && $HOME/.local/bin/uv run python jobs/lifecycle_monitor.py >> $PROJECT_ROOT/jobs/lifecycle.log 2>&1" >> $CRON_FILE
fi

# Install new cron file
crontab $CRON_FILE
rm $CRON_FILE

echo -e "\n Setup Complete! Database: 5432, pgAdmin: 5050."
echo "Background ingestion and monitoring jobs have been added to crontab."
