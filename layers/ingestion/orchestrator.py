import argparse
import asyncio
import json
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

logger = logging.getLogger(__name__)


def parse_creators_json(path: str):
  if not os.path.exists(path):
    return [], []
  with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
  return [
    {
      "name": i.get("name", ""),
      "url": i.get("social_link", ""),
      "platform": p.lower(),
    }
    for p in ["TikTok", "Instagram", "YouTube"]
    if p in data
    for i in data[p]
  ], data.get("Reddit", [])


def get_c(creators, plat, limit=0):
  lst = [c["url"] for c in creators if c["platform"] == plat]
  return lst[:limit] if limit else lst


def save_and_insert(posts, platform_name):
  if not posts:
    return

  inserted_count = 0
  for post in posts:
    if insert_post(post):
      inserted_count += 1
  logger.info(f"Inserted {inserted_count} new posts into DB for {platform_name}.")


async def run_platform(platform: str, args):
  logger.info(f"--- Starting {platform.capitalize()} Ingestion ---")
  creators, subreddits = parse_creators_json("config/creators.json")
  
  client = None
  if platform != "reddit":
    client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None
    if not client:
      logger.info("Missing APIFY_TOKEN")
      return

  tasks = []
  try:
    if platform == "tiktok":
      if tt := get_c(creators, "tiktok", args.limit_creators):
        tasks.append(scrape_tiktok(client, tt, args.limit_posts, args.limit_engagers, args.posts_per_engager))
      for _ in range(args.explore_count):
        tasks.append(scrape_tiktok_explore(client, args.limit_posts))
        
    elif platform == "instagram":
      if ig := get_c(creators, "instagram", args.limit_creators):
        tasks.append(scrape_instagram(client, ig, args.limit_posts, args.limit_engagers, args.posts_per_engager))
      for _ in range(args.explore_count):
        tasks.append(scrape_instagram_explore(client, args.limit_posts))
        
    elif platform == "youtube":
      if yt := get_c(creators, "youtube", args.limit_creators):
        tasks.append(scrape_youtube(client, yt, args.limit_posts))
      for _ in range(args.explore_count):
        tasks.append(scrape_youtube_explore(client, args.limit_posts))
        
    elif platform == "reddit":
      if subreddits:
        tasks.append(scrape_reddit(subreddits, args.reddit_limit))
      for _ in range(args.explore_count):
        tasks.append(scrape_reddit_explore(args.reddit_limit))
  except Exception as e:
    logger.error(f"Failed to setup tasks for {platform}: {e}")
    return

  posts = []
  if tasks:
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
      if isinstance(res, Exception):
        logger.error(f"Task failed during {platform} ingestion: {res}")
      else:
        posts.extend([post.to_dict() for post in res])

  save_and_insert(posts, platform)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Run specific ingestion platform.")
  parser.add_argument("platform", choices=["tiktok", "instagram", "youtube", "reddit"], help="Platform to scrape")
  parser.add_argument("--limit-creators", type=int, default=0, help="Limit creator list count (0 = all)")
  parser.add_argument("--limit-posts", type=int, default=2, help="Posts to scrape per creator/explore")
  parser.add_argument("--limit-engagers", type=int, default=1, help="Commenters to sample per post")
  parser.add_argument("--posts-per-engager", type=int, default=2, help="Posts to scrape per commenter")
  parser.add_argument("--reddit-limit", type=int, default=5, help="Hot submissions per subreddit")
  parser.add_argument("--explore-count", type=int, default=3, help="Explore feed scrape runs")
    
  args = parser.parse_args()

  asyncio.run(run_platform(args.platform, args))
