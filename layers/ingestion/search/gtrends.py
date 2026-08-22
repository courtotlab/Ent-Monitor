import asyncio
import os
import random

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

SBERT_GT_THRESHOLD = 0.35

async def run_google_trends_worker():
  print("Starting Google Trends worker")
  client = Actor.new_client(token=os.getenv("APIFY_TOKEN")) if os.getenv("APIFY_TOKEN") else None

  sbert = SbertFilter()
  sbert.load_anchors(fetch_sbert_anchors_with_source())

  try:
    top_20_trends = download_google_trends_rss(geo="US", normalize=True).get("trends", [])[:20]
  except Exception as e:
    print(f"Failed to fetch Google Trends RSS: {e}"); return
  print(f"Fetched {len(top_20_trends)} trending terms from RSS")

  recently_processed = get_recent_gt_spikes([t for tt in top_20_trends if (t := tt.get("keyword"))]) if top_20_trends else set()

  all_enriched, consecutive_failures = [], 0
  for trend in top_20_trends:
    if consecutive_failures >= 3: break
    if (title := trend.get("keyword", "")) in recently_processed: continue

    try:
      print(f"Explore: fetching related queries for '{title}'...")
      rising_queries = [r["query"] for r in download_google_trends_explore(title, geo="US").get("related_queries", {}).get("rising", [])]
      all_enriched.append({"trend_title": title, "traffic": trend.get("volume_text", ""), "rising_queries": rising_queries})
      consecutive_failures = 0
      await asyncio.sleep(random.uniform(12, 20))
    except Exception as e:
      consecutive_failures += 1
      if "429" in str(e) or "rate" in str(e).lower(): await asyncio.sleep(random.uniform(60, 120))
      else: await asyncio.sleep(15)

  passed_count, dispatched_count = 0, 0
  for item in all_enriched:
    title, rising_queries = item["trend_title"], item["rising_queries"]
    if not rising_queries: continue

    passed_queries = sorted([{"query": q, "score": s} for q, s in zip(rising_queries, sbert.score_texts(rising_queries)) if s >= SBERT_GT_THRESHOLD], key=lambda x: -x["score"])
    if not passed_queries: continue

    passed_count += 1
    try:
      insert_gt_spike(Json({"gt_term": title, "gt_traffic": item.get("traffic"), "gt_rising_queries": passed_queries}), title, make_trend_id(title))
      dispatched_count += 1
    except Exception as e:
      print(f"DB insert failed for '{title}': {e}")
      continue

    if client:
      try:
        results = await asyncio.gather(scrape_tiktok_search(client, [title], limit_posts=5, source="gtrends_search"), scrape_instagram_search(client, [title], limit_posts=5, source="gtrends_search"), return_exceptions=True)
        if all_posts := [p.to_dict() for r in results if isinstance(r, list) for p in r]:
          post_scores = sbert.score_texts([(p.get("caption_text") or "") + " " + (p.get("transcript_text") or "") for p in all_posts])
          inserted = sum(1 for post, score in zip(all_posts, post_scores) if (post.update({"source": "gtrends_search"}) or True) and insert_post(post, float(score)))
          print(f"  -> Saved {inserted} new posts into DB for '{title}'")
      except Exception as e:
        print(f"Inline Apify fetch failed for '{title}': {e}")

  print(f"DONE | {len(top_20_trends)} checked | {passed_count} passed | {dispatched_count} dispatched")

if __name__ == "__main__":
  asyncio.run(run_google_trends_worker())
