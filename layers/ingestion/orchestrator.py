import argparse
import asyncio
import json
import os
from datetime import datetime
from layers.shared.paths import get_results_dir

from dotenv import load_dotenv

load_dotenv()

from apify import Actor

from layers.ingestion.social.instagram import scrape_instagram, scrape_instagram_explore
from layers.ingestion.social.reddit import scrape_reddit, scrape_reddit_explore
from layers.ingestion.social.tiktok import scrape_tiktok, scrape_tiktok_explore
from layers.ingestion.social.youtube import scrape_youtube, scrape_youtube_explore
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


def get_c(creators, plat, limit=0):
    lst = [c["url"] for c in creators if c["platform"] == plat]
    return lst[:limit] if limit else lst


def save_and_insert(posts, platform_name):
    if not posts:
        print(f"No posts scraped for {platform_name}.")
        return
    
    out = get_results_dir() / f"collection_{platform_name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=4, ensure_ascii=False)
    
    print(f"Saved {len(posts)} batch posts to {out.name}")
    
    inserted_count = 0
    for post in posts:
        if insert_post(post):
            inserted_count += 1
    print(f"Inserted {inserted_count} new posts into DB for {platform_name}.")


async def run_tiktok(limit_creators=0, limit_posts=2, limit_engagers=1, posts_per_engager=2, explore_count=3):
    print("--- Starting TikTok Ingestion ---")
    creators, _ = parse_creators_json("config/creators.json")
    client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None
    if not client:
        print("Missing APIFY_TOKEN")
        return

    tasks = []
    if tt := get_c(creators, "tiktok", limit_creators):
        tasks.append(scrape_tiktok(client, tt, limit_posts, limit_engagers, posts_per_engager))
    for _ in range(explore_count):
        tasks.append(scrape_tiktok_explore(client, limit_posts))

    posts = []
    if tasks:
        for res in await asyncio.gather(*tasks):
            posts.extend([post.to_dict() for post in res])
    save_and_insert(posts, "tiktok")


async def run_instagram(limit_creators=0, limit_posts=2, limit_engagers=1, posts_per_engager=2, explore_count=3):
    print("--- Starting Instagram Ingestion ---")
    creators, _ = parse_creators_json("config/creators.json")
    client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None
    if not client:
        print("Missing APIFY_TOKEN")
        return

    tasks = []
    if ig := get_c(creators, "instagram", limit_creators):
        tasks.append(scrape_instagram(client, ig, limit_posts, limit_engagers, posts_per_engager))
    for _ in range(explore_count):
        tasks.append(scrape_instagram_explore(client, limit_posts))

    posts = []
    if tasks:
        for res in await asyncio.gather(*tasks):
            posts.extend([post.to_dict() for post in res])
    save_and_insert(posts, "instagram")


async def run_youtube(limit_creators=0, limit_posts=2, explore_count=3):
    print("--- Starting YouTube Ingestion ---")
    creators, _ = parse_creators_json("config/creators.json")
    client = Actor.new_client() if os.getenv("APIFY_TOKEN") else None
    if not client:
        print("Missing APIFY_TOKEN")
        return

    tasks = []
    if yt := get_c(creators, "youtube", limit_creators):
        tasks.append(scrape_youtube(client, yt, limit_posts))
    for _ in range(explore_count):
        tasks.append(scrape_youtube_explore(client, limit_posts))

    posts = []
    if tasks:
        for res in await asyncio.gather(*tasks):
            posts.extend([post.to_dict() for post in res])
    save_and_insert(posts, "youtube")


async def run_reddit(reddit_limit=5, explore_count=3):
    print("--- Starting Reddit Ingestion ---")
    _, subreddits = parse_creators_json("config/creators.json")
    
    tasks = []
    if subreddits:
        tasks.append(scrape_reddit(subreddits, reddit_limit))
    for _ in range(explore_count):
        tasks.append(scrape_reddit_explore(reddit_limit))

    posts = []
    if tasks:
        for res in await asyncio.gather(*tasks):
            posts.extend([post.to_dict() for post in res])
    save_and_insert(posts, "reddit")


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

    if args.platform == "tiktok":
        asyncio.run(run_tiktok(args.limit_creators, args.limit_posts, args.limit_engagers, args.posts_per_engager, args.explore_count))
    elif args.platform == "instagram":
        asyncio.run(run_instagram(args.limit_creators, args.limit_posts, args.limit_engagers, args.posts_per_engager, args.explore_count))
    elif args.platform == "youtube":
        asyncio.run(run_youtube(args.limit_creators, args.limit_posts, args.explore_count))
    elif args.platform == "reddit":
        asyncio.run(run_reddit(args.reddit_limit, args.explore_count))
