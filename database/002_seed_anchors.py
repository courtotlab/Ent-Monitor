"""
Cold-start seed for sbert_anchors. Postgres init scripts can't run Python,
so run this once manually after `docker compose up -d`:
    uv sync
    uv run python database/002_seed_anchors.py
"""

import os

import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

DATABASE_URL = os.getenv(
  "DATABASE_URL",
  "postgresql://ent_admin:localdevpassword@localhost:5432/ent_surveillance",
)

SEED_ANCHORS = [
  "garlic clove inserted into ear canal as home remedy",
  "onion poultice applied to ear for infection",
  "ear candling to remove earwax",
  "cotton swab pushed deep into ear canal",
  "tonsil stone removed with bobby pin or sharp tool",
  "hydrogen peroxide poured into child's ear",
  "essential oil dripped into ear for pain relief",
  "foreign object inserted into nose as a dare",
  "bobby pin used to scratch or clean inside ear",
  "vinegar ear rinse for infection",
  "popping ear with a sharp object",
  "child swallowing foreign object as a challenge",
  "DIY ear piercing at home",
  "extracting earwax with a hairpin",
  "nasal irrigation with unsafe homemade solution",
  "stuffing tissue or cotton into ear to stop pain",
  "teen daring another teen to insert object in nose",
  "natural remedy for ear infection using kitchen ingredients",
  "ASMR video of squeezing or extracting tonsil stones",
  "parent treating child's ear infection without doctor",
]

NEWS_ANCHORS = [
  "child taken to emergency room after viral social media challenge",
  "teen hospitalized following TikTok dare",
  "parents warned about dangerous internet trend",
  "pediatric emergency spike linked to online challenge",
  "ER sees increase in children with object stuck in ear",
  "hospital reports unusual injuries from social media behavior",
  "viral challenge sends kids to hospital",
  "doctor warns about dangerous TikTok trend",
  "child hurt copying online video",
  "warning issued after children copy dangerous social media stunt",
]


def main():
  model = SentenceTransformer("all-MiniLM-L6-v2")
  conn = psycopg2.connect(DATABASE_URL)
  cur = conn.cursor()

  for text in SEED_ANCHORS:
    emb = model.encode(text).tolist()
    emb_str = "[" + ",".join(str(x) for x in emb) + "]"
    cur.execute(
      """
        INSERT INTO sbert_anchors (anchor_text, embedding, source, active, added_by)
        VALUES (%s, %s::vector, 'manual', TRUE, 'cold_start_seed')
        ON CONFLICT (anchor_text) DO NOTHING
      """,
      (text, emb_str),
    )

  for text in NEWS_ANCHORS:
    emb = model.encode(text).tolist()
    emb_str = "[" + ",".join(str(x) for x in emb) + "]"
    cur.execute(
      """
        INSERT INTO sbert_anchors (anchor_text, embedding, source, active, added_by)
        VALUES (%s, %s::vector, 'news_outcome', TRUE, 'cold_start_seed')
        ON CONFLICT (anchor_text) DO NOTHING
      """,
      (text, emb_str),
    )

  conn.commit()
  cur.close()
  conn.close()
  print(
    f"Seeded {len(SEED_ANCHORS)} manual anchors and {len(NEWS_ANCHORS)} news_outcome anchors."
  )


if __name__ == "__main__":
  main()
