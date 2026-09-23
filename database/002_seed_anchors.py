"""
Cold-start seed for sbert_anchors. Postgres init scripts can't run Python,
so run this once manually after `docker compose up -d`:
    uv sync
    uv run python database/002_seed_anchors.py
"""

import json
import os

import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
  raise ValueError("DATABASE_URL environment variable is required")


def load_anchors(name: str) -> list[str]:
  """Load and flatten categorized anchors from config JSON."""
  path = os.path.join(os.path.dirname(__file__), "..", "config", f"{name}.json")
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  return [item for group in data.values() for item in group] if isinstance(data, dict) else data


def seed_anchors():
  print("Loading SBERT model (all-MiniLM-L6-v2)...")
  model = SentenceTransformer("all-MiniLM-L6-v2")

  print("Connecting to database...")
  conn = psycopg2.connect(DATABASE_URL)
  cur = conn.cursor()

  for source, filename in [("manual", "seed_anchors"), ("news_outcome", "news_anchors")]:
    anchors = load_anchors(filename)
    for text in anchors:
      emb = model.encode(text).tolist()
      cur.execute(
        """
        INSERT INTO sbert_anchors (anchor_text, embedding, source)
        VALUES (%s, %s::vector, %s)
        ON CONFLICT (anchor_text) DO NOTHING
        """,
        (text, f"[{','.join(map(str, emb))}]", source),
      )
    print(f"Seeded {len(anchors)} {source} anchors from {filename}.json.")

  conn.commit()
  cur.close()
  conn.close()


if __name__ == "__main__":
  seed_anchors()
