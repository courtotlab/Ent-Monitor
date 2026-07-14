import asyncio
import os

import praw
import requests

from layers.ingestion.models import NormalizedPost
from layers.ingestion.normalizer import norm_reddit


def scrape_reddit_sync(subreddits: list[str], limit_posts: int) -> list[NormalizedPost]:
  if not os.getenv("REDDIT_CLIENT_ID") or not os.getenv("REDDIT_CLIENT_SECRET"):
    return []

  reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT"),
  )

  posts, seen = [], set()
  for sub in subreddits:
    sub_count = 0
    praw_failed = False
    try:
      subreddit = reddit.subreddit(sub)
      for sort_method in ["hot", "new", "top"]:
        try:
          fetcher = getattr(subreddit, sort_method)
          for submission in fetcher(limit=limit_posts):
            if submission.id not in seen:
              seen.add(submission.id)
              posts.append(norm_reddit(submission, sub, is_praw=True))
              sub_count += 1

            if sub_count >= limit_posts:
              break
        except Exception as e:
          print(f"[Reddit] Error /r/{sub} with PRAW {sort_method}: {e}")
          praw_failed = True
          break

        if sub_count >= limit_posts:
          break
    except Exception as e:
      print(f"[Reddit] Error /r/{sub} via PRAW: {e}")
      praw_failed = True

    if praw_failed or sub_count < limit_posts:
      # Fallback to JSON endpoints
      for sort_method in ["best", "hot", "new"]:
        try:
          url = f"https://www.reddit.com/r/{sub}/{sort_method}.json?limit={limit_posts}"
          headers = {"User-Agent": os.getenv("REDDIT_USER_AGENT")}
          response = requests.get(url, headers=headers, timeout=10)
          response.raise_for_status()
          data = response.json()

          for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            post_id = post_data.get("id")
            if post_id and post_id not in seen:
              seen.add(post_id)
              posts.append(norm_reddit(post_data, sub, is_praw=False))
              sub_count += 1

            if sub_count >= limit_posts:
              break

        except Exception as e:
          print(f"[Reddit] Fallback error /r/{sub} with JSON {sort_method}: {e}")
          continue

        if sub_count >= limit_posts:
          break

  return posts

async def scrape_reddit(subreddits: list[str], limit_posts: int) -> list[NormalizedPost]:
    return await asyncio.to_thread(scrape_reddit_sync, subreddits, limit_posts)
