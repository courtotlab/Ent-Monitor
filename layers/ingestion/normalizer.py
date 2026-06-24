import datetime
import re
from layers.ingestion.models import NormalizedPost

def extract_id(url: str) -> str:
    url = url.rstrip("/")
    return url.split("@")[-1] if "@" in url else url.split("/")[-1]


def norm_instagram(item: dict, method: str, creator_id: str) -> NormalizedPost:
    caption = item.get("caption") or ""
    tags = item.get("hashtags") or []
    if isinstance(tags, str):
        tags = [tags]
    if not tags:
        tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

    return NormalizedPost(
        post_id=str(item.get("id") or item.get("shortCode") or item.get("url") or f"{item.get('timestamp', '')}_{creator_id}"),
        platform="instagram",
        source_method=method,
        source_method_conf="high" if method == "creator_monitor" else "medium",
        creator_id=str(item.get("ownerUsername") or item.get("username") or creator_id),
        caption_text=caption,
        hashtags=tags or None,
        posted_at=item.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engagement={
            "likes": item.get("likesCount") or item.get("likes") or 0,
            "comments": item.get("commentsCount") or item.get("comments") or 0,
            "shares": item.get("sharesCount") or 0,
            "views": item.get("videoViewCount") or item.get("views") or 0,
        },
        metadata={"video_url": item.get("videoUrl") or item.get("url") or ""}
    )

def norm_reddit(submission, subreddit: str) -> NormalizedPost:
    return NormalizedPost(
        post_id=str(submission.id),
        platform="reddit",
        source_method="reddit_stream",
        source_method_conf="high",
        creator_id=str(submission.author.name if submission.author else "deleted"),
        caption_text=f"{submission.title}\n\n{submission.selftext}".strip(),
        posted_at=datetime.datetime.fromtimestamp(submission.created_utc, datetime.timezone.utc).isoformat(),
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engagement={
            "likes": getattr(submission, "score", 0),
            "comments": getattr(submission, "num_comments", 0),
            "shares": 0, "views": 0,
            "score": getattr(submission, "score", 0)
        },
        metadata={"subreddit": subreddit, "url": submission.url}
    )

def norm_tiktok(item: dict, method: str, creator_id: str) -> NormalizedPost:
    caption = item.get("desc") or item.get("text") or ""
    tags = list({x["hashtagName"] for x in item.get("textExtra") or [] if x.get("hashtagName")})
    if not tags:
        tags = list(dict.fromkeys(re.findall(r"#(\w+)", caption)))

    stats = item.get("stats") or {}
    posted = item.get("createTime") or item.get("createTimeISO")
    if isinstance(posted, (int, float)):
        posted = datetime.datetime.fromtimestamp(posted, datetime.timezone.utc).isoformat()
    elif not posted:
        posted = datetime.datetime.now(datetime.timezone.utc).isoformat()

    author = item.get("author") or {}
    return NormalizedPost(
        post_id=str(item.get("id") or item.get("webVideoUrl") or f"{posted}_{creator_id}"),
        platform="tiktok",
        source_method=method,
        source_method_conf="high" if method == "creator_monitor" else "medium",
        creator_id=str(author.get("uniqueId") or item.get("authorMeta", {}).get("name") or creator_id),
        caption_text=caption,
        hashtags=tags or None,
        posted_at=posted,
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engagement={
            "likes": item.get("diggCount") or stats.get("diggCount") or stats.get("likeCount") or item.get("likeCount") or 0,
            "comments": item.get("commentCount") or stats.get("commentCount") or 0,
            "shares": item.get("shareCount") or stats.get("shareCount") or 0,
            "views": item.get("playCount") or stats.get("playCount") or stats.get("viewCount") or item.get("viewCount") or 0,
        },
        metadata={"video_url": item.get("webVideoUrl") or item.get("videoUrl") or ""}
    )

def norm_youtube(item: dict, creator_handle: str) -> NormalizedPost:
    return NormalizedPost(
        post_id=str(item.get("id") or item.get("videoUrl") or f"{item.get('date', '')}_{creator_handle}"),
        platform="youtube",
        source_method="creator_monitor",
        source_method_conf="high",
        creator_id=str(creator_handle),
        caption_text=f"{item.get('title', '')}\n\n{item.get('description', '')}".strip(),
        transcript_text=item.get("subtitlesText") or item.get("subtitles") or None,
        posted_at=item.get("date") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engagement={
            "likes": item.get("likes") or item.get("likeCount") or 0,
            "comments": item.get("comments") or item.get("commentCount") or 0,
            "shares": 0,
            "views": item.get("viewCount") or item.get("views") or 0,
        },
        metadata={"video_url": item.get("videoUrl") or f"https://www.youtube.com/watch?v={item.get('id', '')}"}
    )
