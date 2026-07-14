import datetime
import re

from layers.ingestion.models import NormalizedPost


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


def norm_reddit(post_data, subreddit: str, is_praw: bool) -> NormalizedPost:
  if is_praw:
    return NormalizedPost(
      post_id=str(post_data.id),
      platform="reddit",
      source="reddit_stream",
      creator_id=str(post_data.author.name if post_data.author else "deleted"),
      caption_text=f"{post_data.title}\n\n{post_data.selftext}".strip(),
      posted_at=datetime.datetime.fromtimestamp(
        post_data.created_utc, datetime.UTC
      ).isoformat(),
      collected_at=now_iso(),
      engagement={
        "likes": getattr(post_data, "score", 0),
        "comments": getattr(post_data, "num_comments", 0),
        "shares": 0,
        "views": 0,
        "score": getattr(post_data, "score", 0),
      },
      metadata={"subreddit": subreddit, "url": post_data.url},
    )
  else:
    return NormalizedPost(
      post_id=str(post_data.get("id", "")),
      platform="reddit",
      source="reddit_json",
      creator_id=str(post_data.get("author") or "deleted"),
      caption_text=f"{post_data.get('title', '')}\n\n{post_data.get('selftext', '')}".strip(),
      posted_at=datetime.datetime.fromtimestamp(
        post_data.get("created_utc", 0), datetime.UTC
      ).isoformat(),
      collected_at=now_iso(),
      engagement={
        "likes": post_data.get("score", 0),
        "comments": post_data.get("num_comments", 0),
        "shares": 0,
        "views": 0,
        "score": post_data.get("score", 0),
      },
      metadata={"subreddit": subreddit, "url": post_data.get("url", "")},
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


def norm_youtube(video_data: dict, creator_handle: str) -> NormalizedPost:
  caption = f"{video_data.get('title', '')}\n\n{video_data.get('text', '')}".strip()
  tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

  return NormalizedPost(
    post_id=str(video_data.get("id", "")),
    platform="youtube",
    source="creator_monitor",
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
