# Ent-Monitor Documentation

A real-time surveillance pipeline that monitors social media platforms for emerging **pediatric ENT (Ear, Nose & Throat)** harm trends detecting dangerous challenges, unsafe DIY procedures, and viral misinformation before they cause real-world injury.

---

## Documentation Index

### [Architecture](architecture/)

- [**System Design**](architecture/system-design.md): Global system architecture, infrastructure topology, tier boundaries, and end-to-end data flow.

- **Components**: In-depth architectural design for each pipeline subsystem:
  - [Ingestion Overview](architecture/components/ingestion/overview.md): Unified entry point, staggered execution rationale, and shared DB routing.
    - [Social Media Scrapers](architecture/components/ingestion/social-media.md): TikTok, Instagram, YouTube, and Reddit (creator graph walk, explore feeds, PRAW fallback).
    - [Google Trends](architecture/components/ingestion/google-trends.md): Search volume anomaly detection, rising queries, backoff, and inline social search.
    - [GDELT News](architecture/components/ingestion/gdelt.md): Global news stream, 7-stage filter funnel, spaCy NER, and inline cross-fetch.
    - [Database Operations](architecture/components/ingestion/database.md): Normalized post model, target tables, SQL queries, inputs, and outputs.
  - [Preprocessing Overview](architecture/components/preprocess/overview.md): Quality filter, SBERT semantic gate, and anchor reference system.
    - [Database Operations](architecture/components/preprocess/database.md): Raw SQL for reading unprocessed posts, loading anchors, and writing semantic scores.
  - [Analysis Overview](architecture/components/analysis/overview.md): LangGraph state machine, 10-node routing, intent validation, and `AgentState` schema.
    - [Tools & Evidence Cascade](architecture/components/analysis/tools.md): Authoritative reference for PubMed, DuckDuckGo, Semantic Scholar, and CrossRef tools.
    - [Database Operations](architecture/components/analysis/database.md): Cluster persistence, run tracking, and trend queries.
    - [Analysis Nodes](architecture/components/analysis/nodes/): Dedicated specifications for all 10 agent nodes (`observe`, `classify`, `research`, `verify`, etc.).
  - [Monitoring Overview](architecture/components/monitoring/overview.md): Autonomous background monitoring architecture and daily execution timeline.
    - [Velocity Monitor](architecture/components/monitoring/velocity_monitor.md): Real-time spread tracking, Apify keyword search, and SBERT centroid matching.
    - [Lifecycle Monitor](architecture/components/monitoring/lifecycle_monitor.md): 6 lifecycle stages, state transition matrix, and `lifecycle_history` audit trail.
    - [Database Operations](architecture/components/monitoring/database.md): Raw SQL queries for velocity checks, lifecycle decay evaluation, and status updates.

### [Database](database/)

- [**Schema Reference**](database/schema.md): Authoritative single source of truth for PostgreSQL 16 + pgvector DDL, full table schemas, constraints, and indexes.

### [API](api/)

- [**Endpoints Reference**](api/endpoints.md): Next.js App Engine API routes with underlying SQL queries, HTTP methods, and response schemas.

### [Setup & Operations](setup/)

- [**Local Development Guide**](setup/local.md): Local developer workstation setup for Docker, Python dependencies via `uv`, database seeding, layer execution, and Next.js frontend via `npm` or `bun`.
- [**Cloud Deployment Guide**](setup/cloud.md): Production GCP Compute Engine VM, App Engine Standard, persistent disk mounting, dual-directory (`/opt` vs `/mnt/data`) workflow, automated crontab schedule, and post-reboot recovery.
