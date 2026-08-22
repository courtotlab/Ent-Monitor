import logging
import sys
from pathlib import Path

# Add the root directory to path so imports work correctly when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from layers.analysis.core.graph import run_analysis
from layers.analysis.db.queries import fetch_unprocessed_posts


def main():

  print("Fetching unprocessed posts from database...")
  posts = fetch_unprocessed_posts(threshold=0.3)
  if not posts:
    print("No new posts to process.")
    return

  print(
    f"Fetched {len(posts)} posts. Starting pipeline (this may take a few minutes)..."
  )

  # run_analysis automatically handles the run_id and circuit breakers.
  result = run_analysis(posts)

  print(" PIPELINE COMPLETED ")
  print("=" * 50)
  print(f"Number of clusters analyzed: {len(result.get('clusters', []))}")

if __name__ == "__main__":
  main()
