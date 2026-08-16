import argparse
import json
import logging
import sys
from pathlib import Path

# Add the root directory to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from layers.analysis.core.graph import run_analysis
from layers.analysis.db.queries import fetch_unprocessed_posts

# Optional: configure root logger to mirror the analysis.log formatting to console
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
  parser = argparse.ArgumentParser(
    description="Run the Layer 3 Analysis Pipeline."
  )
  parser.add_argument(
    "--input_file",
    help="Optional path to a JSON file. If omitted, fetches unprocessed posts from the database.",
    default=None
  )
  args = parser.parse_args()

  if args.input_file:
    input_path = Path(args.input_file)
    if not input_path.exists():
      print(f"Error: File {input_path} does not exist.")
      sys.exit(1)
    print(f"Loading posts from {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
      posts = json.load(f)
  else:
    print("Fetching unprocessed posts from database...")
    posts = fetch_unprocessed_posts(threshold=0.38)
    if not posts:
      print("No new posts to process.")
      return

  print(
    f"Fetched {len(posts)} posts. Starting pipeline (this may take a few minutes)..."
  )

  # run_analysis automatically handles the run_id, circuit breakers, and writes to results/final/
  result = run_analysis(posts)

  print("\n" + "=" * 50)
  print(" PIPELINE COMPLETED ")
  print("=" * 50)
  print(f"Run ID: {result.get('run_id')}")
  print(f"Number of clusters analyzed: {len(result.get('clusters', []))}")
  print(f"Summary written to: results/final/{result.get('run_id')}/run_summary.json")
  print("Full logs available at: layers/analysis/analysis.log")


if __name__ == "__main__":
  main()
