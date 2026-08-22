-- Pediatric ENT Surveillance Pipeline — Schema
-- PostgreSQL 16 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- Table 1: creators
-- Tiered watch-list of social media accounts producing ENT-relevant content.
CREATE TABLE creators (
    creator_id          TEXT NOT NULL,           -- Platform-native username or ID
    platform            TEXT NOT NULL,           -- tiktok | instagram | youtube | reddit
    tier                TEXT NOT NULL DEFAULT 'probation', -- core | probation | retired
    seed_category       TEXT,                    -- Why this creator was added (e.g. 'ear_health'); NULL = auto-discovered
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at          TIMESTAMPTZ,             -- Set when tier changes to 'retired'; NULL for active accounts

    PRIMARY KEY (creator_id, platform),
    CONSTRAINT chk_creators_tier CHECK (tier IN ('core', 'probation', 'retired'))
);

CREATE INDEX idx_creators_tier ON creators(tier);

-- Table 2: posts
-- Central fact table for every collected post.
CREATE TABLE posts (
    post_id             TEXT NOT NULL,           -- Platform-native unique post ID
    platform            TEXT NOT NULL,           -- tiktok | instagram | youtube | reddit
    source              TEXT NOT NULL,           -- Collection source (e.g. creator_monitor)
    creator_id          TEXT,                    -- FK to creators
    caption_text        TEXT,                    -- Original text caption of the post
    transcript_text     TEXT,                    -- Audio transcript
    hashtags            JSONB,
    metadata            JSONB NOT NULL DEFAULT '{}', -- Source-specific URLs and discovery provenance
    likes               INTEGER DEFAULT 0,
    comments            INTEGER DEFAULT 0,
    shares              INTEGER DEFAULT 0,
    views               INTEGER DEFAULT 0,
    sbert_score         REAL,                    -- Max cosine similarity vs anchors (gate 3 score)
    matched_anchor_id   INTEGER,                 -- FK to sbert_anchors: which anchor scored highest for this post
    gate4_category      TEXT,                    -- Risk label assigned by agent: HIGH | MODERATE | LOW
    linked_trend_id     TEXT,                    -- FK to trends
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posted_at           TIMESTAMPTZ,             -- Platform publish time

    PRIMARY KEY (post_id, platform),
    CONSTRAINT chk_posts_source CHECK (source IN (
        'creator_monitor', 'engager', 'reddit',
        'explore_feed', 'gtrends_search', 'gdelt_news'))
);

CREATE INDEX idx_posts_collected          ON posts(collected_at);
CREATE INDEX idx_posts_source             ON posts(source);
CREATE INDEX idx_posts_metadata           ON posts USING gin(metadata);
CREATE INDEX idx_posts_gate4_category     ON posts(gate4_category);
CREATE INDEX idx_posts_linked_trend       ON posts(linked_trend_id) WHERE linked_trend_id IS NOT NULL;
CREATE INDEX idx_posts_creator_confirm    ON posts(creator_id, platform) WHERE gate4_category IN ('HIGH', 'MODERATE');
CREATE INDEX idx_posts_matched_anchor     ON posts(matched_anchor_id) WHERE matched_anchor_id IS NOT NULL;

-- Table 3: sbert_anchors
-- Semantic anchors used for pre-filtering (Gate 3).
CREATE TABLE sbert_anchors (
    anchor_id           SERIAL PRIMARY KEY,
    anchor_text         TEXT NOT NULL UNIQUE,    -- Behavioral description used as semantic reference
    embedding           vector(384) NOT NULL,
    source              TEXT NOT NULL,           -- manual | agent_classified | news_extract | bertrend_cluster
    added_by            TEXT,                    -- Script or agent run that added this anchor (e.g. 'cold_start_seed')
    active              BOOLEAN DEFAULT FALSE,   -- Whether this anchor is actively used in gate 3 filtering
    match_count         INTEGER DEFAULT 0,       -- Posts that had this anchor as their best match and passed threshold
    added_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_anchors_active    ON sbert_anchors(active) WHERE active = TRUE;
CREATE INDEX idx_anchors_embedding ON sbert_anchors USING hnsw (embedding vector_cosine_ops);

-- Table 4: trends
-- Detected trends and their lifecycle states.
CREATE TABLE trends (
    trend_id            TEXT PRIMARY KEY,        -- Slug derived from trend name, stable across runs
    label               TEXT NOT NULL,           -- HIGH | MODERATE | LOW
    risk_score          REAL NOT NULL,           -- Computed risk (0.0 to 1.0)
    post_count          INTEGER DEFAULT 0,       -- Total confirmed posts linked to this trend
    platforms           JSONB,                   -- Distinct platforms this trend appears on
    slang_terms         JSONB,                   -- Alternative names and hashtags
    discovery_source    TEXT,                    -- How the trend was initially discovered (e.g. gdelt_news)
    first_detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ,             -- Timestamp when the last post was linked to this trend
    lifecycle_status    TEXT NOT NULL DEFAULT 'Isolated incident', -- Emergence | Growth | Resurfacing | Declining | Latent | Isolated incident
    lifecycle_history   JSONB DEFAULT '[]',      -- Time-series of lifecycle status and post counts: [{"date": "...", "status": "...", "post_count": 0}]
    verification_status TEXT DEFAULT 'PROVISIONAL', -- CONFIRMED | PROVISIONAL | INSUFFICIENT_EVIDENCE
    trend_name          TEXT,                    -- Short 4-5 word trend name
    abstract            TEXT,                    -- LLM classification summary
    search_context      TEXT,                    -- LLM search context
    harm_mechanism      TEXT,                    -- LLM extracted harm mechanism
    evidence            JSONB,                   -- List of relevant academic evidence
    centroid            vector(384),             -- SBERT embedding centroid for cross-run cluster matching

    -- Cluster-level velocity tracking (how fast this trend is spreading)
    velocity_growth_rate    REAL,               -- Posts/day change rate (+ve = rising, -ve = falling)
    velocity_checked_at     TIMESTAMPTZ,        -- When velocity was last computed for this trend
    velocity_next_check_at  TIMESTAMPTZ,        -- When to next compute velocity (default: NOW() + 24h on creation)

    low_confidence          BOOLEAN DEFAULT FALSE, -- Set when self-consistency check disagrees

    CONSTRAINT chk_trends_label CHECK (label IN ('HIGH', 'MODERATE', 'LOW')),
    CONSTRAINT chk_trends_lifecycle CHECK (lifecycle_status IN (
        'Emergence', 'Growth', 'Resurfacing', 'Declining', 'Latent', 'Isolated incident')),
    CONSTRAINT chk_trends_verification CHECK (verification_status IN (
        'CONFIRMED', 'PROVISIONAL', 'INSUFFICIENT_EVIDENCE'))
);

CREATE INDEX idx_trends_lifecycle       ON trends(lifecycle_status);
CREATE INDEX idx_trends_dashboard       ON trends(lifecycle_status, risk_score);
CREATE INDEX idx_trends_centroid        ON trends USING hnsw (centroid vector_cosine_ops);
CREATE INDEX idx_trends_velocity_sched  ON trends(velocity_next_check_at)
    WHERE velocity_next_check_at IS NOT NULL;

-- Table 5: trend_signals
-- Extracted signals that still require a verification workflow (e.g. news matches).
CREATE TABLE trend_signals (
    signal_id           SERIAL PRIMARY KEY,
    signal_type         TEXT NOT NULL,           -- news_match | slow_spread
    signal_data         JSONB NOT NULL DEFAULT '{}',
    search_query        TEXT NOT NULL,           -- Query used to search platforms and verify this signal
    search_platforms    JSONB NOT NULL DEFAULT '["reddit","tiktok","instagram"]',
    search_status       TEXT NOT NULL DEFAULT 'pending',
    linked_trend_id     TEXT REFERENCES trends(trend_id),
    dismissed           BOOLEAN DEFAULT FALSE,   -- TRUE if a clinician dismissed this signal
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_signals_type CHECK (signal_type IN ('news_match', 'slow_spread', 'gt_spike'))
);

CREATE INDEX idx_signals_pending      ON trend_signals(search_status) WHERE search_status = 'pending';
CREATE INDEX idx_signals_type         ON trend_signals(signal_type);
CREATE INDEX idx_signals_trend        ON trend_signals(linked_trend_id) WHERE linked_trend_id IS NOT NULL;
CREATE INDEX idx_signals_dismissed    ON trend_signals(signal_type, dismissed) WHERE dismissed = FALSE;
CREATE INDEX idx_signals_detected     ON trend_signals(detected_at);
CREATE UNIQUE INDEX idx_signals_news_url ON trend_signals(
    (signal_data->>'news_source_url'), search_query
) WHERE signal_type = 'news_match';

-- Table 6: pipeline_state
-- Generic KV store for worker state.
CREATE TABLE pipeline_state (
    state_key           TEXT PRIMARY KEY,        -- Key name for the pipeline state item
    state_value         JSONB NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO pipeline_state (state_key, state_value) VALUES
    ('gdelt_poll', jsonb_build_object('last_url', NULL, 'last_polled_at', NULL))
ON CONFLICT (state_key) DO NOTHING;

INSERT INTO pipeline_state (state_key, state_value) VALUES
    ('subreddit_stats', '{}'::jsonb)
ON CONFLICT (state_key) DO NOTHING;

-- Table 7: agent_runs
-- Stores LangGraph execution stats.
CREATE TABLE agent_runs (
    run_id              TEXT PRIMARY KEY,        -- UUID for this agent run; also used as result folder name
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    REAL,
    status              TEXT NOT NULL DEFAULT 'running', -- running | completed | failed | timeout
    posts_input         INTEGER DEFAULT 0,       -- Number of posts fed into the agent
    clusters_formed     INTEGER DEFAULT 0,       -- Number of topic clusters formed
    trends_classified   INTEGER DEFAULT 0,       -- Number of trends classified (including Low)
    report_markdown     TEXT,                    -- Auto-generated markdown summary of this run
    error_message       TEXT,                    -- Error message if status = 'failed'

    CONSTRAINT chk_agent_status CHECK (status IN ('running', 'completed', 'failed', 'timeout'))
);

CREATE INDEX idx_agent_runs_status  ON agent_runs(status);
CREATE INDEX idx_agent_runs_started ON agent_runs(started_at);

-- Helper Table 1: gdelt_seen_articles
-- URL deduplication for GDELT worker.
CREATE TABLE gdelt_seen_articles (
    url                 TEXT PRIMARY KEY,
    seen_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gdelt_seen_at ON gdelt_seen_articles(seen_at);
