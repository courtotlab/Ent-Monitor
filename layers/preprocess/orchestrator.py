import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .filter import run_quality_filter
from .queries import fetch_active_anchors, insert_post, update_sbert_score
from .semantic_filter import SBERT_THRESHOLD, SbertFilter


@dataclass
class PreprocessStats:
  input_total: int = 0
  quality_passed: int = 0
  quality_dropped: int = 0
  inserted: int = 0
  duplicate_db: int = 0
  sbert_scored: int = 0
  sbert_passed: int = 0
  sbert_failed: int = 0
  by_source: dict[str, dict[str, int]] = field(default_factory=dict)


def _latest_results_file(results_dir: Path) -> Path | None:
  files = sorted(results_dir.glob("collection_*.json"), reverse=True)
  return files[0] if files else None


def load_posts(path: Path) -> list[dict[str, Any]]:
  with path.open(encoding="utf-8") as f:
    data = json.load(f)
  if not isinstance(data, list):
    raise ValueError(f"Expected a JSON array in {path}")
  return data


def run_preprocessing(results_file: str | None = None) -> PreprocessStats:
  results_dir = Path("results")
  path = Path(results_file) if results_file else _latest_results_file(results_dir)
  if not path or not path.exists():
    raise FileNotFoundError(
      "No results file found. Run ingestion first or pass --results-file."
    )

  posts = load_posts(path)
  stats = PreprocessStats(input_total=len(posts))

  quality = run_quality_filter(posts)
  stats.quality_passed = quality.stats.passed
  stats.quality_dropped = (
    stats.input_total - stats.quality_passed - quality.stats.duplicate_in_batch
  )

  anchors = fetch_active_anchors()
  sbert = SbertFilter()
  sbert.load_anchors(anchors)

  scored = sbert.score_posts(quality.survivors)
  score_by_key = {(post["post_id"], post["platform"]): score for post, score in scored}

  filtered_posts = []

  for post in quality.survivors:
    key = (post["post_id"], post["platform"])
    score = score_by_key.get(key, 0.0)
    source = post.get("source", "unknown")

    if source not in stats.by_source:
      stats.by_source[source] = {
        "input": 0,
        "quality_passed": 0,
        "inserted": 0,
        "sbert_passed": 0,
      }
    stats.by_source[source]["input"] += 1
    stats.by_source[source]["quality_passed"] += 1

    inserted = insert_post(post, sbert_score=score)
    if inserted:
      stats.inserted += 1
      stats.by_source[source]["inserted"] += 1
    else:
      stats.duplicate_db += 1
      update_sbert_score(post["post_id"], post["platform"], score)

    stats.sbert_scored += 1
    if sbert.passes_threshold(score):
      stats.sbert_passed += 1
      stats.by_source[source]["sbert_passed"] += 1
      if inserted:
        post_with_score = dict(post)
        post_with_score["sbert_score"] = score
        filtered_posts.append(post_with_score)
    else:
      stats.sbert_failed += 1

  filtered_dir = results_dir / "filtered"
  filtered_dir.mkdir(parents=True, exist_ok=True)
  filtered_path = filtered_dir / path.name
  with filtered_path.open("w", encoding="utf-8") as f:
    json.dump(filtered_posts, f, indent=2, ensure_ascii=False)

  _print_report(path, stats, quality.stats)
  return stats


def _print_report(path: Path, stats: PreprocessStats, quality_stats) -> None:
  print(f"\nPreprocessing: {path.name}")
  print(f"  Input posts:        {stats.input_total}")
  print(f"  Quality passed:     {stats.quality_passed}")
  print(f"    too short:        {quality_stats.too_short}")
  print(f"    non-english:      {quality_stats.non_english}")
  print(f"    batch duplicates: {quality_stats.duplicate_in_batch}")
  print(f"    bot flagged:      {quality_stats.bot_flagged} (logged, not dropped)")
  print(f"  DB inserted:        {stats.inserted}")
  print(f"  DB duplicates:      {stats.duplicate_db}")
  print(f"  SBERT scored:       {stats.sbert_scored}")
  print(f"  SBERT >= {SBERT_THRESHOLD}:     {stats.sbert_passed}")
  print(f"  SBERT <  {SBERT_THRESHOLD}:     {stats.sbert_failed}")
  if stats.by_source:
    print("  By source:")
    for source, counts in sorted(stats.by_source.items()):
      print(
        f"    {source}: in={counts['input']} "
        f"quality={counts['quality_passed']} "
        f"inserted={counts['inserted']} "
        f"sbert_pass={counts['sbert_passed']}"
      )


def main():
  parser = argparse.ArgumentParser(description="Run preprocessing on ingestion results")
  parser.add_argument(
    "--results-file",
    type=str,
    help="Path to collection JSON (default: latest in results/)",
  )
  args = parser.parse_args()
  run_preprocessing(results_file=args.results_file)


if __name__ == "__main__":
  main()
