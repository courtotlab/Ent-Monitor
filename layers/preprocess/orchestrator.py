import argparse
from dataclasses import dataclass, field
from typing import Any

from .filter import run_quality_filter
from .queries import (
  fetch_active_anchors,
  increment_anchor_match_counts,
  fetch_unprocessed_posts,
  update_preprocessed_posts,
)
from .semantic_filter import SBERT_THRESHOLD, SbertFilter


@dataclass
class PreprocessStats:
  input_total: int = 0
  quality_passed: int = 0
  sbert_scored: int = 0
  sbert_passed: int = 0
  sbert_failed: int = 0
  by_source: dict[str, dict[str, int]] = field(default_factory=dict)


def run_preprocessing(limit: int = 1000) -> PreprocessStats:
  print(f"Fetching up to {limit} unprocessed posts from DB...")
  posts = fetch_unprocessed_posts(limit)
  if not posts:
    print("No unprocessed posts found.")
    return PreprocessStats()
  return process_posts(posts)


def process_posts(posts: list[dict[str, Any]]) -> PreprocessStats:
  """Apply quality and semantic gates, then update the DB."""
  stats = PreprocessStats(input_total=len(posts))

  quality = run_quality_filter(posts)
  stats.quality_passed = quality.stats.passed

  anchors = fetch_active_anchors()
  sbert = SbertFilter()
  sbert.load_anchors(anchors)

  scored = sbert.score_posts(quality.survivors)
  score_map = {
    (p["post_id"], p["platform"]): (score, anchor_id)
    for p, score, anchor_id in scored
  }
  
  survivor_keys = {(p["post_id"], p["platform"]) for p in quality.survivors}
  updates = []
  fired_anchor_ids = []

  for post in posts:
    post_id, platform = post["post_id"], post["platform"]
    source = post.get("source", "unknown")
    key = (post_id, platform)
    
    if source not in stats.by_source:
      stats.by_source[source] = {"input": 0, "quality_passed": 0, "sbert_passed": 0}
    stats.by_source[source]["input"] += 1

    if key in survivor_keys:
      stats.by_source[source]["quality_passed"] += 1
      stats.sbert_scored += 1
      
      score, matched_anchor = score_map.get(key, (0.0, None))
      
      if sbert.passes_threshold(score):
        stats.sbert_passed += 1
        stats.by_source[source]["sbert_passed"] += 1
        if matched_anchor is not None:
          fired_anchor_ids.append(matched_anchor)
      else:
        stats.sbert_failed += 1
      
      updates.append((post_id, platform, score, matched_anchor))
    else:
      # Failed quality filter -> assign -1.0 so it is marked as processed but discarded
      updates.append((post_id, platform, -1.0, None))

  print("Batch updating database...")
  update_preprocessed_posts(updates)

  # Batch-increment match_count for all anchors that fired this run
  increment_anchor_match_counts(fired_anchor_ids)

  _print_report(stats, quality.stats)
  return stats


def _print_report(stats: PreprocessStats, quality_stats) -> None:
  print(f"\nPreprocessing DB Batch")
  print(f"  Input posts:        {stats.input_total}")
  print(f"  Quality passed:     {stats.quality_passed}")
  print(f"    too short:        {quality_stats.too_short}")
  print(f"    non-english:      {quality_stats.non_english}")
  print(f"  SBERT scored:       {stats.sbert_scored}")
  print(f"  SBERT >= {SBERT_THRESHOLD}:     {stats.sbert_passed}")
  print(f"  SBERT <  {SBERT_THRESHOLD}:     {stats.sbert_failed}")
  if stats.by_source:
    print("  By source:")
    for source, counts in sorted(stats.by_source.items()):
      print(
        f"    {source}: in={counts['input']} "
        f"quality={counts['quality_passed']} "
        f"sbert_pass={counts['sbert_passed']}"
      )


def main():
  parser = argparse.ArgumentParser(description="Run preprocessing on DB queue")
  parser.add_argument(
    "--limit",
    type=int,
    default=1000,
    help="Max number of unprocessed posts to fetch",
  )
  args = parser.parse_args()
  run_preprocessing(limit=args.limit)


if __name__ == "__main__":
  main()
