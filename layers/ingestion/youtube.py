from layers.ingestion.models import NormalizedPost
from layers.ingestion.normalizer import norm_youtube
async def scrape_youtube(client, creators: list[str], limit_posts: int) -> list[NormalizedPost]:
    if not creators: return []

    start_urls = [{"url": c} for c in creators if c]
        
    posts = []
    try:
        run = await client.actor("streamers/youtube-scraper").call(run_input={
            "startUrls": start_urls, "maxResults": limit_posts * len(creators), "maxResultsShorts": limit_posts * len(creators),
            "subtitlesLanguage": "en", "downloadSubtitles": True
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if item.get("id") or item.get("videoUrl"):
                posts.append(norm_youtube(item, item.get("channelName", "")))
    except Exception as e:
        print(f"[YT] Scrape error: {e}")
        
    return posts
