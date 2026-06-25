from layers.ingestion.models import NormalizedPost
from layers.ingestion.normalizer import norm_instagram, extract_id
async def scrape_instagram(client, creators: list[str], limit_posts: int, limit_engagers: int, posts_per_engager: int) -> list[NormalizedPost]:
    if not creators: return []
    posts = []

    creator_post_urls = []
    try:
        run = await client.actor("apify/instagram-scraper").call(run_input={
            "directUrls": [c for c in creators if c],
            "resultsType": "posts",
            "resultsLimit": limit_posts,
            "proxyConfiguration": {"useApifyProxy": True},
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            shortCode = item.get("shortCode")
            if shortCode and len(creator_post_urls) < 5 * len(creators):
                creator_post_urls.append(f"https://www.instagram.com/p/{shortCode}/")
            if "error" not in item and (item.get("id") or item.get("shortCode")):
                posts.append(norm_instagram(item, "creator_monitor", item.get("ownerUsername", "")))
    except Exception as e:
        print(f"[IG] Creator scrape error: {e}")

    if limit_engagers <= 0 or not creator_post_urls: return posts

    engagers = set()
    creator_handles = {extract_id(c).lower() for c in creators if c}
    try:
        run = await client.actor("apify/instagram-scraper").call(run_input={
            "directUrls": creator_post_urls,
            "resultsType": "comments",
            "resultsLimit": limit_engagers + 5,
            "proxyConfiguration": {"useApifyProxy": True},
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            username = item.get("ownerUsername") or item.get("username")
            if username and username.lower() not in creator_handles:
                engagers.add(username)
            if len(engagers) >= limit_engagers: break
    except Exception as e:
        print(f"[IG] Engager scrape error: {e}")

    engagers = list(engagers)[:limit_engagers]
    if engagers:
        try:
            run = await client.actor("apify/instagram-scraper").call(run_input={
                "directUrls": [f"https://www.instagram.com/{e}/" for e in engagers],
                "resultsType": "posts",
                "resultsLimit": posts_per_engager,
                "proxyConfiguration": {"useApifyProxy": True},
            })
            async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                if "error" not in item and (item.get("id") or item.get("shortCode")):
                    posts.append(norm_instagram(item, "engager_sample", item.get("ownerUsername", "")))
        except Exception as e:
            print(f"[IG] Engager scrape error: {e}")
            
    return posts

async def scrape_instagram_explore(client, limit_posts: int) -> list[NormalizedPost]:
    posts = []
    try:
        run = await client.actor("apify/instagram-scraper").call(run_input={
            "directUrls": ["https://www.instagram.com/explore/tags/trending/"],
            "resultsType": "posts",
            "resultsLimit": limit_posts,
            "proxyConfiguration": {"useApifyProxy": True},
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if "error" not in item and (item.get("id") or item.get("shortCode")):
                posts.append(norm_instagram(item, "explore_feed", "explore"))
    except Exception as e:
        print(f"[IG] Explore scrape error: {e}")
        
    return posts

