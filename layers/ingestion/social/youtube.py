import random
import logging

from layers.ingestion.shared.models import NormalizedPost
from layers.ingestion.shared.normalizer import norm_youtube

logger = logging.getLogger(__name__)


async def scrape_youtube(client, usernames: list[str], limit_posts: int) -> list[NormalizedPost]:
  if not usernames: 
    return []

  start_urls = [{"url": u} for u in usernames if u]

  posts = []
  try:
    run = await client.actor("streamers/youtube-scraper").call(
      run_input={
        "startUrls": start_urls,
        "maxResults": limit_posts,
        "maxResultsShorts": limit_posts,
        "subtitlesLanguage": "en",
        "downloadSubtitles": True,
      }
    )

    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      if "error" in item:
        logger.warning(f"[YT] Apify returned error in creator item: {item.get('error')}")
      elif item.get("id") or item.get("videoUrl"):
        posts.append(norm_youtube(item, item.get("channelName", "")))
  except Exception as e:
    logger.error(f"[YT] Scrape error: {e}")

  return posts


async def scrape_youtube_explore(client, limit_posts: int) -> list[NormalizedPost]:
  posts = []
  explore_queries = [
    "trending shorts",
    "viral shorts",
    "popular shorts",
    "explore",
    "trending",
  ]
  random_query = random.choice(explore_queries)

  try:
    run = await client.actor("streamers/youtube-scraper").call(
      run_input={
        "startUrls": [
          {
            "url": f"https://www.youtube.com/results?search_query={random_query.replace(' ', '+')}"
          }
        ],
        "maxResults": limit_posts,
        "maxResultsShorts": limit_posts,
        "subtitlesLanguage": "en",
        "downloadSubtitles": True,
      }
    )

    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      if "error" in item:
        logger.warning(f"[YT] Apify returned error in explore item: {item.get('error')}")
      elif item.get("id") or item.get("videoUrl"):
        posts.append(norm_youtube(item, "explore", "explore_feed"))
  except Exception as e:
    logger.error(f"[YT] Explore scrape error: {e}")

  return posts
