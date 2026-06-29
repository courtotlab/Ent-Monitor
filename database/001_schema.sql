-- ════════════════════════════════════════════════════════════════
-- Pediatric ENT Surveillance Pipeline — Full Schema (v9, local dev)
-- Uses pgvector for sbert_anchors.embedding instead of BYTEA
-- ════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;

-- ───────────────────────────────────────────
-- Table 1: creators
-- ───────────────────────────────────────────
CREATE TABLE creators (
    creator_id          TEXT NOT NULL,
    platform            TEXT NOT NULL,
    tier                TEXT NOT NULL DEFAULT 'core',          -- core | probation | retired
    confirmed_post_ct   INTEGER DEFAULT 0,
    last_confirmed_at   TIMESTAMPTZ,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at          TIMESTAMPTZ,
    reinstated_at       TIMESTAMPTZ,
    reinstatement_layers   TEXT,                                  -- reddit_mention | news_mention
    seed_category       TEXT,                                  -- folk_remedy | asmr_extraction | naturopath | teen_challenge | debunker
    engager_pool_rank   INTEGER,
    pool_valid_until    TIMESTAMPTZ,
    notes               TEXT,
    PRIMARY KEY (creator_id, platform)
);
CREATE INDEX idx_creators_tier ON creators(tier);
CREATE INDEX idx_creators_engager_pool ON creators(engager_pool_rank)
    WHERE engager_pool_rank IS NOT NULL;

-- ───────────────────────────────────────────
-- Table 2: posts
-- ───────────────────────────────────────────
CREATE TABLE posts (
    post_id             TEXT NOT NULL,
    platform            TEXT NOT NULL,                         -- tiktok | instagram | youtube | reddit
    source              TEXT NOT NULL,                         -- creator_monitor | engager_sample | reddit_stream | explore_sample | trend_verification
    context             TEXT NOT NULL,                         -- high | medium | low
    trigger_type        TEXT,                                  -- NULL | gt_spike | news_match
    trigger_query        TEXT,
    priority             TEXT NOT NULL DEFAULT 'standard',      -- high | standard
    creator_id           TEXT,
    creator_tier          TEXT,                                 -- core | probation | retired | null
    creator_follower_ct  INTEGER,
    creator_median_eng   INTEGER,
    creator_median_normalized_eng REAL,
    caption_text         TEXT,
    ocr_text              TEXT,
    transcript_text       TEXT,
    hashtags               JSONB,
    likes                  INTEGER DEFAULT 0,
    comments               INTEGER DEFAULT 0,
    shares                 INTEGER DEFAULT 0,
    views                  INTEGER DEFAULT 0,
    eng_at_hours            INTEGER,
    velocity_ratio          REAL,
    velocity_flag           BOOLEAN DEFAULT FALSE,
    sbert_score              REAL,
    gate4_relevant            BOOLEAN,
    gate4_harm_signal         BOOLEAN,
    gate4_category             TEXT,                            -- ear_remedy | tonsil_procedure | nasal_insertion | challenge_general | discussion | other
    gate4_confidence           REAL,
    gate4_reasoning             TEXT,
    linked_trend_id              TEXT,
    normalized_engagement         REAL,
    collected_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posted_at                      TIMESTAMPTZ,
    PRIMARY KEY (post_id, platform)
);
CREATE INDEX idx_posts_collected      ON posts(collected_at);
CREATE INDEX idx_posts_source         ON posts(source);
CREATE INDEX idx_posts_gate4          ON posts(gate4_relevant, gate4_harm_signal);
CREATE INDEX idx_posts_trigger        ON posts(trigger_type) WHERE trigger_type IS NOT NULL;
CREATE INDEX idx_posts_linked_trend   ON posts(linked_trend_id)
    WHERE linked_trend_id IS NOT NULL;

-- ───────────────────────────────────────────
-- Table 3: velocity_tracking
-- ───────────────────────────────────────────
CREATE TABLE velocity_tracking (
    post_id             TEXT NOT NULL,
    platform            TEXT NOT NULL,
    creator_id          TEXT,
    creator_median_eng  INTEGER,
    creator_median_normalized_eng REAL,
    eng_at_hour_0       INTEGER,
    eng_at_hour_1       INTEGER,
    eng_at_hour_3       INTEGER,
    eng_at_hour_6       INTEGER,
    eng_at_hour_12      INTEGER,
    ratio_at_hour_1     REAL,
    ratio_at_hour_3     REAL,
    ratio_at_hour_6     REAL,
    ratio_at_hour_12    REAL,
    flagged             BOOLEAN DEFAULT FALSE,
    flagged_at_hour     INTEGER,
    retired             BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (post_id, platform),
    FOREIGN KEY (post_id, platform) REFERENCES posts(post_id, platform)
        ON DELETE CASCADE
);
CREATE INDEX idx_velocity_active ON velocity_tracking(retired) WHERE retired = FALSE;

-- ───────────────────────────────────────────
-- Table 4: sbert_anchors  (pgvector instead of BYTEA)
-- ───────────────────────────────────────────
CREATE TABLE sbert_anchors (
    anchor_id           SERIAL PRIMARY KEY,
    anchor_text         TEXT NOT NULL UNIQUE,
    embedding           vector(384) NOT NULL,        -- all-MiniLM-L6-v2 = 384 dims
    source               TEXT NOT NULL,               -- manual | bertrend_cluster | news_extract
    source_cluster_id     TEXT,
    cluster_post_count     INTEGER,
    added_by                TEXT,
    review_status            TEXT DEFAULT 'pending',   -- pending | approved | rejected
    active                    BOOLEAN DEFAULT FALSE,
    added_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at                 TIMESTAMPTZ,
    deactivated_at               TIMESTAMPTZ,
    deactivated_reason            TEXT
);
CREATE INDEX idx_anchors_active ON sbert_anchors(active) WHERE active = TRUE;
CREATE INDEX idx_anchors_review ON sbert_anchors(review_status)
    WHERE review_status = 'pending';
CREATE INDEX idx_anchors_embedding ON sbert_anchors
    USING hnsw (embedding vector_cosine_ops);

-- ───────────────────────────────────────────
-- Table 5: active_trends
-- ───────────────────────────────────────────
CREATE TABLE active_trends (
    trend_id                TEXT PRIMARY KEY,
    label                   TEXT NOT NULL,             -- HARMFUL | CONCERNING | SAFE
    risk_score              REAL NOT NULL,
    post_count              INTEGER DEFAULT 0,
    platforms               JSONB,
    discovery_source        TEXT,                      -- creator_monitor | engager_sample | reddit_stream | gt_spike | news_match | explore_sample
    gt_spike_term            TEXT,
    news_article_title        TEXT,
    first_detected_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at                 TIMESTAMPTZ,
    velocity_posts_hr             REAL,

    lifecycle_status               TEXT NOT NULL DEFAULT 'emergence', -- emergence|growth|peak|decline|dormancy|resurgence
    velocity_trend                  TEXT,                              -- rising|stable|declining
    peak_post_count                  INTEGER DEFAULT 0,
    peak_velocity                      REAL DEFAULT 0,
    peak_reached_at                     TIMESTAMPTZ,
    dormancy_at                           TIMESTAMPTZ,
    resurgence_at                          TIMESTAMPTZ,
    resurgence_count                         INTEGER DEFAULT 0,
    weekly_post_counts                        JSONB DEFAULT '{}',

    verification_status                        TEXT DEFAULT 'monitoring', -- monitoring|confirmed|unverified

    false_positive                               BOOLEAN DEFAULT FALSE,
    fp_suppressed_until                            TIMESTAMPTZ,

    report_version                                  INTEGER DEFAULT 0,
    report_path                                       TEXT
);
CREATE INDEX idx_trends_lifecycle ON active_trends(lifecycle_status);
CREATE INDEX idx_trends_active    ON active_trends(false_positive, lifecycle_status);
CREATE INDEX idx_trends_verified  ON active_trends(verification_status);

-- ───────────────────────────────────────────
-- Table 6: trend_lifecycle_history
-- ───────────────────────────────────────────
CREATE TABLE trend_lifecycle_history (
    history_id          SERIAL PRIMARY KEY,
    trend_id            TEXT NOT NULL REFERENCES active_trends(trend_id),
    event_type          TEXT NOT NULL,   -- post_confirmed | lifecycle_transition | resurgence | false_positive_marked | verification_confirmed | manual_override
    from_status         TEXT,
    to_status           TEXT,
    post_count_at_event INTEGER,
    velocity_at_event   REAL,
    triggered_by        TEXT,            -- gate4 | weekly_job | clinician | dispatcher
    notes               TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_history_trend ON trend_lifecycle_history(trend_id, occurred_at);

-- ───────────────────────────────────────────
-- Table 7: trend_signals
-- ───────────────────────────────────────────
CREATE TABLE trend_signals (
    signal_id               SERIAL PRIMARY KEY,
    signal_type             TEXT NOT NULL,         -- gt_spike | news_match | slow_spread

    gt_term                 TEXT,
    gt_spike_ratio          REAL,
    gt_baseline_value       REAL,
    gt_spike_value          REAL,

    news_source_url         TEXT,
    news_source_name        TEXT,
    news_article_title      TEXT,
    news_article_date       TIMESTAMPTZ,
    news_sbert_score        REAL,
    news_behavioral_extract TEXT,

    slow_spread_weeks       INTEGER,
    slow_spread_total_posts INTEGER,
    slow_spread_creators    INTEGER,
    slow_spread_condition   TEXT,        -- sustained_accumulation | broad_creator_spread

    search_query            TEXT NOT NULL,
    search_platforms        JSONB NOT NULL DEFAULT '["reddit","tiktok","instagram"]',
    search_status           TEXT NOT NULL DEFAULT 'pending',  -- pending|searching|done|failed|monitoring

    geo_region               TEXT,
    posts_collected           INTEGER DEFAULT 0,
    posts_confirmed             INTEGER DEFAULT 0,
    verified                     BOOLEAN DEFAULT FALSE,
    linked_trend_id               TEXT REFERENCES active_trends(trend_id),

    dismissed                     BOOLEAN DEFAULT FALSE,
    dismissed_at                   TIMESTAMPTZ,

    detected_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    search_started_at                 TIMESTAMPTZ,
    search_completed_at                 TIMESTAMPTZ,
    error_msg                             TEXT
);
CREATE INDEX idx_signals_pending  ON trend_signals(search_status) WHERE search_status = 'pending';
CREATE INDEX idx_signals_type     ON trend_signals(signal_type);
CREATE INDEX idx_signals_verified ON trend_signals(verified);
CREATE INDEX idx_signals_trend    ON trend_signals(linked_trend_id)
    WHERE linked_trend_id IS NOT NULL;

-- ───────────────────────────────────────────
-- Table 8: gt_watch_terms
-- ───────────────────────────────────────────
CREATE TABLE gt_watch_terms (
    term_id         SERIAL PRIMARY KEY,
    term_text       TEXT UNIQUE NOT NULL,
    active          BOOLEAN DEFAULT TRUE,
    source          TEXT NOT NULL,         -- manual_seed | gate4_auto
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    last_spiked_at  TIMESTAMPTZ,
    permanent       BOOLEAN DEFAULT FALSE
);

-- ───────────────────────────────────────────
-- Table 9: subreddit_stats
-- ───────────────────────────────────────────
CREATE TABLE subreddit_stats (
    subreddit               TEXT PRIMARY KEY,
    median_post_score_7d    REAL NOT NULL,
    subscriber_count        INTEGER,
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────
-- Table 10: category_weekly_stats
-- ───────────────────────────────────────────
CREATE TABLE category_weekly_stats (
    stat_id             SERIAL PRIMARY KEY,
    gate4_category      TEXT NOT NULL,
    week_label          TEXT NOT NULL,      -- ISO week e.g. '2026-W24'
    post_count          INTEGER NOT NULL,
    unique_creators     INTEGER,
    unique_platforms    INTEGER,
    avg_confidence      REAL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (gate4_category, week_label)
);

-- ════════════════════════════════════════════════════════════════
-- Cold-start seed: manual gt_watch_terms (permanent)
-- ════════════════════════════════════════════════════════════════
INSERT INTO gt_watch_terms (term_text, source, permanent) VALUES
    ('garlic ear infection', 'manual_seed', TRUE),
    ('ear candle wax removal', 'manual_seed', TRUE),
    ('tonsil stone bobby pin', 'manual_seed', TRUE),
    ('onion poultice ear', 'manual_seed', TRUE),
    ('hydrogen peroxide ear cleaning child', 'manual_seed', TRUE)
ON CONFLICT (term_text) DO NOTHING;
