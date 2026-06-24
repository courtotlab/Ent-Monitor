import os, asyncio
import praw
from layers.ingestion.models import NormalizedPost
from layers.ingestion.normalizer import norm_reddit
def _scrape_reddit_sync(subreddits: list[str], limit_posts: int) -> list[NormalizedPost]:
    if not os.getenv("REDDIT_CLIENT_ID") or not os.getenv("REDDIT_CLIENT_SECRET"): return []

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "ENT-surveillance/1.0")
    )
    
    posts, seen = [], set()
    for sub in subreddits:
        try:
            for submission in reddit.subreddit(sub).hot(limit=limit_posts):
                if submission.id not in seen:
                    seen.add(submission.id)
                    posts.append(norm_reddit(submission, sub))
        except Exception as e:
            print(f"[Reddit] Error /r/{sub}: {e}")
            
    return posts

async def scrape_reddit(subreddits: list[str], limit_posts: int) -> list[NormalizedPost]:
    return await asyncio.to_thread(_scrape_reddit_sync, subreddits, limit_posts)
