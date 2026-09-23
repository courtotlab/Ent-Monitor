import argparse
import asyncio
import os
import logging

from dotenv import load_dotenv

load_dotenv()

from apify import Actor

from layers.ingestion.shared.queries import insert_post
from layers.ingestion.social.instagram import scrape_instagram, scrape_instagram_explore
from layers.ingestion.social.reddit import scrape_reddit, scrape_reddit_explore
from layers.ingestion.social.tiktok import scrape_tiktok, scrape_tiktok_explore
from layers.ingestion.social.youtube import scrape_youtube, scrape_youtube_explore
from layers.ingestion.news.gdelt import main as run_gdelt
from layers.ingestion.search.gtrends import run_google_trends_worker
from layers.ingestion.shared.queries import get_all_creators

logger = logging.getLogger("layers.ingestion.orchestrator")


def fetch_creators_db() -> dict[str, list[str]]:
  try:
    rows = get_all_creators()
  except Exception as e:
    logger.error(f"Failed to fetch creators from DB: {e}")
    return {}

  creators = {"tiktok": [], "instagram": [], "youtube": [], "reddit": []}
  for creator_id, platform in rows:
    if platform == "reddit":
      creators["reddit"].append(creator_id)
    elif platform == "tiktok":
      creators["tiktok"].append(f"https://www.tiktok.com/@{creator_id}")
    elif platform == "instagram":
      creators["instagram"].append(f"https://www.instagram.com/{creator_id}/")
    elif platform == "youtube":
      creators["youtube"].append(f"https://www.youtube.com/@{creator_id}")
  
  return creators


def save_and_insert(posts, platform_name) -> int:
  if not posts:
    logger.info(f"Inserted 0 posts into DB for {platform_name} (0 collected)")
    return 0

  inserted_count = 0
  for post in posts:
    if insert_post(post):
      inserted_count += 1
  logger.info(f"Inserted {inserted_count} posts into DB for {platform_name} ({len(posts)} collected)")
  return inserted_count


async def run_platform(platform: str):
  logger.info(f"{platform} ingestion started")

  # Default scrape configuration
  limit_creators = 0        # Number of seeded creators to fetch (0 means fetch all)
  limit_posts = 5           # Number of recent posts to scrape per creator
  limit_engagers = 5        # Number of unique commenters/engagers to find per post
  posts_per_engager = 5     # Number of recent posts to scrape from each engager's own profile
  reddit_limit = 50         # Number of posts to fetch per subreddit
  explore_count = 5         # Number of generic explore/trending posts to fetch per platform

  creators = fetch_creators_db()
  
  client = None
  if platform != "reddit":
    client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None
    if not client:
      logger.error("Missing APIFY_TOKEN in environment")
      logger.info(f"{platform} ingestion ended")
      return

  tasks = []
  try:
    if platform == "tiktok":
      tt = creators.get("tiktok", [])
      tt = tt[:limit_creators] if limit_creators else tt
      if not tt:
        logger.warning(f"No {platform} creators found in database to monitor")
      else:
        tasks.append(scrape_tiktok(client, tt, limit_posts, limit_engagers, posts_per_engager))
      for _ in range(explore_count):
        tasks.append(scrape_tiktok_explore(client, limit_posts))
        
    elif platform == "instagram":
      ig = creators.get("instagram", [])
      ig = ig[:limit_creators] if limit_creators else ig
      if not ig:
        logger.warning(f"No {platform} creators found in database to monitor")
      else:
        tasks.append(scrape_instagram(client, ig, limit_posts, limit_engagers, posts_per_engager))
      for _ in range(explore_count):
        tasks.append(scrape_instagram_explore(client, limit_posts))
        
    elif platform == "youtube":
      yt = creators.get("youtube", [])
      yt = yt[:limit_creators] if limit_creators else yt
      if not yt:
        logger.warning(f"No {platform} creators found in database to monitor")
      else:
        tasks.append(scrape_youtube(client, yt, limit_posts))
      for _ in range(explore_count):
        tasks.append(scrape_youtube_explore(client, limit_posts))
        
    elif platform == "reddit":
      subreddits = creators.get("reddit", [])
      if not subreddits:
        logger.warning("No subreddits found in database to monitor")
      else:
        tasks.append(scrape_reddit(subreddits, reddit_limit))
      for _ in range(explore_count):
        tasks.append(scrape_reddit_explore(reddit_limit))
  except Exception as e:
    logger.error(f"Failed to setup tasks for {platform}: {e}")
    logger.info(f"{platform} ingestion ended")
    return

  posts = []
  if tasks:
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
      if isinstance(res, Exception):
        logger.error(f"Fetch failed during {platform} ingestion: {res}")
      elif res:
        posts.extend([post.to_dict() for post in res])

  save_and_insert(posts, platform)
  logger.info(f"{platform} ingestion ended")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Run specific ingestion platform.")
  parser.add_argument("platform", choices=["tiktok", "instagram", "youtube", "reddit", "gdelt", "gtrends"], help="Platform to scrape")
    
  args = parser.parse_args()

  if args.platform == "gdelt":
    logger.info("gdelt ingestion started")
    asyncio.run(run_gdelt())
    logger.info("gdelt ingestion ended")
  elif args.platform == "gtrends":
    logger.info("gtrends ingestion started")
    asyncio.run(run_google_trends_worker())
    logger.info("gtrends ingestion ended")
  else:
    asyncio.run(run_platform(args.platform))

