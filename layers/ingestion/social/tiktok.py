import random
import logging

from layers.ingestion.shared.models import NormalizedPost
from layers.ingestion.shared.normalizer import extract_id, norm_tiktok

logger = logging.getLogger(__name__)


async def scrape_tiktok(client, handles: list[str], limit_posts: int, limit_engagers: int, posts_per_engager: int) -> list[NormalizedPost]:
  posts = []
  valid_handles = [u for u in handles if u]
  if not valid_handles:
    return posts

  post_urls = []
  try:
    run = await client.actor("clockworks/tiktok-scraper").call(
      run_input={
        "profiles": valid_handles,
        "resultsPerPage": limit_posts,
        "sortBy": "createTime",
      },
      logger=None,
    )
    async for item in client.dataset(run.default_dataset_id).iterate_items():
      url = item.get("webVideoUrl") or item.get("videoUrl")
      if url and len(post_urls) < 5 * len(valid_handles):
        post_urls.append(url)
      
      if "error" in item:
        target = item.get("url") or (item.get("input") or {}).get("profile", "")
        msg = f" for '{target}'" if target else ""
        logger.warning(f"[TT] Creator fetch failed{msg}: {item['error']}")
      elif item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
        posts.append(
          norm_tiktok(
            item, "creator_monitor", item.get("author", {}).get("uniqueId", "")
          )
        )
  except Exception as e:
    logger.error(f"[TT] Creator scrape failed: {e}")

  if limit_engagers <= 0 or not post_urls:
    return posts

  engagers = set()
  handle_set = {extract_id(u).lower() for u in valid_handles}

  try:
    run = await client.actor("clockworks/tiktok-scraper").call(
      run_input={
        "postURLs": post_urls,
        "resultsType": "comments",
        "resultsPerPage": limit_engagers,
      },
      logger=None,
    )
    async for item in client.dataset(run.default_dataset_id).iterate_items():
      if "error" in item:
        logger.warning(f"[TT] Engager comments fetch failed: {item['error']}")
      else:
        author_id = (item.get("author") or {}).get("uniqueId", "")
        if author_id and author_id.lower() not in handle_set:
          engagers.add(author_id)
        if len(engagers) >= limit_engagers:
          break
  except Exception as e:
    logger.error(f"[TT] Engager comments fetch failed: {e}")

  engagers = list(engagers)[:limit_engagers]
  if engagers:
    try:
      run = await client.actor("clockworks/tiktok-scraper").call(
        run_input={
          "profiles": engagers,
          "resultsPerPage": posts_per_engager,
          "sortBy": "createTime",
        },
        logger=None,
      )
      async for item in client.dataset(run.default_dataset_id).iterate_items():
        if "error" in item:
          target = item.get("url") or (item.get("input") or {}).get("profile", "")
          msg = f" for '{target}'" if target else ""
          logger.warning(f"[TT] Engager post fetch failed{msg}: {item['error']}")
        elif item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
          posts.append(
            norm_tiktok(item, "engager", item.get("author", {}).get("uniqueId", ""))
          )
    except Exception as e:
      logger.error(f"[TT] Engager posts fetch failed: {e}")

  return posts


async def scrape_tiktok_explore(client, limit_posts: int) -> list[NormalizedPost]:
  posts = []

  try:
    explore_tags = ["fyp", "foryou", "foryoupage", "trending", "viral", "explore"]
    random_tag = random.choice(explore_tags)
    run = await client.actor("clockworks/tiktok-scraper").call(
      run_input={
        "hashtags": [random_tag],
        "resultsPerPage": limit_posts,
      },
      logger=None,
    )
    async for item in client.dataset(run.default_dataset_id).iterate_items():
      if "error" in item:
        logger.warning(f"[TT] Explore hashtag '#{random_tag}' failed: {item['error']}")
      elif item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
        posts.append(norm_tiktok(item, "explore_feed", "explore"))
  except Exception as e:
    logger.error(f"[TT] Explore scrape failed: {e}")

  return posts


async def scrape_tiktok_search(
  client, keywords: list[str], limit_posts: int, source: str
) -> list[NormalizedPost]:
  posts = []
  if not keywords:
    return posts

  try:
    run = await client.actor("clockworks/tiktok-scraper").call(
      run_input={
        "searchQueries": keywords,
        "resultsPerPage": limit_posts,
        "sortBy": "createTime",
      },
      logger=None,
    )
    async for item in client.dataset(run.default_dataset_id).iterate_items():
      if "error" in item:
        logger.warning(f"[TT] Search query '{keywords}' failed: {item['error']}")
      elif item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
        posts.append(norm_tiktok(item, source, "search"))
  except Exception as e:
    logger.error(f"[TT] Search scrape failed: {e}")

  return posts
