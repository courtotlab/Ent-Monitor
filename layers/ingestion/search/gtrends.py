import asyncio
import json
import os
import random

from apify import Actor
from psycopg2.extras import Json
from trendspyg import download_google_trends_explore, download_google_trends_rss

from layers.ingestion.social.instagram import scrape_instagram_search
from layers.ingestion.social.tiktok import scrape_tiktok_search
from layers.preprocess.queries import insert_post
from layers.preprocess.semantic_filter import SbertFilter
from layers.shared.db import get_connection
from layers.shared.trends import make_trend_id

SBERT_GT_THRESHOLD = 0.35


async def run_google_trends_worker():
  """
  Preprocessing Stages for Google Trends:
  - Stage 1 (Anchors): Load active SBERT anchors from the database.
  - Stage 2 (Fetch): Get Top 20 trending terms from US Google Trends RSS.
  - Stage 3 (Explore): Extract rising related queries for each trend, with deduplication.
  - Stage 4 (SBERT): Score the rising queries against danger/health anchors using SBERT.
  - Stage 5 (Dispatch): Insert trends passing the threshold into the database.
  - Stage 6 (Social): Optionally fetch and score recent TikTok/Instagram posts.
  """
  print("Starting Google Trends worker")

  apify_token = os.getenv("APIFY_TOKEN")
  client = Actor.new_client(token=apify_token) if apify_token else None

  # 1. Load DB anchors
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT embedding, source FROM sbert_anchors WHERE active = TRUE")
    anchors_raw = cur.fetchall()

  if not anchors_raw:
    print("No active SBERT anchors found.")
    return

  parsed_anchors = []
  for emb, source in anchors_raw:
    emb_list = json.loads(emb) if isinstance(emb, str) else emb
    parsed_anchors.append((source, emb_list))

  sbert = SbertFilter()
  sbert.load_anchors(parsed_anchors)

  # 2. Get Google Trends Top 20
  try:
    env = download_google_trends_rss(geo="US", normalize=True)
    trends = env.get("trends", [])
  except Exception as e:
    print(f"Failed to fetch Google Trends RSS: {e}")
    return

  # Take the top 20 trends
  top_20_trends = trends[:20]
  print(f"Fetched {len(top_20_trends)} trending terms from RSS")

  # 3. Extract related queries for all top 20 using Explore
  all_enriched = []
  consecutive_failures = 0

  trend_titles = [t.get("keyword", "") for t in top_20_trends if t.get("keyword")]
  
  if trend_titles:
    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
        """
          SELECT search_query FROM trend_signals
            WHERE search_query = ANY(%s)
              AND signal_type = 'gt_spike'
              AND dismissed = FALSE
              AND detected_at >= NOW() - INTERVAL '7 days'
        """,
        (trend_titles,),
      )
      recently_processed = {row[0] for row in cur.fetchall()}
  else:
    recently_processed = set()

  for trend in top_20_trends:
    title = trend.get("keyword", "")

    if consecutive_failures >= 3:
      print("3 consecutive Explore failures - stopping Explore calls for this run.")
      break

    # Check dedup before Explore call (saves an API call if already processed)
    if title in recently_processed:
      print(f"Dedup skip (Explore): '{title}' processed in last 7 days")
      continue

    try:
      print(f"Explore: fetching related queries for '{title}'...")
      explore_data = download_google_trends_explore(title, geo="US")

      rising = explore_data.get("related_queries", {}).get("rising", [])
      rising_queries = [r["query"] for r in rising]

      print(f"  Explore: {len(rising_queries)} rising queries")

      all_enriched.append(
        {
          "trend_title": title,
          "traffic": trend.get("volume_text", ""),
          "rising_queries": rising_queries,
        }
      )

      consecutive_failures = 0

      sleep_time = random.uniform(12, 20)
      print(f"  Sleeping {sleep_time:.1f}s before next Explore call...")
      await asyncio.sleep(sleep_time)

    except Exception as e:
      consecutive_failures += 1
      err_str = str(e)
      if "429" in err_str or "rate" in err_str.lower():
        backoff = random.uniform(60, 120)
        print(
          f"429 on Explore for '{title}' "
          f"(failure {consecutive_failures}/3) - backing off {backoff:.0f}s"
        )
        await asyncio.sleep(backoff)
      else:
        print(f"Explore failed for '{title}': {e}")
        await asyncio.sleep(15)

  print(f"Total for SBERT: {len(all_enriched)} terms")

  # 4. SBERT on rising queries
  passed_count = 0
  dispatched_count = 0

  for item in all_enriched:
    trend_title = item["trend_title"]
    rising_queries = item["rising_queries"]

    if not rising_queries:
      print(f"No rising queries for '{trend_title}' - skip SBERT")
      continue

    # Batch encode all rising queries at once
    print(f"SBERT scoring {len(rising_queries)} queries for '{trend_title}'...")
    scores = sbert.score_texts(rising_queries)

    passed_queries = []
    for query, score in zip(rising_queries, scores):
      print(f"  {score:.3f} | '{query}'")
      if score >= SBERT_GT_THRESHOLD:
        passed_queries.append({"query": query, "score": score})

    if not passed_queries:
      print(f"'{trend_title}' - no queries passed SBERT threshold")
      continue

    # Sort: highest score first
    passed_queries.sort(key=lambda x: -x["score"])
    passed_count += 1
    print(
      f"✓ PASSED: '{trend_title}' | "
      f"top query: '{passed_queries[0]['query']}' "
      f"(score: {passed_queries[0]['score']:.3f})"
    )

    trend_id = make_trend_id("gt", trend_title)

    # 5. Dispatch
    try:
      with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
          """
            INSERT INTO trend_signals (
              signal_type, signal_data,
              search_query, search_platforms, search_status, linked_trend_id
            ) VALUES (
              'gt_spike', %s,
              %s, '["tiktok","instagram"]'::jsonb, 'pending', %s
            )
          """,
          (
            Json({
              "gt_term": trend_title,
              "gt_traffic": item.get("traffic"),
              "gt_rising_queries": passed_queries,
            }),
            trend_title,
            trend_id,
          ),
        )
        conn.commit()
      print(f"DB written for '{trend_title}'")
      dispatched_count += 1
    except Exception as e:
      print(f"DB insert failed for '{trend_title}': {e}")
      continue

    # 6. Social: Inline Apify fetch
    if client:
      print(f"Fetching social posts for '{trend_title}'...")
      try:
        results = await asyncio.gather(
          scrape_tiktok_search(client, [trend_title], limit_posts=5, source="gtrends_search"),
          scrape_instagram_search(client, [trend_title], limit_posts=5, source="gtrends_search"),
          return_exceptions=True,
        )
        all_posts = []
        for r in results:
          if isinstance(r, list):
            all_posts.extend(r)
          else:
            print(f"Scrape task failed: {r}")

        print(f"Fetched {len(all_posts)} posts for '{trend_title}'")

        if all_posts:
          posts_dicts = [p.to_dict() for p in all_posts]
          # Batch score posts too
          post_texts = [
            (p.get("caption_text") or "") + " " + (p.get("transcript_text") or "")
            for p in posts_dicts
          ]
          post_scores = sbert.score_texts(post_texts)

          inserted_count = 0
          for post, score in zip(posts_dicts, post_scores):
            post["source"] = "gtrends_search"
            if insert_post(post, float(score)):
              inserted_count += 1
          print(f"  -> Saved {inserted_count} new posts into DB for '{trend_title}'")
      except Exception as e: 
        print(f"Inline Apify fetch failed for '{trend_title}': {e}")
    else:
      print("No APIFY_TOKEN - skipping inline social fetch")

  print(
    f"DONE | {len(top_20_trends)} top trends fetched and checked | "
    f"{passed_count} passed SBERT | "
    f"{dispatched_count} dispatched"
  )


if __name__ == "__main__":
  asyncio.run(run_google_trends_worker())
