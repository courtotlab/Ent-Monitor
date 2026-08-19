import random
from layers.ingestion.shared.models import NormalizedPost
from layers.ingestion.shared.normalizer import norm_youtube


async def scrape_youtube(client, usernames: list[str], limit_posts: int) -> list[NormalizedPost]:
  if not usernames: return []

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
      if item.get("id") or item.get("videoUrl"):
        posts.append(norm_youtube(item, item.get("channelName", "")))
  except Exception as e:
    print(f"[YT] Scrape error: {e}")

  return posts

async def scrape_youtube_explore(client, limit_posts: int) -> list[NormalizedPost]:
  posts = []
  explore_queries = ["trending shorts", "viral shorts", "popular shorts", "explore", "trending"]
  random_query = random.choice(explore_queries)
  
  try:
    run = await client.actor("streamers/youtube-scraper").call(
      run_input={
        "startUrls": [{"url": f"https://www.youtube.com/results?search_query={random_query.replace(' ', '+')}"}],
        "maxResults": limit_posts,
        "maxResultsShorts": limit_posts,
        "subtitlesLanguage": "en",
        "downloadSubtitles": True,
      }
    )

    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      if item.get("id") or item.get("videoUrl"):
        posts.append(norm_youtube(item, "explore", "explore_feed"))
  except Exception as e:
    print(f"[YT] Explore scrape error: {e}")

  return posts
