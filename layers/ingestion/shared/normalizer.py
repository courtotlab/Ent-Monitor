import datetime

from layers.ingestion.shared.models import NormalizedPost


def now_iso() -> str:
  return datetime.datetime.now(datetime.UTC).isoformat()


def extract_id(url: str) -> str:
  url = url.rstrip("/")
  return url.split("@")[-1] if "@" in url else url.split("/")[-1]


def norm_instagram(post_data: dict, source: str, creator_id: str) -> NormalizedPost:
  caption = post_data.get("caption", "")

  return NormalizedPost(
    post_id=str(post_data.get("id", "")),
    platform="instagram",
    source=source,
    creator_id=str(
      post_data.get("ownerUsername") or post_data.get("username", creator_id)
    ),
    caption_text=caption,
    url=post_data.get("url", "") or None,
    posted_at=post_data.get("timestamp") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(post_data.get("likesCount") or 0),
      "comments": int(post_data.get("commentsCount") or 0),
      "shares": int(post_data.get("sharesCount") or 0),
      "views": int(post_data.get("videoViewCount") or 0),
    },
  )


def norm_reddit(post_data, subreddit: str, is_praw: bool, source_override: str = None) -> NormalizedPost:
  get_val = lambda k, d="": getattr(post_data, k, d) if is_praw else post_data.get(k, d)

  if is_praw:
    creator = str(post_data.author.name if getattr(post_data, "author", None) else "deleted")
  else:
    creator = str(post_data.get("author", "deleted"))

  title = get_val("title")
  selftext = get_val("selftext")
  created_utc = get_val("created_utc", 0)
  score = get_val("score", 0)
  num_comments = get_val("num_comments", 0)
  post_url = get_val("url")

  return NormalizedPost(
    post_id=str(get_val("id")),
    platform="reddit",
    source=source_override or "reddit",
    creator_id=creator,
    caption_text=f"{title}\n\n{selftext}".strip(),
    url=post_url or None,
    posted_at=datetime.datetime.fromtimestamp(created_utc, datetime.UTC).isoformat(),
    collected_at=now_iso(),
    engagement={
      "likes": score,
      "comments": num_comments,
      "shares": 0,
      "views": 0,
      "score": score,
    },
  )


def norm_tiktok(post_data: dict, source: str, creator_id: str) -> NormalizedPost:
  caption = post_data.get("text", "")

  return NormalizedPost(
    post_id=str(post_data.get("id", "")),
    platform="tiktok",
    source=source,
    creator_id=str(post_data.get("authorMeta", {}).get("name", creator_id)),
    caption_text=caption,
    url=post_data.get("webVideoUrl", "") or None,
    posted_at=post_data.get("createTimeISO") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(post_data.get("diggCount") or 0),
      "comments": int(post_data.get("commentCount") or 0),
      "shares": int(post_data.get("shareCount") or 0),
      "views": int(post_data.get("playCount") or 0),
    },
  )


def norm_youtube(video_data: dict, creator_handle: str, source_override: str = None) -> NormalizedPost:
  caption = f"{video_data.get('title', '')}\n\n{video_data.get('text', '')}".strip()

  return NormalizedPost(
    post_id=str(video_data.get("id", "")),
    platform="youtube",
    source=source_override or "creator_monitor",
    creator_id=str(video_data.get("channelName", creator_handle)),
    caption_text=caption,
    transcript_text=video_data.get("subtitles") or "",
    url=video_data.get("url", "") or None,
    posted_at=video_data.get("date") or now_iso(),
    collected_at=now_iso(),
    engagement={
      "likes": int(video_data.get("likes") or 0),
      "comments": int(video_data.get("commentsCount") or 0),
      "shares": 0,
      "views": int(video_data.get("viewCount") or 0),
    },
  )
