import argparse
import asyncio
import json
import os
# from datetime import datetime
# from layers.shared.paths import get_results_dir

from dotenv import load_dotenv

load_dotenv()

from apify import Actor

from layers.ingestion.instagram import scrape_instagram, scrape_instagram_explore
from layers.ingestion.reddit import scrape_reddit
from layers.ingestion.tiktok import scrape_tiktok, scrape_tiktok_explore
from layers.ingestion.youtube import scrape_youtube
from layers.preprocess.queries import insert_post


def parse_creators_json(path: str):
  if not os.path.exists(path): return [], []
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


async def run_ingestion():
  parser = argparse.ArgumentParser()
  parser.add_argument("--platform", choices=["tiktok", "instagram", "youtube", "reddit", "all"], default="all")  # Platforms to scrape
  parser.add_argument("--limit-creators", type=int, default=0)  # Limit creator list count (0 = all)
  parser.add_argument("--limit-posts", type=int, default=2)  # Posts to scrape per creator/explore
  parser.add_argument("--limit-engagers", type=int, default=1)  # Commenters to sample per post
  parser.add_argument("--posts-per-engager", type=int, default=2)  # Posts to scrape per commenter
  parser.add_argument("--reddit-limit", type=int, default=5)  # Hot submissions per subreddit
  parser.add_argument("--explore-count", type=int, default=1)  # Explore feed scrape runs
  args = parser.parse_args()

  creators, subreddits = parse_creators_json("config/creators.json")
  client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None

  # Run batch scrapers
  tasks, posts = [], []

  def get_c(plat):
    lst = [c["url"] for c in creators if c["platform"] == plat]
    return lst[: args.limit_creators] if args.limit_creators else lst

  if (args.platform in ["tiktok", "all"]) and client:
    if tt := get_c("tiktok"):
      tasks.append(scrape_tiktok(client, tt, args.limit_posts, args.limit_engagers, args.posts_per_engager))
    for _ in range(args.explore_count):
      tasks.append(scrape_tiktok_explore(client, args.limit_posts))

  if (args.platform in ["instagram", "all"]) and client:
    if ig := get_c("instagram"):
      tasks.append(scrape_instagram(client, ig, args.limit_posts, args.limit_engagers, args.posts_per_engager))
    for _ in range(args.explore_count):
      tasks.append(scrape_instagram_explore(client, args.limit_posts))

  if (args.platform in ["youtube", "all"]) and client and (yt := get_c("youtube")):
    tasks.append(scrape_youtube(client, yt, args.limit_posts))
  if (args.platform in ["reddit", "all"]) and subreddits:
    tasks.append(scrape_reddit(subreddits, args.reddit_limit))

  if tasks:
    for res in await asyncio.gather(*tasks):
      posts.extend([post.to_dict() for post in res])

    if posts:
      # out = get_results_dir() / f"collection_{datetime.now():%Y%m%d_%H%M%S}.json"
      # out.parent.mkdir(parents=True, exist_ok=True)
      # with open(out, "w", encoding="utf-8") as f:
      #   json.dump(posts, f, indent=4, ensure_ascii=False)
      # print(f"Saved {len(posts)} batch posts to {out.name}")
      inserted_count = 0
      for post in posts:
        if insert_post(post):
          inserted_count += 1


if __name__ == "__main__":
  asyncio.run(run_ingestion())
