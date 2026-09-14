# Cloud Deployment and Operations Guide

This guide details deploying the ENT Monitor system to Google Cloud Platform across two primary tiers:
1. **Compute Engine VM (`aware-backend`)**: Runs all data ingestion scrapers, spaCy/SBERT preprocessing, the LangGraph multi-agent analysis pipeline, background cron jobs, and the PostgreSQL + pgvector database container.
2. **App Engine Standard (`web`)**: Hosts the Next.js 16 production web dashboard, communicating directly with the backend database.

---

## Cloud Architecture

The cloud infrastructure runs on Google Cloud Platform (Montreal: `northamerica-northeast1`) across two tiers:

```mermaid
flowchart TD
  Users["Clinicians and Analysts"] -->|HTTPS| Web

  subgraph GCP["Google Cloud Platform (GCP)"]
  direction LR
    subgraph AE["App Engine"]
      AESpecs["Specs: 1x F1 Instance<br/>730 hrs/mo (Free Tier)"]
      Web["Next.js 16 Dashboard"]
      API["Backend APIs<br/>TypeScript / Node.js"]
      Web --> API
    end

    subgraph CE["Compute Engine"]
      CESpecs["Specs: N1 g1-small (1 vCPU, 1.7 GB RAM)<br/>100 GB SSD PD<br/>Cost: ~$26/mo"]
      VMAPI["VM Services"]
      Cron["Crontab Schedulers"]
      Pipelines["Python Pipelines"]
      DB[("PostgreSQL 16<br/>+ pgvector")]
      Cron -->|Daily| Pipelines
      Pipelines -->|"Read / Write"| DB
      VMAPI -->|"Read / Write"| DB
    end
    API -->|"HTTPS / External IP"| VMAPI
  end
```
---

## Deployment Specifications and Cost

| Component | Service | Specification | Monthly Cost |
|---|---|---|---|
| Backend VM | Compute Engine | N1 `g1-small` (1 vCPU, 1.7 GB RAM) | $21.76 / mo |
| Boot Disk | Compute Engine | 10 GB Standard Persistent Disk | Included |
| Data Disk | Persistent Disk | 100 GB Standard PD (`/mnt/data`) | $4.40 / mo |
| Dashboard | App Engine | Standard 1x `F1` (730 hrs/mo) | $0.00 / mo |
| **Total Run Rate** | **GCP** | **Autonomous Surveillance Stack** | **$26.16 / month** |

> **Region:** All cloud resources are provisioned in either **Toronto** (`northamerica-northeast2`) or **Montreal** (`northamerica-northeast1`).

- **Sizing Rationale:** `g1-small` ($21.76/mo) provides continuous 24/7 background operation alongside the 100 GB persistent SSD ($4.40/mo). App Engine `F1` running 24/7 (730 hours/month) is fully covered under GCP free tier quota (28 free instance-hours/day, costing $0.00/mo).

---

## Prerequisites

- A Google Cloud Platform account with billing enabled.
- Compute Engine API and App Engine API enabled in your GCP project.
- **Google Cloud Shell** in your web browser (no local CLI installation required). Simply click the **Activate Cloud Shell** icon (`>_`) in the top navigation bar of your GCP project console. Cloud Shell automatically authenticates and binds to your active project.

---

## 1. Compute Engine VM Setup (Backend)

The backend VM runs all scrapers, the AI analysis pipeline, and hosts the PostgreSQL database.

### Create the VM Instance

1. Navigate to **Compute Engine -> VM Instances -> Create Instance** in the GCP Console (or use `gcloud compute instances create`).
2. Configure instance settings according to the decided production specifications:
   - **Name:** `aware-backend`
   - **Region:** `northamerica-northeast1` (Montreal)
   - **Zone:** `northamerica-northeast1-a` (or `northamerica-northeast1-c`)
   - **Machine family:** General Purpose
   - **Series:** N1
   - **Machine type:** `g1-small` (1 vCPU, 1.7 GB RAM) at $21.76/month (or `e2-medium` with 2 vCPU, 4 GB RAM for higher native memory).
   - **Boot disk:** 10 GB Standard Persistent Disk, Debian 12.
   - **Additional disk:** Add a 100 GB Standard Persistent Disk ($4.40/month) to be mounted at `/mnt/data`.

### Format and Mount the Data Disk

Connect to the VM via SSH and mount the 100 GB disk to `/mnt/data`:

```bash
# 1. Identify attached disks
lsblk

# 2. Format the 100 GB disk (ext4, first time only)
sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/sdb

# 3. Create the mount directory
sudo mkdir -p /mnt/data

# 4. Mount the disk with discard and defaults
sudo mount -o discard,defaults /dev/sdb /mnt/data

# 5. Make it survive reboots automatically in /etc/fstab
echo "UUID=$(sudo blkid -s UUID -o value /dev/sdb) /mnt/data ext4 discard,defaults,nofail 0 2" | sudo tee -a /etc/fstab
```

> **Tip:** You can run `lsblk` or `df -h` to verify that the 100 GB disk is mounted at `/mnt/data`. The UUID entry in `/etc/fstab` ensures that Linux automatically mounts this disk on every reboot.

---

## 2. Storage Architecture: `/mnt/data/Ent-Monitor` with `/opt/Ent-Monitor` Symlink

To keep the 10 GB boot disk clean and prevent disk exhaustion, all code, Docker volumes, logs, and package caches reside on the 100 GB persistent SSD (`/mnt/data`). A symbolic link at `/opt/Ent-Monitor` allows commands and scripts referencing `/opt/Ent-Monitor` to operate seamlessly on the persistent disk.

### Step-by-Step Directory Setup

```bash
# 1. Move repository to the 100 GB persistent data disk
sudo mv /opt/Ent-Monitor /mnt/data/

# 2. Create a symlink so /opt/Ent-Monitor points directly to /mnt/data/Ent-Monitor
sudo ln -s /mnt/data/Ent-Monitor /opt/Ent-Monitor

# 3. Set user ownership for your user account
sudo chown -R $USER:$USER /mnt/data/Ent-Monitor
sudo chown -R $USER:$USER /mnt/data

# 4. Clear default root cache and redirect Astral uv cache to the 100 GB data drive
rm -rf ~/.cache/uv
export UV_CACHE_DIR=/mnt/data/uv_cache
mkdir -p $UV_CACHE_DIR
echo "export UV_CACHE_DIR=/mnt/data/uv_cache" >> ~/.bashrc
```

| Path | Type | Underlying Location | Purpose |
|---|---|---|---|
| **`/mnt/data/Ent-Monitor`** | Physical directory | 100 GB Persistent SSD | Active production workspace, Docker data (`postgres_data`), crontab target, and logs |
| **`/opt/Ent-Monitor`** | Symbolic link (`ln -s`) | `/mnt/data/Ent-Monitor` | Direct pointer ensuring `/opt/...` paths execute against the persistent SSD |
| **`/mnt/data/uv_cache`** | Physical directory | 100 GB Persistent SSD | Centralized Python package cache preventing root disk exhaustion |

---

## 3. Automated VM Deployment Script: `deploy_vm.sh`

The [deploy_vm.sh](../../deploy/deploy_vm.sh) shell script automates the complete backend installation in 6 stages:

1. **Installs System Dependencies:** Updates `apt` and installs `docker.io`, `docker-compose`, `python3-pip`, `python3-venv`, `curl`, and `nano`.
2. **Installs Astral uv:** Fetches and installs `uv` to `$HOME/.local/bin/uv`.
3. **Prepares Python Environment:**
   - Routes cache to `/mnt/data/uv_cache` via `export UV_CACHE_DIR=/mnt/data/uv_cache`.
   - Sets network timeout: `export UV_HTTP_TIMEOUT=120`.
   - Executes `uv sync` to install all dependencies from `uv.lock`.
   - Downloads the spaCy English model: `uv run python -m spacy download en_core_web_sm`.
4. **Validates Environment Variables:** Prompts you to paste required API keys into `.env` if not already present.
5. **Starts PostgreSQL Container:** Starts PostgreSQL 16 with pgvector via Docker Compose in `deploy/docker-compose.yml`, initializes [001_schema.sql](../../database/001_schema.sql), and waits for health check completion.
6. **Seeds Database:** Runs [002_seed_anchors.py](../../database/002_seed_anchors.py) (SBERT embeddings) and [003_seed_creators.py](../../database/003_seed_creators.py) (creator watchlist).
7. **Configures Crontab Schedules:** Installs autonomous cron jobs for staggered scraping, preprocessing, analysis, and monitoring.

Run the deployment script:

```bash
cd /opt/Ent-Monitor
git pull
cd /opt/Ent-Monitor/deploy
bash deploy_vm.sh
```

### Automated Crontab Schedule

| Job | UTC Schedule | Script Invoked | Purpose |
|---|---|---|---|
| TikTok Scraper | `00 01 * * *` | `python -m layers.ingestion.orchestrator tiktok` | Staggered ingestion |
| Instagram Scraper | `15 01 * * *` | `python -m layers.ingestion.orchestrator instagram` | Staggered ingestion |
| YouTube Scraper | `30 01 * * *` | `python -m layers.ingestion.orchestrator youtube` | Staggered ingestion |
| Reddit Scraper | `45 01 * * *` | `python -m layers.ingestion.orchestrator reddit` | Staggered ingestion |
| Google Trends | `00 03 * * *` | `python -m layers.ingestion.orchestrator gtrends` | Search interest metrics |
| GDELT News | `00 06 * * *` | `python -m layers.ingestion.orchestrator gdelt` | Global news events |
| Preprocessing | `00 08 * * *` | `python -m layers.preprocess.orchestrator` | Entity extraction & SBERT scoring |
| LangGraph Analysis Loop | `00 12 * * *` | `python -m layers.analysis.core.orchestrator` | OBSERVE -> CLASSIFY -> INVESTIGATE -> VERIFY -> REPORT |
| Velocity Check 1 | `00 17 * * *` | `python jobs/velocity_monitor.py` | 5h post-analysis growth check |
| Velocity Check 2 | `00 22 * * *` | `python jobs/velocity_monitor.py` | 10h post-analysis final velocity check |
| Lifecycle Decay | `00 00 * * *` | `python jobs/lifecycle_monitor.py` | Midnight daily status transitions |

---

## 4. Backend VM Environment Variables (`.env`)

The backend requires a `.env` file in the project root (`/mnt/data/Ent-Monitor/.env` or `/opt/Ent-Monitor/.env`):

| Variable | Required | Description | Example |
|---|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance` |
| `APIFY_TOKEN` | Yes | Apify API token for TikTok, Instagram, and YouTube actors | `apify_api_xxxxxxxxxxxxxxxxxxxx` |
| `REDDIT_CLIENT_ID` | Yes | Reddit OAuth Client ID via PRAW | `xxxxxxxxxxxxxx` |
| `REDDIT_CLIENT_SECRET` | Yes | Reddit OAuth Client Secret | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `REDDIT_USER_AGENT` | Yes | Identifier string for Reddit API requests | `EntMonitor/1.0` |
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4.1 classification and verification | `sk-proj-xxxxxxxxxxxxxxxxxxxx` |
| `HF_TOKEN` | No | HuggingFace token to prevent rate limits on SBERT weight downloads | `hf_xxxxxxxxxxxxxxxxxxxxxxxx` |

---

## 5. GCP Firewall Configuration

In the Google Cloud Console, create a firewall rule allowing incoming PostgreSQL traffic from App Engine:

1. Navigate to **VPC Network -> Firewall -> Create Firewall Rule**.
2. Configure parameters:
   - **Name:** `allow-postgres-external`
   - **Network:** `default`
   - **Targets:** All instances in the network (or target tag `aware-backend`)
   - **Source IPv4 ranges:** `0.0.0.0/0` (or restricted to App Engine egress IP range / Cloud NAT)
   - **Protocols and ports:** Specified protocols and ports: TCP `5432`

| Rule Name | Protocol / Port | Source | Target | Purpose |
|---|---|---|---|---|
| `allow-postgres-external` | TCP 5432 | `0.0.0.0/0` (or App Engine IP range) | `aware-backend` | App Engine dashboard connecting to PostgreSQL |
| `allow-pgadmin-external` (Optional) | TCP 5050 | Admin workstation IP | `aware-backend` | Remote pgAdmin database inspection |

---

## 6. App Engine Setup (Frontend Dashboard)

The frontend is a Next.js 16 application deployed to Google App Engine Standard (Node.js 22 runtime) directly from **Google Cloud Shell** in your web browser.

### Step 1: Clone or Pull Repository in Cloud Shell

Open **Google Cloud Shell** in your browser and clone or update the repository in your Cloud Shell home directory:

```bash
# If cloning for the first time in Cloud Shell:
cd ~
git clone https://github.com/courtotlab/Ent-Monitor
cd Ent-Monitor

# Or if pulling latest updates into an existing clone:
cd ~/Ent-Monitor
git pull
```

> **Tip:** If Git blocks a `git pull` because you have local IP edits in `web/app.yaml`, run `git stash && git pull && git stash pop` to pull safely without losing your configuration.

### Step 2: Configure `web/app.yaml`

Navigate to `web/` and update [web/app.yaml](../../web/app.yaml) with your backend VM external IP:

```bash
cd ~/Ent-Monitor/web
nano app.yaml
```

Update `DATABASE_URL` with your VM external IP:

```yaml
runtime: nodejs22

instance_class: F1

env_variables:
  # Replace <VM_EXTERNAL_IP> with the external IP address of aware-backend
  DATABASE_URL: "postgresql://ent_admin:localdevpassword@<VM_EXTERNAL_IP>:5432/ent_surveillance"

handlers:
  - url: /.*
    script: auto
```

### Step 3: Deploy to App Engine from Cloud Shell

Run the deployment script from the `web/` directory in Cloud Shell:

```bash
cd ~/Ent-Monitor/web
gcloud app deploy app.yaml --quiet
```

App Engine automatically executes `npm install` and `npm run build`. The build process typically takes 2 to 4 minutes.

Once deployment completes, view your live production dashboard:

```bash
gcloud app browse
```

The application is accessible at: `https://<YOUR_PROJECT_ID>.appspot.com`

---

## 7. Post-Reboot Recovery and Operations

If the VM reboots due to maintenance, OS patch updates, or an intentional restart, follow this exact procedure to restore all services and verify data integrity:

### Step 1: Verify the Persistent Data Disk Mount

Check if `/mnt/data` is mounted:

```bash
df -h | grep mnt
```

If the disk is not listed, find the UUID and mount it:

```bash
sudo blkid
sudo mount UUID=$(sudo blkid -s UUID -o value /dev/sdb) /mnt/data
# Or mount directly by device:
# sudo mount /dev/sdb /mnt/data
```

### Step 2: Start the Database Container

The PostgreSQL container runs out of `/mnt/data/Ent-Monitor/deploy` where the persistent 100 GB disk volume (`postgres_data`) resides:

```bash
cd /mnt/data/Ent-Monitor/deploy
sudo docker-compose up -d
```

Verify that the container is healthy:

```bash
sudo docker ps --filter "name=ent-surveillance-db"
```

### Step 3: Verify PostgreSQL Connection and Data Integrity

Wait 10 seconds for the database to complete startup, then verify the connection and post count:

```bash
sleep 10
cd /mnt/data/Ent-Monitor
uv run python -c "import psycopg2; conn = psycopg2.connect('postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance'); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM posts'); print('\nSUCCESS! Total posts in database:', cur.fetchone()[0])"
```

### Step 4: Verify Cron Daemon Status

Confirm that `cron` is active and scheduled jobs are intact:

```bash
sudo systemctl status cron
crontab -l
```

### Step 5: Verify App Engine Dashboard

Open `https://<YOUR_PROJECT_ID>.appspot.com` in your browser. Confirm that the dashboard loads live clusters, velocity sparklines, and clinical verification metrics from the restored database.

---

## Related Documentation

- [Local Development Setup Guide](local.md): Run the full stack locally with Docker and Next.js.
- [Database Schema Reference](../database/schema.md): Complete table schemas, relations, and pgvector indexes.
- [Ingestion Layer Architecture](../architecture/components/ingestion/overview.md): Scraping pipeline design across all platforms.
