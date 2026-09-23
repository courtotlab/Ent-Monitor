import asyncio
import os
import random
import logging
import gc

from apify import Actor
from psycopg2.extras import Json
from trendspyg import download_google_trends_explore, download_google_trends_rss

from layers.ingestion.shared.queries import (
  fetch_sbert_anchors_with_source,
  get_recent_gt_spikes,
  insert_gt_spike,
  insert_post,
)
from layers.ingestion.social.instagram import scrape_instagram_search
from layers.ingestion.social.tiktok import scrape_tiktok_search
from layers.preprocess.semantic_filter import SbertFilter
from layers.shared.trends import make_trend_id

logger = logging.getLogger(__name__)

SBERT_GT_THRESHOLD = 0.35

async def run_google_trends_worker():
  logger.info("Starting Google Trends worker")
  client = Actor.new_client(token=os.getenv("APIFY_TOKEN")) if os.getenv("APIFY_TOKEN") else None

  # Phase 1: Fetch Trends (Lightweight Network)
  try:
    top_20_trends = download_google_trends_rss(geo="US", normalize=True).get("trends", [])[:20]
  except Exception as e:
    logger.error(f"Failed to fetch Google Trends RSS: {e}"); return
  logger.info(f"Fetched {len(top_20_trends)} trending terms from RSS")

  recently_processed = get_recent_gt_spikes([t for tt in top_20_trends if (t := tt.get("keyword"))]) if top_20_trends else set()

  all_enriched, consecutive_failures = [], 0
  for trend in top_20_trends:
    if consecutive_failures >= 3: break
    if (title := trend.get("keyword", "")) in recently_processed: continue

    try:
      logger.info(f"Explore: fetching related queries for '{title}'...")
      rising_queries = [r["query"] for r in download_google_trends_explore(title, geo="US").get("related_queries", {}).get("rising", [])]
      all_enriched.append({"trend_title": title, "traffic": trend.get("volume_text", ""), "rising_queries": rising_queries})
      consecutive_failures = 0
      await asyncio.sleep(random.uniform(12, 20))
    except Exception as e:
      consecutive_failures += 1
      if "429" in str(e) or "rate" in str(e).lower(): await asyncio.sleep(random.uniform(60, 120))
      else: await asyncio.sleep(15)

  # Phase 2: NLP Filtering (Heavy CPU/RAM)
  logger.info("Phase 2: Loading SBERT for query filtering")
  sbert = SbertFilter()
  sbert.load_anchors(fetch_sbert_anchors_with_source())

  passed_count, dispatched_count = 0, 0
  trends_to_scrape = []

  for item in all_enriched:
    title, rising_queries = item["trend_title"], item["rising_queries"]
    if not rising_queries: continue

    passed_queries = sorted([{"query": q, "score": s} for q, s in zip(rising_queries, sbert.score_texts(rising_queries)) if s >= SBERT_GT_THRESHOLD], key=lambda x: -x["score"])
    if not passed_queries: continue

    passed_count += 1
    try:
      insert_gt_spike(Json({"gt_term": title, "gt_traffic": item.get("traffic"), "gt_rising_queries": passed_queries}), make_trend_id(title))
      dispatched_count += 1
      trends_to_scrape.append(title)
    except Exception as e:
      logger.error(f"DB insert failed for '{title}': {e}")
      continue

  # Free Memory!
  logger.info("Freeing SBERT from memory before Apify scrape")
  del sbert
  gc.collect()

  # Phase 3: Social Media Scraping (Heavy Network Wait)
  all_posts = []
  if client and trends_to_scrape:
    logger.info(f"Phase 3: Scraping {len(trends_to_scrape)} passed trends via Apify")
    tasks = []
    for title in trends_to_scrape:
      tasks.append(scrape_tiktok_search(client, [title], limit_posts=5, source="gtrends_search"))
      tasks.append(scrape_instagram_search(client, [title], limit_posts=5, source="gtrends_search"))
    
    try:
      results = await asyncio.gather(*tasks, return_exceptions=True)
      for idx, r in enumerate(results):
        if isinstance(r, Exception):
          logger.error(f"Inline Apify task {idx} failed: {r}")
        elif isinstance(r, list):
          all_posts.extend([p.to_dict() for p in r])
    except Exception as e:
      logger.error(f"Inline Apify gather failed: {e}")

  # Phase 4: Final NLP Processing
  if all_posts:
    logger.info("Phase 4: Loading SBERT again for post filtering")
    sbert = SbertFilter()
    sbert.load_anchors(fetch_sbert_anchors_with_source())
    
    post_scores = sbert.score_texts([(p.get("caption_text") or "") + " " + (p.get("transcript_text") or "") for p in all_posts])
    inserted = sum(1 for post, score in zip(all_posts, post_scores) if (post.update({"source": "gtrends_search"}) or True) and insert_post(post, float(score)))
    logger.info(f"  -> Saved {inserted} new posts into DB from {len(trends_to_scrape)} trends")
    
    del sbert
    gc.collect()

  logger.info(f"DONE | {len(top_20_trends)} checked | {passed_count} passed | {dispatched_count} dispatched")

if __name__ == "__main__":
  asyncio.run(run_google_trends_worker())
