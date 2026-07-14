from .models import NormalizedPost
from .normalizer import norm_youtube


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
