-- Pediatric ENT Surveillance Pipeline — Schema
-- PostgreSQL 16 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- Table 1: creators
-- Tiered watch-list of social media accounts producing ENT-relevant content.
CREATE TABLE creators (
    creator_id          TEXT NOT NULL,           -- Platform-native username or ID
    platform            TEXT NOT NULL,           -- Platform name (tiktok, instagram, etc)           -- tiktok | instagram | youtube | reddit
    tier                TEXT NOT NULL DEFAULT 'probation', -- core | probation | retired
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- When the creator was first added to the DB
    retired_at          TIMESTAMPTZ,             -- When the creator was demoted to retired tier
    seed_category       TEXT,                    -- Nullable; auto-discovered if NULL

    PRIMARY KEY (creator_id, platform),
    CONSTRAINT chk_creators_tier CHECK (tier IN ('core', 'probation', 'retired'))
);

CREATE INDEX idx_creators_tier ON creators(tier);

-- Table 2: posts
-- Central fact table for every collected post.
CREATE TABLE posts (
    post_id             TEXT NOT NULL,           -- Platform-native unique post ID
    platform            TEXT NOT NULL,           -- Platform name (tiktok, instagram, etc)
    source              TEXT NOT NULL,           -- Collection source (e.g. creator_monitor)
    creator_id          TEXT,                    -- FK to creators
    caption_text        TEXT,                    -- Original text caption of the post
    transcript_text     TEXT,                    -- Combined OCR/audio transcript
    hashtags            JSONB,
    likes               INTEGER DEFAULT 0,       -- Number of likes on the post
    comments            INTEGER DEFAULT 0,       -- Number of comments on the post
    shares              INTEGER DEFAULT 0,       -- Number of shares of the post
    views               INTEGER DEFAULT 0,       -- Number of views/plays of the post
    normalized_engagement REAL,                  -- Computed engagement ratio
    velocity_active      BOOLEAN DEFAULT FALSE,  -- True if the post is actively monitored for engagement spikes
    velocity_growth_rate REAL,                   -- Engagement growth per hour
    velocity_next_check_at TIMESTAMPTZ,          -- Timestamp when the post should be re-queried for velocity
    sbert_score         REAL,                    -- Max cosine similarity vs anchors
    gate4_relevant      BOOLEAN,                 -- Agent determination on ENT relevance
    gate4_category      TEXT,                    -- Categorization by agent
    linked_trend_id     TEXT,                    -- FK to active_trends
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Timestamp when our system scraped the post
    posted_at           TIMESTAMPTZ,             -- Platform publish time

    PRIMARY KEY (post_id, platform),
    CONSTRAINT chk_posts_source CHECK (source IN (
        'creator_monitor', 'engager_sample', 'reddit_stream',
        'explore_sample', 'trend_verification', 'reddit_json'))
);

CREATE INDEX idx_posts_collected          ON posts(collected_at);
CREATE INDEX idx_posts_source             ON posts(source);
CREATE INDEX idx_posts_velocity_schedule  ON posts(velocity_next_check_at) WHERE velocity_active = TRUE;
CREATE INDEX idx_posts_gate4              ON posts(gate4_relevant);
CREATE INDEX idx_posts_gate4_category     ON posts(gate4_category) WHERE gate4_relevant = TRUE;
CREATE INDEX idx_posts_linked_trend       ON posts(linked_trend_id) WHERE linked_trend_id IS NOT NULL;
CREATE INDEX idx_posts_creator_confirm    ON posts(creator_id, platform) WHERE gate4_relevant = TRUE;
CREATE INDEX idx_posts_engagement_floor   ON posts(normalized_engagement) WHERE normalized_engagement IS NOT NULL AND normalized_engagement >= 0.05;

-- Table 3: sbert_anchors
-- Semantic anchors used for pre-filtering (Gate 3).
CREATE TABLE sbert_anchors (
    anchor_id           SERIAL PRIMARY KEY,      -- Unique identifier for the anchor
    anchor_text         TEXT NOT NULL UNIQUE,    -- Behavioral description
    embedding           vector(384) NOT NULL,
    source              TEXT NOT NULL,           -- manual | agent_classified | news_extract | bertrend_cluster
    added_by            TEXT,                    -- System or script that added the anchor
    active              BOOLEAN DEFAULT FALSE,   -- Whether this anchor is actively used in gate 3 filtering
    match_count         INTEGER DEFAULT 0,       -- Total matches used as relevance signal
    added_at            TIMESTAMPTZ NOT NULL DEFAULT NOW() -- Timestamp when the anchor was created
);

CREATE INDEX idx_anchors_active    ON sbert_anchors(active) WHERE active = TRUE;
CREATE INDEX idx_anchors_embedding ON sbert_anchors USING hnsw (embedding vector_cosine_ops);

-- Table 4: active_trends
-- Detected trends and their lifecycle states.
CREATE TABLE active_trends (
    trend_id            TEXT PRIMARY KEY,        -- Unique string ID for the trend
    label               TEXT NOT NULL,           -- HARMFUL | CONCERNING | SAFE
    risk_score          REAL NOT NULL,           -- Computed risk (0.0 to 1.0)
    post_count          INTEGER DEFAULT 0,       -- Total confirmed posts for this trend
    platforms           JSONB,                   -- Platforms this trend appears on
    discovery_source    TEXT,                    -- How the trend was initially discovered (e.g. gt_spike)
    first_detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ,             -- Timestamp when the last post was added to this trend
    lifecycle_status    TEXT NOT NULL DEFAULT 'emergence',
    weekly_post_counts  JSONB DEFAULT '{}',      -- Rolling window stats
    verification_status TEXT DEFAULT 'confirmed', -- confirmed | monitoring | unverified
    false_positive      BOOLEAN DEFAULT FALSE,   -- Flag indicating if human marked this trend as false positive
    fp_suppressed_until TIMESTAMPTZ,             -- Timestamp until which this false positive trend is hidden
    report_version      INTEGER DEFAULT 0,       -- Auto-incrementing version of reports generated for this trend

    CONSTRAINT chk_trends_label CHECK (label IN ('HARMFUL', 'CONCERNING', 'SAFE')),
    CONSTRAINT chk_trends_lifecycle CHECK (lifecycle_status IN (
        'emergence', 'growth', 'peak', 'decline', 'dormancy', 'resurgence')),
    CONSTRAINT chk_trends_verification CHECK (verification_status IN (
        'monitoring', 'confirmed', 'unverified'))
);

CREATE INDEX idx_trends_lifecycle ON active_trends(lifecycle_status);
CREATE INDEX idx_trends_dashboard ON active_trends(false_positive, lifecycle_status, risk_score);

-- Table 5: trend_lifecycle_history
-- Immutable event log for trend state transitions.
CREATE TABLE trend_lifecycle_history (
    history_id          SERIAL PRIMARY KEY,      -- Unique ID for the history log entry
    trend_id            TEXT NOT NULL REFERENCES active_trends(trend_id),
    event_type          TEXT NOT NULL,           -- The type of lifecycle event
    from_status         TEXT,                    -- Previous lifecycle status before transition
    to_status           TEXT,                    -- New lifecycle status after transition
    post_count_at_event INTEGER,                 -- Number of posts in the trend when this event occurred
    triggered_by        TEXT,                    -- What triggered the event (agent, weekly_job, clinician)
    notes               TEXT,                    -- Optional human-readable notes about the transition
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_history_trend ON trend_lifecycle_history(trend_id, occurred_at);

-- Table 6: trend_signals
-- Extracted signals (e.g. Google Trends spikes, news matches).
CREATE TABLE trend_signals (
    signal_id           SERIAL PRIMARY KEY,      -- Unique ID for the extracted signal
    signal_type         TEXT NOT NULL,           -- gt_spike | news_match | slow_spread
    signal_data         JSONB NOT NULL DEFAULT '{}',
    search_query        TEXT NOT NULL,           -- Query to be searched to verify this signal
    search_platforms    JSONB NOT NULL DEFAULT '["reddit","tiktok","instagram"]',
    search_status       TEXT NOT NULL DEFAULT 'pending',
    posts_collected     INTEGER DEFAULT 0,       -- Number of posts collected during verification
    posts_confirmed     INTEGER DEFAULT 0,       -- Number of posts confirmed relevant by agent
    verified            BOOLEAN DEFAULT FALSE,   -- True if the signal was successfully verified as an active trend
    linked_trend_id     TEXT REFERENCES active_trends(trend_id), -- Associated trend ID if verified
    dismissed           BOOLEAN DEFAULT FALSE,   -- True if a clinician dismissed this signal
    dismissed_at        TIMESTAMPTZ,             -- Timestamp when the signal was dismissed
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    search_started_at   TIMESTAMPTZ,             -- Timestamp when the verification search started
    search_completed_at TIMESTAMPTZ,             -- Timestamp when the verification search finished
    error_msg           TEXT,                    -- Any error message encountered during verification

    CONSTRAINT chk_signals_type CHECK (signal_type IN ('gt_spike', 'news_match', 'slow_spread'))
);

CREATE INDEX idx_signals_pending      ON trend_signals(search_status) WHERE search_status = 'pending';
CREATE INDEX idx_signals_type         ON trend_signals(signal_type);
CREATE INDEX idx_signals_trend        ON trend_signals(linked_trend_id) WHERE linked_trend_id IS NOT NULL;
CREATE INDEX idx_signals_dismissed    ON trend_signals(signal_type, dismissed) WHERE dismissed = FALSE;
CREATE INDEX idx_signals_detected     ON trend_signals(detected_at);
CREATE INDEX idx_signals_news_url     ON trend_signals((signal_data->>'news_source_url'), detected_at) WHERE signal_type = 'news_match';
CREATE INDEX idx_signals_gt_dedup     ON trend_signals(search_query, detected_at) WHERE signal_type = 'gt_spike';

-- Table 7: pipeline_state
-- Generic KV store for worker state.
CREATE TABLE pipeline_state (
    state_key           TEXT PRIMARY KEY,        -- The key name for the pipeline state item
    state_value         JSONB NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO pipeline_state (state_key, state_value) VALUES
    ('gdelt_poll', jsonb_build_object('last_url', NULL, 'last_polled_at', NULL))
ON CONFLICT (state_key) DO NOTHING;

INSERT INTO pipeline_state (state_key, state_value) VALUES
    ('subreddit_stats', '{}'::jsonb)
ON CONFLICT (state_key) DO NOTHING;

-- Table 8: agent_runs
-- Stores LangGraph execution stats.
CREATE TABLE agent_runs (
    run_id              TEXT PRIMARY KEY,        -- Unique UUID for the agent run
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,             -- Timestamp when the agent run finished
    duration_seconds    REAL,                    -- Execution time of the agent run in seconds
    status              TEXT NOT NULL DEFAULT 'running',
    posts_input         INTEGER DEFAULT 0,       -- Number of posts fed into the agent for classification
    clusters_formed     INTEGER DEFAULT 0,       -- Number of topic clusters formed during the run
    trends_classified   INTEGER DEFAULT 0,       -- Number of trends classified during the run
    token_usage         JSONB,                   -- LLM API token usage statistics for the run
    report_markdown     TEXT,                    -- Generated markdown report text of the run results
    error_message       TEXT,                    -- Error message if the run failed

    CONSTRAINT chk_agent_status CHECK (status IN ('running', 'completed', 'failed', 'timeout'))
);

CREATE INDEX idx_agent_runs_status  ON agent_runs(status);
CREATE INDEX idx_agent_runs_started ON agent_runs(started_at);

-- Table 9: agent_actions
-- Granular audit trail for AI tool calls.
CREATE TABLE agent_actions (
    action_id           BIGSERIAL PRIMARY KEY,   -- Unique auto-incrementing ID for the tool call
    run_id              TEXT NOT NULL REFERENCES agent_runs(run_id),
    node_name           TEXT NOT NULL,           -- Name of the agent node (e.g. DECIDE)
    tool_name           TEXT NOT NULL,           -- Name of the tool called
    tool_input          JSONB,                   -- Input arguments passed to the tool
    tool_output         TEXT,                    -- Output returned from the tool
    called_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_actions_run      ON agent_actions(run_id, called_at);
CREATE INDEX idx_actions_tool     ON agent_actions(tool_name);

-- Helper Table 1: gdelt_seen_articles
-- URL deduplication for GDELT worker.
CREATE TABLE gdelt_seen_articles (
    url                 TEXT PRIMARY KEY,
    seen_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gdelt_seen_at ON gdelt_seen_articles(seen_at);
