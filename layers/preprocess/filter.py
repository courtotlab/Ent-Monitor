import re
from dataclasses import dataclass, field
from typing import Any

from langdetect import LangDetectException, detect

MIN_WORD_COUNT = 3
BOT_LIKE_RATIO = 1000


@dataclass
class QualityFilterStats:
  passed: int = 0
  duplicate_in_batch: int = 0
  non_english: int = 0
  too_short: int = 0
  bot_flagged: int = 0


@dataclass
class QualityFilterResult:
  survivors: list[dict[str, Any]] = field(default_factory=list)
  stats: QualityFilterStats = field(default_factory=QualityFilterStats)


def _word_count(text: str) -> int:
  return len(re.findall(r"\b\w+\b", text or ""))


def _is_bot_pattern(post: dict[str, Any]) -> bool:
  engagement = post.get("engagement") or {}
  likes = int(engagement.get("likes") or 0)
  comments = int(engagement.get("comments") or 0)
  if comments == 0 and likes > 0:
    return likes / max(comments, 1) > BOT_LIKE_RATIO
  if comments > 0 and likes / comments > BOT_LIKE_RATIO:
    return True
  return False


def _is_english(text: str) -> bool:
  sample = (text or "").strip()
  if not sample:
    return False
  try:
    return detect(sample) == "en"
  except LangDetectException:
    return True


def run_quality_filter(posts: list[dict[str, Any]]) -> QualityFilterResult:
  """Quality filter - dedup (in-batch), spam/bot flag, language, minimum content."""
  stats = QualityFilterStats()
  seen: set[tuple[str, str]] = set()
  survivors: list[dict[str, Any]] = []

  for post in posts:
    key = (str(post["post_id"]), str(post["platform"]))
    if key in seen:
      stats.duplicate_in_batch += 1
      continue
    seen.add(key)

    caption = post.get("caption_text") or ""
    if _word_count(caption) < MIN_WORD_COUNT:
      stats.too_short += 1
      continue

    if not _is_english(caption):
      stats.non_english += 1
      continue

    if _is_bot_pattern(post):
      stats.bot_flagged += 1

    survivors.append(post)
    stats.passed += 1

  return QualityFilterResult(survivors=survivors, stats=stats)
