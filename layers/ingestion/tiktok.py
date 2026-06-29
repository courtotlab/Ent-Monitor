from .models import NormalizedPost
from .normalizer import norm_tiktok, extract_id

async def scrape_tiktok(client, usernames: list[str], limit_posts: int, limit_engagers: int, posts_per_engager: int) -> list[NormalizedPost]:
    posts = []
    if not usernames: return posts

    post_urls = []
    try:
        run = await client.actor("clockworks/tiktok-scraper").call(run_input={
            "profiles": [u for u in usernames if u], "resultsPerPage": limit_posts, "sortBy": "createTime",
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            url = item.get("webVideoUrl") or item.get("videoUrl")
            if url and len(post_urls) < 5 * len(usernames):
                post_urls.append(url)
            if item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
                posts.append(norm_tiktok(item, "creator_monitor", item.get("author", {}).get("uniqueId", "")))
    except Exception as e:
        print(f"[TT] Creator scrape error: {e}")

    if limit_engagers <= 0 or not post_urls: return posts

    engagers = set()
    handles = {extract_id(u).lower() for u in usernames if u}
    
    try:
        run = await client.actor("clockworks/tiktok-scraper").call(run_input={
            "postUrls": post_urls, "resultsType": "comments", "resultsPerPage": limit_engagers
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            author_id = (item.get("author") or {}).get("uniqueId", "")
            if author_id and author_id.lower() not in handles:
                engagers.add(f"@{author_id}")
            if len(engagers) >= limit_engagers: break
    except Exception as e:
        print(f"[TT] Engager scrape error: {e}")

    engagers = list(engagers)[:limit_engagers]
    if engagers:
        try:
            run = await client.actor("clockworks/tiktok-scraper").call(run_input={
                "profiles": engagers, "resultsPerPage": posts_per_engager, "sortBy": "createTime"
            })
            async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                if item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
                    posts.append(norm_tiktok(item, "engager_sample", item.get("author", {}).get("uniqueId", "")))
        except Exception as e:
            print(f"[TT] Engager scrape error: {e}")
            
    return posts

async def scrape_tiktok_explore(client, limit_posts: int) -> list[NormalizedPost]:
    posts = []
    
    try:
        run = await client.actor("clockworks/tiktok-scraper").call(run_input={
            "hashtags": ["fyp"],
            "resultsPerPage": limit_posts,
        })
        async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if item.get("id") or item.get("webVideoUrl") or item.get("videoUrl"):
                posts.append(norm_tiktok(item, "explore_feed", "explore"))
    except Exception as e:
        print(f"[TT] Explore scrape error: {e}")
        
    return posts

