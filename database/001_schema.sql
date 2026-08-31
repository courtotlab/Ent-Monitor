-- Pediatric ENT Surveillance Pipeline — Schema
-- PostgreSQL 16 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- Table 1: creators
-- Watch-list of social media accounts producing ENT-relevant content.
CREATE TABLE creators (
    creator_id          TEXT NOT NULL,           -- Platform-native username or ID
    platform            TEXT NOT NULL,           -- tiktok | instagram | youtube | reddit

    PRIMARY KEY (creator_id, platform)
);

-- Table 2: posts
-- Central fact table for every collected post.
CREATE TABLE posts (
    post_id             TEXT NOT NULL,           -- Platform-native unique post ID
    platform            TEXT NOT NULL,           -- tiktok | instagram | youtube | reddit
    source              TEXT NOT NULL,           -- Collection source (e.g. creator_monitor)
    creator_id          TEXT,                    -- FK to creators
    caption_text        TEXT,                    -- Original text caption of the post
    transcript_text     TEXT,                    -- Audio transcript
    url                 TEXT,                    -- Direct link to the source post (TikTok/IG/YouTube video, Reddit thread)
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
CREATE INDEX idx_posts_linked_trend       ON posts(linked_trend_id) WHERE linked_trend_id IS NOT NULL;

-- Table 3: sbert_anchors
-- Semantic anchors used for pre-filtering (Gate 3).
CREATE TABLE sbert_anchors (
    anchor_id           SERIAL PRIMARY KEY,
    anchor_text         TEXT NOT NULL UNIQUE,    -- Behavioral description used as semantic reference
    embedding           vector(384) NOT NULL,
    source              TEXT NOT NULL,           -- manual | news_outcome
    active              BOOLEAN DEFAULT TRUE,    -- Whether this anchor is actively used in gate 3 filtering
    match_count         INTEGER DEFAULT 0,       -- Posts that had this anchor as their best match and passed threshold
    CONSTRAINT chk_sbert_source CHECK (source IN ('manual', 'news_outcome'))
);

CREATE INDEX idx_anchors_active    ON sbert_anchors(active) WHERE active = TRUE;

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
    last_verified_at    TIMESTAMPTZ,             -- When the agent last ran full classification for this trend (fast-path merges do NOT refresh this)
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
    should_monitor          BOOLEAN DEFAULT FALSE,  -- TRUE for HIGH/MODERATE trends actively being monitored
    velocity_growth_rate    REAL,               -- Posts/hour change rate (+ve = rising, -ve = falling)
    velocity_check_count    INTEGER DEFAULT 0,  -- Number of times velocity monitor has checked this (max 3)


    CONSTRAINT chk_trends_label CHECK (label IN ('HIGH', 'MODERATE', 'LOW')),
    CONSTRAINT chk_trends_lifecycle CHECK (lifecycle_status IN (
        'Emergence', 'Growth', 'Resurfacing', 'Declining', 'Latent', 'Isolated incident')),
    CONSTRAINT chk_trends_verification CHECK (verification_status IN (
        'CONFIRMED', 'PROVISIONAL', 'INSUFFICIENT_EVIDENCE'))
);

CREATE INDEX idx_trends_centroid        ON trends USING hnsw (centroid vector_cosine_ops);

-- Table 5: trend_signals
-- Unverified external signals (news/trends) and accumulated early-warning noise posts.
CREATE TABLE trend_signals (
    signal_id           SERIAL PRIMARY KEY,
    signal_type         TEXT NOT NULL,           -- news_match | gt_spike | early_warning
    signal_data         JSONB NOT NULL DEFAULT '{}',
    search_platforms    JSONB NOT NULL DEFAULT '["reddit","tiktok","instagram"]',
    search_status       TEXT NOT NULL DEFAULT 'pending',
    linked_trend_id     TEXT REFERENCES trends(trend_id),
    dismissed           BOOLEAN DEFAULT FALSE,   -- TRUE if a clinician dismissed this signal
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_signals_type CHECK (signal_type IN ('news_match', 'gt_spike', 'early_warning'))
);

CREATE INDEX idx_signals_pending      ON trend_signals(search_status) WHERE search_status = 'pending';
CREATE INDEX idx_signals_type         ON trend_signals(signal_type);
CREATE INDEX idx_signals_trend        ON trend_signals(linked_trend_id) WHERE linked_trend_id IS NOT NULL;
CREATE INDEX idx_signals_dismissed    ON trend_signals(signal_type, dismissed) WHERE dismissed = FALSE;
CREATE INDEX idx_signals_detected     ON trend_signals(detected_at);
CREATE UNIQUE INDEX idx_signals_news_url ON trend_signals(
    (signal_data->>'news_source_url')
) WHERE signal_type = 'news_match';
CREATE UNIQUE INDEX idx_signals_ew_post_id ON trend_signals(
    (signal_data->>'post_id')
) WHERE signal_type = 'early_warning';

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


-- Helper Table 1: gdelt_seen_articles
-- URL deduplication for GDELT worker.
CREATE TABLE gdelt_seen_articles (
    url                 TEXT PRIMARY KEY,
    seen_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gdelt_seen_at ON gdelt_seen_articles(seen_at);
