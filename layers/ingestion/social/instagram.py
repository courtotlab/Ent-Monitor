import random

from layers.ingestion.shared.models import NormalizedPost
from layers.ingestion.shared.normalizer import extract_id, norm_instagram


async def scrape_instagram(client, profile_urls: list[str], limit_posts: int, limit_engagers: int, posts_per_engager: int) -> list[NormalizedPost]:
  if not profile_urls: return []
  posts = []

  post_urls = []
  try:
    run = await client.actor("apify/instagram-scraper").call(
      run_input={
        "directUrls": [u for u in profile_urls if u],
        "resultsType": "posts",
        "resultsLimit": limit_posts,
        "proxyConfiguration": {"useApifyProxy": True},
      }
    )
    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      shortCode = item.get("shortCode")
      if shortCode and len(post_urls) < 5 * len(profile_urls):
        post_urls.append(f"https://www.instagram.com/p/{shortCode}/")
      if "error" not in item and (item.get("id") or item.get("shortCode")):
        posts.append(
          norm_instagram(item, "creator_monitor", item.get("ownerUsername", ""))
        )
  except Exception as e:
    print(f"[IG] Creator scrape error: {e}")

  if limit_engagers <= 0 or not post_urls:
    return posts

  engagers = set()
  handle_set = {extract_id(u).lower() for u in profile_urls if u}

  try:
    run = await client.actor("apify/instagram-scraper").call(
      run_input={
        "directUrls": post_urls,
        "resultsType": "comments",
        "resultsLimit": limit_engagers,
        "proxyConfiguration": {"useApifyProxy": True},
      }
    )
    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      username = item.get("ownerUsername") or item.get("username")
      if username and username.lower() not in handle_set:
        engagers.add(username)
      if len(engagers) >= limit_engagers:
        break
  except Exception as e:
    print(f"[IG] Engager comments fetch error: {e}")

  engagers = list(engagers)[:limit_engagers]
  if engagers:
    try:
      run = await client.actor("apify/instagram-scraper").call(
        run_input={
          "directUrls": [f"https://www.instagram.com/{e}/" for e in engagers],
          "resultsType": "posts",
          "resultsLimit": posts_per_engager,
          "proxyConfiguration": {"useApifyProxy": True},
        }
      )
      async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        if "error" not in item and (item.get("id") or item.get("shortCode")):
          posts.append(norm_instagram(item, "engager", item.get("ownerUsername", "")))
    except Exception as e:
      print(f"[IG] Engager posts fetch error: {e}")

  return posts


async def scrape_instagram_explore(client, limit_posts: int) -> list[NormalizedPost]:
  posts = []

  try:
    explore_tags = ["trending", "explore", "viral", "foryou", "reels", "foryoupage"]
    random_tag = random.choice(explore_tags)
    run = await client.actor("apify/instagram-scraper").call(
      run_input={
        "directUrls": [f"https://www.instagram.com/explore/tags/{random_tag}/"],
        "resultsType": "posts",
        "resultsLimit": limit_posts,
        "proxyConfiguration": {"useApifyProxy": True},
      }
    )
    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      if "error" not in item and (item.get("id") or item.get("shortCode")):
        posts.append(norm_instagram(item, "explore_feed", "explore"))
  except Exception as e:
    print(f"[IG] Explore scrape error: {e}")

  return posts


async def scrape_instagram_search(client, keywords: list[str], limit_posts: int, source: str) -> list[NormalizedPost]:
  posts = []
  if not keywords:
    return posts
  try:
    run = await client.actor("apify/instagram-scraper").call(
      run_input={
        "search": " ".join(keywords),
        "searchType": "hashtag",
        "resultsType": "posts",
        "resultsLimit": limit_posts,
        "proxyConfiguration": {"useApifyProxy": True},
      }
    )
    async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
      if "error" not in item and (item.get("id") or item.get("shortCode")):
        posts.append(norm_instagram(item, source, "search"))
  except Exception as e:
    print(f"[IG] Search scrape error: {e}")

  return posts
