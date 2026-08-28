"""
Cold-start seed for creators. Postgres init scripts can't run Python,
so run this once manually after `docker compose up -d`:
    uv sync
    uv run python database/003_seed_creators.py
"""

import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
  "DATABASE_URL",
  "postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance",
)

def extract_creator_id(url: str, platform: str) -> str:
  url = url.rstrip('/')
    
  if platform == "tiktok": return url.split("@")[-1]
  elif platform == "instagram": return url.split("/")[-1]
  elif platform == "youtube":
    if "@" in url: return url.split("@")[-1]
    return url.split("/")[-1]
  elif platform == "reddit": return url.split("/")[-1]
        
  return url.split("/")[-1]

def seed_creators():
  config_path = os.path.join(os.path.dirname(__file__), "..", "config", "creators.json")
    
  with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)
        
  print(f"Connecting to {DATABASE_URL}...")
  conn = psycopg2.connect(DATABASE_URL)
  cursor = conn.cursor()
    
  inserted = 0
  total_processed = 0
    
  for platform_key, creators in data.items():
    platform = platform_key.lower() # tiktok, instagram, etc.
        
    for item in creators:
      if isinstance(item, str):
        creator_id = item
      else:
        social_link = item.get("social_link")
        if not social_link: continue
        creator_id = extract_creator_id(social_link, platform)
            
      total_processed += 1
            
      try:
        cursor.execute(
          """
          INSERT INTO creators (creator_id, platform)
          VALUES (%s, %s)
          ON CONFLICT (creator_id, platform) DO NOTHING
          RETURNING creator_id;
          """,
          (creator_id, platform)
        )
        if cursor.fetchone(): inserted += 1
      except Exception as e:
        print(f"Error inserting {creator_id} on {platform}: {e}")
        conn.rollback()
        continue
                
  conn.commit()
  cursor.close()
  conn.close()
    
  print(f"Processed {total_processed} creators from config.")
  print(f"Successfully inserted {inserted} new creators into the database.")

if __name__ == "__main__":
  seed_creators()
