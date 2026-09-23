"""
Cold-start seed for creators. Postgres init scripts can't run Python,
so run this once manually after `docker compose up -d`:
  uv sync
  uv run python database/003_seed_creators.py
"""

import json
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
  raise ValueError("DATABASE_URL environment variable is required")


def extract_creator_id(url_or_handle: str) -> str:
  """Extract clean handle from any profile URL or raw identifier."""
  return url_or_handle.rstrip("/").split("/")[-1].lstrip("@")


def seed_creators():
  config_path = os.path.join(os.path.dirname(__file__), "..", "config", "creators.json")

  with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)

  print("Connecting to database...")
  conn = psycopg2.connect(DATABASE_URL)
  cursor = conn.cursor()

  inserted = 0
  total_processed = 0

  for platform_key, creators in data.items():
    platform = platform_key.lower()

    for item in creators:
      raw = item if isinstance(item, str) else item.get("social_link", "")
      if not raw: continue
      creator_id = extract_creator_id(raw)

      total_processed += 1

      try:
        cursor.execute(
          """
          INSERT INTO creators (creator_id, platform)
          VALUES (%s, %s)
          ON CONFLICT (creator_id, platform) DO NOTHING
          RETURNING creator_id;
          """,
          (creator_id, platform),
        )
        if cursor.fetchone(): inserted += 1
      except psycopg2.Error as e:
        print(f"Error inserting {creator_id} on {platform}: {e}")
        conn.rollback()
        continue

  conn.commit()
  cursor.close()
  conn.close()

  print(f"Processed {total_processed} creator(s) from config.")
  if inserted == 0 and total_processed > 0:
    print("Creator(s) already in the DB! (0 new inserts)")
  else:
    print(f"Successfully inserted {inserted} new creator(s) into the database.")


if __name__ == "__main__":
  seed_creators()
