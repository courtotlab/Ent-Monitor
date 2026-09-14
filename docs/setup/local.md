# Local Development Setup Guide

This guide walks through configuring and running the entire ENT Monitor system locally, including the PostgreSQL database with pgvector, the Python backend pipelines (ingestion, preprocessing, LangGraph agentic loop, and monitoring), and the Next.js 16 web dashboard.

---

## Prerequisites

Ensure the following tools are installed on your workstation:

| Tool | Minimum Version | Installation Reference | Purpose |
|---|---|---|---|
| Git | 2.x+ | [git-scm.com](https://git-scm.com/) | Version control and repository management |
| Docker & Docker Compose | 24.x+ | [docker.com](https://www.docker.com/) | Containerized PostgreSQL and pgvector database |
| Python | 3.12+ | [python.org](https://www.python.org/) | Backend runtime environment |
| Astral uv | 0.4+ | [astral.sh/uv](https://astral.sh/uv/) | Fast Python package and environment manager |
| Node.js & npm (or Bun) | Node 18+ (20+ recommended) or Bun 1.x+ | [nodejs.org](https://nodejs.org/) / [bun.sh](https://bun.sh/) | Next.js frontend runtime and package manager |

Install Astral uv if not already present:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

If using Bun instead of Node.js / npm:

```bash
# macOS / Linux
curl -fsSL https://bun.sh/install | bash

# Windows (PowerShell)
powershell -c "irm bun.sh/install.ps1 | iex"
```

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/courtotlab/Ent-Monitor
cd Ent-Monitor
```

---

## Step 2: Environment Configuration

Create a `.env` file in the project root directory (`Ent-Monitor/.env`):

```bash
cp .env.example .env
```

### Required Configuration Keys

| Variable | Required | Description | Example / Default |
|---|---|---|---|
| `DATABASE_URL` | Yes | Connection string to the local PostgreSQL database | `postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance` |
| `APIFY_TOKEN` | Yes | API token for Apify actors (TikTok, Instagram, YouTube) | `apify_api_xxxxxxxxxxxxxxxxxxxx` |
| `REDDIT_CLIENT_ID` | Yes | Reddit application client ID (script type via PRAW) | `xxxxxxxxxxxxxx` |
| `REDDIT_CLIENT_SECRET` | Yes | Reddit application client secret | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `REDDIT_USER_AGENT` | Yes | User agent identifier for Reddit API requests | `EntMonitor/1.0` |
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4.1 classification and verification | `sk-proj-xxxxxxxxxxxxxxxxxxxx` |
| `HF_TOKEN` | No | HuggingFace user token to avoid rate limits on model downloads | `hf_xxxxxxxxxxxxxxxxxxxxxxxx` |

### Sample Local `.env`

```env
DATABASE_URL=postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance
APIFY_TOKEN=apify_api_your_token_here
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=EntMonitor/1.0
OPENAI_API_KEY=sk-proj-your_openai_api_key
```

---

## Step 3: Start the Database Container

The local database runs in Docker using [docker-compose.yml](../../deploy/docker-compose.yml). It starts:
- PostgreSQL 16 with the `pgvector` extension on port `5432`.
- Schema initialization: Docker automatically executes [001_schema.sql](../../database/001_schema.sql) from the `database/` directory on first startup.
- pgAdmin 4 web administration interface on port `5050`.

Start the containers in detached mode:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Wait 5 to 10 seconds for PostgreSQL initialization, then verify container health:

```bash
docker ps --filter "name=ent-surveillance-db"
```

To connect via pgAdmin:
- URL: `http://localhost:5050`
- Email: `admin@local.dev`
- Password: `admin`
- Database host: `postgres` (internal Docker network) or `localhost` (if connecting from host)
- Port: `5432`
- User: `ent_admin`
- Password: `localdevpassword`

---

## Step 4: Python Environment and Database Seeding

Install all Python dependencies and download the spaCy English NLP model using `uv`:

```bash
# Install dependencies from pyproject.toml / uv.lock
uv sync

# Download the spaCy language model for clinical NER extraction
uv run python -m spacy download en_core_web_sm
```

### Seed Anchors and Watchlist

Seed the database with pre-computed SBERT medical anchor embeddings and the curated creator watchlist:

```bash
# 1. Seed clinical anchor embeddings for semantic similarity scoring
uv run python database/002_seed_anchors.py

# 2. Seed curated medical creator accounts for targeted ingestion
uv run python database/003_seed_creators.py
```

Verify that the tables contain data:

```bash
uv run python -c "import psycopg2; conn = psycopg2.connect('postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance'); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM anchors'); print('Anchors seeded:', cur.fetchone()[0]); cur.execute('SELECT COUNT(*) FROM creator_watchlist'); print('Creators seeded:', cur.fetchone()[0]); conn.close()"
```

---

## Step 5: Running Backend Pipeline Layers

You can invoke each pipeline layer individually to ingest, preprocess, analyze, or monitor trends.

### 1. Ingestion Layer

Collect raw social media and news content into the `raw_posts` and `posts` tables:

```bash
# Ingest from TikTok via Apify
uv run python -m layers.ingestion.orchestrator tiktok

# Ingest from Instagram via Apify
uv run python -m layers.ingestion.orchestrator instagram

# Ingest from YouTube via Apify
uv run python -m layers.ingestion.orchestrator youtube

# Ingest from Reddit via PRAW
uv run python -m layers.ingestion.orchestrator reddit

# Ingest Google Trends search metrics
uv run python -m layers.ingestion.orchestrator gtrends

# Ingest news articles from GDELT
uv run python -m layers.ingestion.orchestrator gdelt
```

### 2. Preprocessing Layer

Clean raw text, extract medical entities with spaCy, compute SBERT vector embeddings (`all-MiniLM-L6-v2`), and calculate similarity scores against clinical anchors:

```bash
uv run python -m layers.preprocess.orchestrator
```

### 3. Analysis Layer (LangGraph Multi-Agent Loop)

Execute the full agentic loop across pending clusters (OBSERVE intent validation, CLASSIFY medical taxonomy, INVESTIGATE clinical evidence retrieval, VERIFY claims, and REPORT alert generation):

```bash
uv run python -m layers.analysis.core.orchestrator
```

### 4. Velocity and Lifecycle Monitoring Jobs

Track emergent growth velocity and update trend lifecycle stages:

```bash
# Run velocity check (searches Apify, computes SBERT cosine similarity, logs growth metrics)
uv run python jobs/velocity_monitor.py

# Run lifecycle decay check (evaluates 6 stages: Emergence, Growth, Resurfacing, Declining, Latent, Isolated incident)
uv run python jobs/lifecycle_monitor.py
```

---

## Step 6: Running the Web Dashboard

The frontend is a Next.js 16 application with Tailwind CSS, React 19, and Radix UI components located in the `web/` directory. You can run the dashboard using either **npm** or **bun**.

### 1. Install Dependencies

Using npm:

```bash
cd web
npm install
```

Using Bun:

```bash
cd web
bun install
```

### 2. Configure Local Frontend Environment

Create a `.env.local` file inside the `web/` folder pointing to your local PostgreSQL instance:

```bash
# web/.env.local
DATABASE_URL="postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance"
```

### 3. Start Development Server

Using npm:

```bash
npm run dev
```

Using Bun:

```bash
bun dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. The dashboard connects to your local database and displays live surveillance metrics, trend clusters, clinical verification scores, and alert feeds.

---

## Troubleshooting Local Setup

### Port 5432 Already in Use

If a native PostgreSQL service is already running on your host:
1. Stop the local PostgreSQL service (`sudo systemctl stop postgresql` on Linux or via Windows Services).
2. Or remap the host port in `deploy/docker-compose.yml` (for example, `"5433:5432"`) and update `DATABASE_URL` in `.env` and `web/.env.local`.

### Resetting Local Database

To wipe all data and start from a clean state:

```bash
# Stop containers and delete named volumes
docker compose -f deploy/docker-compose.yml down -v

# Remove local volume directory if present
rm -rf deploy/postgres_data

# Re-launch and re-seed
docker compose -f deploy/docker-compose.yml up -d
sleep 10
uv run python database/002_seed_anchors.py
uv run python database/003_seed_creators.py
```

### Clean Python Environment

If dependencies become desynchronized:

```bash
uv cache clean
uv sync --refresh
```

---

## Related Documentation

- [Cloud Deployment Guide](cloud.md): Instructions for provisioning Google Compute Engine VM and App Engine Standard.
- [Database Schema Reference](../database/schema.md): Detailed database tables, indexes, and constraints.
- [Analysis Layer Architecture](../architecture/components/analysis/overview.md): Deep dive into the LangGraph multi-agent analysis loop.
