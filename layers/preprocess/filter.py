import re
from dataclasses import dataclass, field
from typing import Any

from langdetect import LangDetectException, detect

MIN_WORD_COUNT = 3


@dataclass
class QualityFilterStats:
  passed: int = 0
  non_english: int = 0
  too_short: int = 0


@dataclass
class QualityFilterResult:
  survivors: list[dict[str, Any]] = field(default_factory=list)
  stats: QualityFilterStats = field(default_factory=QualityFilterStats)


def _word_count(text: str) -> int:
  return len(re.findall(r"\b\w+\b", text or ""))


def _is_english(text: str) -> bool:
  try: return detect(sample) == "en" if (sample := (text or "").strip()) else False
  except LangDetectException: return True


def run_quality_filter(posts: list[dict[str, Any]]) -> QualityFilterResult:
  """Quality filter - language, minimum content."""
  stats = QualityFilterStats()
  survivors: list[dict[str, Any]] = []

  for post in posts:
    caption = post.get("caption_text") or ""
    if _word_count(caption) < MIN_WORD_COUNT:
      stats.too_short += 1
      continue

    if not _is_english(caption):
      stats.non_english += 1
      continue

    survivors.append(post)
    stats.passed += 1

  return QualityFilterResult(survivors=survivors, stats=stats)
