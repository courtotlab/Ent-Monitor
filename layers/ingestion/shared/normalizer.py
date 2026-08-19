import datetime
import re

from layers.ingestion.shared.models import NormalizedPost


def now_iso() -> str:
  return datetime.datetime.now(datetime.UTC).isoformat()


def extract_id(url: str) -> str:
  url = url.rstrip("/")
  return url.split("@")[-1] if "@" in url else url.split("/")[-1]


def norm_instagram(post_data: dict, source: str, creator_id: str) -> NormalizedPost:
  caption = post_data.get("caption", "")
  tags = [h for h in post_data.get("hashtags", []) if isinstance(h, str)]
  if not tags:
    tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

  return NormalizedPost(
    post_id=str(post_data.get("id", "")),
    platform="instagram",
    source=source,
    creator_id=str(
      post_data.get("ownerUsername") or post_data.get("username", creator_id)
    ),
    caption_text=caption,
    hashtags=tags or None,
    posted_at=post_data.get("timestamp") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(post_data.get("likesCount") or 0),
      "comments": int(post_data.get("commentsCount") or 0),
      "shares": int(post_data.get("sharesCount") or 0),
      "views": int(post_data.get("videoViewCount") or 0),
    },
    metadata={"video_url": post_data.get("url", "")},
  )


def norm_reddit(post_data, subreddit: str, is_praw: bool, source_override: str = None) -> NormalizedPost:
  # Collapse PRAW object vs dict access into shared variables
  post_id = str(post_data.id) if is_praw else str(post_data.get("id", ""))
  source = source_override or "reddit"
  
  if is_praw:
    creator = str(post_data.author.name if post_data.author else "deleted")
  else:
    creator = str(post_data.get("author") or "deleted")
      
  title = post_data.title if is_praw else post_data.get("title", "")
  selftext = post_data.selftext if is_praw else post_data.get("selftext", "")
  created_utc = post_data.created_utc if is_praw else post_data.get("created_utc", 0)
  score = getattr(post_data, "score", 0) if is_praw else post_data.get("score", 0)
  num_comments = getattr(post_data, "num_comments", 0) if is_praw else post_data.get("num_comments", 0)
  url = post_data.url if is_praw else post_data.get("url", "")

  return NormalizedPost(
    post_id=post_id,
    platform="reddit",
    source=source,
    creator_id=creator,
    caption_text=f"{title}\n\n{selftext}".strip(),
    posted_at=datetime.datetime.fromtimestamp(created_utc, datetime.UTC).isoformat(),
    collected_at=now_iso(),
    engagement={
      "likes": score,
      "comments": num_comments,
      "shares": 0,
      "views": 0,
      "score": score,
    },
    metadata={"subreddit": subreddit, "url": url},
  )


def norm_tiktok(post_data: dict, source: str, creator_id: str) -> NormalizedPost:
  caption = post_data.get("text", "")
  tags = [
    h.get("name")
    for h in post_data.get("hashtags", [])
    if isinstance(h, dict) and h.get("name")
  ]
  if not tags:
    tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

  return NormalizedPost(
    post_id=str(post_data.get("id", "")),
    platform="tiktok",
    source=source,
    creator_id=str(post_data.get("authorMeta", {}).get("name", creator_id)),
    caption_text=caption,
    hashtags=tags or None,
    posted_at=post_data.get("createTimeISO") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(post_data.get("diggCount") or 0),
      "comments": int(post_data.get("commentCount") or 0),
      "shares": int(post_data.get("shareCount") or 0),
      "views": int(post_data.get("playCount") or 0),
    },
    metadata={"video_url": post_data.get("webVideoUrl", "")},
  )


def norm_youtube(video_data: dict, creator_handle: str, source_override: str = None) -> NormalizedPost:
  caption = f"{video_data.get('title', '')}\n\n{video_data.get('text', '')}".strip()
  tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

  return NormalizedPost(
    post_id=str(video_data.get("id", "")),
    platform="youtube",
    source=source_override or "creator_monitor",
    creator_id=str(video_data.get("channelName", creator_handle)),
    caption_text=caption,
    hashtags=tags or None,
    transcript_text=video_data.get("subtitles") or "",
    posted_at=video_data.get("date") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(video_data.get("likes") or 0),
      "comments": int(video_data.get("commentsCount") or 0),
      "shares": 0,
      "views": int(video_data.get("viewCount") or 0),
    },
    metadata={"video_url": video_data.get("url", "")},
  )
