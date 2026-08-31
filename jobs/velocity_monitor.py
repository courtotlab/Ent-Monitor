from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import numpy as np
from sentence_transformers import SentenceTransformer

from layers.analysis.db.queries import (
  fetch_trends_to_monitor,
  update_trend_velocity_monitor,
)

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s | %(name)-36s | %(levelname)-7s | %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Tunables 
SBERT_MODEL_NAME = "all-MiniLM-L6-v2" 
SIMILARITY_THRESHOLD = 0.75
MAX_AGE_DAYS = 14

# Velocity monitor runs exactly TWICE per trend after an agentic run:
#   Check 1: at the ~5th hour  → see if it's spreading fast
#   Check 2: at the ~10th hour → final check; then should_monitor is set to FALSE


# Apify config - set in .env
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")


# ─ Apify keyword search stub ─

import asyncio
from apify_client import ApifyClientAsync
from layers.ingestion.social.tiktok import scrape_tiktok_search
from layers.ingestion.social.instagram import scrape_instagram_search

async def keyword_search(
  keywords: list[str],
  since: datetime,
) -> list[dict]:
  """Search for new posts matching the given keywords using Apify."""
  if not APIFY_API_TOKEN:
    logger.warning("APIFY_API_TOKEN not set - running in stub mode (returns empty).")
    return []

  client = ApifyClientAsync(APIFY_API_TOKEN)
  tasks = [
    scrape_tiktok_search(client, keywords, 50, "velocity_monitor"),
    scrape_instagram_search(client, keywords, 50, "velocity_monitor")
  ]
    
  posts = []
  for res in await asyncio.gather(*tasks, return_exceptions=True):
    if isinstance(res, Exception): continue
    for p in res:
      if p.posted_at and datetime.fromisoformat(p.posted_at.replace("Z", "+00:00")) < since:
        continue
      posts.append({"caption_text": p.caption_text, "platform": p.platform})
  return posts


# Core logic

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
  norm_a = np.linalg.norm(a)
  norm_b = np.linalg.norm(b)
  if norm_a == 0 or norm_b == 0:
    return 0.0
  return float(np.dot(a, b) / (norm_a * norm_b))


def _age_days(ts: datetime) -> float:
  if ts is None:
    return 0.0
  if ts.tzinfo is None:
    ts = ts.replace(tzinfo=UTC)
  return (datetime.now(UTC) - ts).total_seconds() / 86400.0



async def run_velocity_monitor() -> int:
  """Run one pass of the velocity monitor. Returns number of trends processed."""
  trends = fetch_trends_to_monitor()
  if not trends:
    logger.info("Velocity monitor: no trends flagged for monitoring - exiting.")
    return 0

  logger.info("Velocity monitor: checking %d monitored trends...", len(trends))

  sbert_model = SentenceTransformer(SBERT_MODEL_NAME)

  processed = 0

  for trend in trends:
    trend_id = trend["trend_id"]
    keywords = trend["slang_terms"]
    centroid = np.array(trend["centroid"], dtype=np.float32)
    first_detected = trend.get("first_detected_at")
    check_count = trend.get("velocity_check_count", 0)

    # Stop condition: age cap 
    if _age_days(first_detected) > MAX_AGE_DAYS:
      logger.info("Trend %s exceeded %d-day age cap - deactivating.", trend_id, MAX_AGE_DAYS)
      update_trend_velocity_monitor(
        trend_id=trend_id,
        new_posts_count=0,
        growth_rate=trend["growth_rate"],
        deactivate=True,
      )
      processed += 1
      continue

    # Fetch new posts via Apify 
    new_posts = await keyword_search(
      keywords=keywords,
      since=datetime.now(UTC) - timedelta(hours=5),
    )

    # SBERT-encode + centroid similarity filter 
    matched: list[dict] = []
    if new_posts:
      texts = [(p.get("caption_text") or "").strip() for p in new_posts]
      embeddings = sbert_model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
      )
      for post, emb in zip(new_posts, embeddings):
        if _cosine_similarity(emb, centroid) >= SIMILARITY_THRESHOLD:
          matched.append(post)

    hours_elapsed = 5.0
    growth_rate = len(matched) / hours_elapsed

    if matched:
      logger.info(
        "Trend %s (%s): +%d matching posts | rate=%.2f/h",
        trend_id, trend.get("trend_name", ""), len(matched), growth_rate,
      )
    else:
      logger.info("Trend %s: 0 matching posts this check.", trend_id)

    # Hard stop after exactly 2 fetches (5th and 10th hour check)
    should_deactivate = (check_count >= 1)
    if should_deactivate:
      logger.info("Trend %s reached maximum 2 checks - deactivating velocity monitor.", trend_id)

    update_trend_velocity_monitor(
      trend_id=trend_id,
      new_posts_count=len(matched),
      growth_rate=growth_rate,
      deactivate=should_deactivate,
    )
    processed += 1

  return processed


if __name__ == "__main__":
  count = asyncio.run(run_velocity_monitor())
  print(f"\nVelocity monitor completed. Processed {count} trends.")
