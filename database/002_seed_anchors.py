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
  # hazardous ingestion
  "swallowing laundry detergent pods as a viral dare",
  "eating a household cleaning product on camera as a challenge",
  "taking a large excess dose of over-the-counter allergy medicine to get high",
  "consuming cough and cold medicine at far higher than the recommended dose for a high",
  "cooking food in cough or cold medicine and eating it as a viral stunt",
  "swallowing small magnets as part of an online dare",
  "swallowing a button battery on a dare",
  "eating an inedible part of food, like a shell or peel, as a viral challenge",
  "mixing multiple medications together and consuming them on camera",
  "drinking a household chemical or cleaning product as a stunt",
  
  # asphyxiation
  "choking yourself or a friend until passing out as a viral game",
  "holding your breath until losing consciousness for an online challenge",
  "strangling yourself with a belt or cord until blacking out, filmed for social media",
  "a blackout challenge where teens choke themselves until they pass out",
  "cutting off airflow to get a head rush as a dare",
  "restricting your own breathing for a euphoric feeling and filming it",
  
  # inhalant misuse
  "inhaling aerosol spray cans to get high, sometimes called chroming",
  "huffing compressed air duster or spray paint fumes for a euphoric effect",
  "inhaling alkyl nitrite poppers for a head rush",
  "breathing in dry ice fumes in an enclosed space as a stunt",
  "sniffing household chemicals to get high on camera",
 
  # self-inflicted pain
  "pressing salt and ice together on skin to see how long you can stand the burn",
  "rubbing a pencil eraser repeatedly on skin until it burns, as a school dare",
  "holding dry ice directly against bare skin as a challenge",
  "eating a liquid-nitrogen frozen snack and getting a cold burn to the mouth or throat",
  "applying extreme heat or cold to skin as an online pain-tolerance dare",
  "burning your own skin with a lighter or hot object for a video",
 
  # foreign object dare
  "inserting a condom into the nose and pulling it out through the mouth as a stunt",
  "pushing a small object like a bead or toy into the nose as a dare",
  "inserting a sharp or foreign object into the ear canal on a dare",
  "sticking objects up the nose to see how far they go, filmed for views",
  "swallowing a coin or small toy as part of a social media challenge",
 
  # fire and projectile
  "spraying aerosol or lighter fluid near an open flame to create a fireball for a video",
  "swallowing or gargling lighter fluid as part of a dare",
  "shooting strangers with a gel bead gun as a street prank challenge",
  "setting a small fire on your own skin or clothing for a viral video",
 
  # DIY medical misinformation
  "diagnosing a baby's tongue-tie at home without a doctor using a social media checklist",
  "flushing an infant's nose with tap water instead of sterile saline",
  "putting garlic oil or essential oil drops directly into a child's ear to treat an infection at home",
  "treating a child's ear or sinus infection using only kitchen ingredients instead of seeing a doctor",
  "performing a hearing test on a child using phone speakers instead of professional equipment",
  "pouring bleach or other household chemicals into a child's nose or ear as a home remedy",
  "using an undiluted corrosive cleaning product on a child's nose or ear to treat congestion or infection",
  "squirting hydrogen peroxide directly into a child's nose to clear congestion",
  "applying a caustic or chemical substance inside a child's nasal cavity or ear canal instead of seeing a doctor",
 
  # viral format signals
  "a viral dare on social media telling viewers not to try this at home",
  "an online challenge going wrong and requiring emergency medical attention",
  "a video captioned 'don't do this' that shows viewers a dangerous stunt anyway",
  "teens filming themselves attempting a risky viral trend for views",
  "a new social media challenge spreading quickly among teenagers with its own hashtag",
 
  # generic dare structure (name-agnostic, for novel trends)
  "a new online challenge telling viewers to try something risky with a common household item",
  "a video using an everyday object in an unsafe or unintended way for views",
  "a challenge encouraging viewers to ingest, inhale, or apply something not meant for that use",
  "a trend that starts as a joke but leads to real injuries requiring medical attention",
  "a challenge with an unfamiliar name and its own hashtag spreading quickly among teenagers",
  "a video where someone is dared by friends or commenters to attempt something unsafe",
  "step-by-step instructions for a risky stunt framed as a fun trend to try",
  "a challenge encouraging viewers to film themselves attempting something painful or dangerous",
 
  # escalation and competition
  "participants competing to outlast each other in a risky physical dare",
  "each new video in a trend attempting a more extreme version than the last",
  "a challenge that got more dangerous over time as people tried to one-up each other",
  "seeing how far or how long someone can push an unsafe stunt for more views",
  "a mild prank format that gradually escalates into something genuinely harmful",
 
  # disclaimer-then-demonstrate framing
  "a caption warning 'don't try this at home' immediately followed by someone doing it anyway",
  "a video framed as a warning that ends up giving full instructions for a dangerous stunt",
  "a reaction or news video that unintentionally teaches viewers how to do a harmful trend",
  "content claiming to expose a dangerous challenge while showing it being performed in detail",
 
  # extreme consumption stunt
  "eating an extremely spicy food until vomiting or passing out for a video",
  "eating or drinking something at an extreme temperature as fast as possible for a challenge",
  "consuming a very large quantity of food or a substance in one sitting for an online dare",
  "a speed-eating or endurance-eating stunt performed for social media views",
 
  # object in body orifice
  "inserting an unusual household object into the nose, ear, or mouth as a stunt",
  "a competition to see how far an object can be pushed into a body opening",
  "pulling an object through one body opening and out another as a viral trick",
   
  # unsupervised chemical mixing
  "combining ordinary household products to create a dangerous reaction for a video",
  "mixing chemicals or cleaning products not meant to be combined to see what happens on camera",
  "an at-home experiment using household chemicals that produces toxic gas or fire",
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
        INSERT INTO sbert_anchors (anchor_text, embedding, source)
        VALUES (%s, %s::vector, 'manual')
        ON CONFLICT (anchor_text) DO NOTHING
      """,
      (text, emb_str),
    )

  for text in NEWS_ANCHORS:
    emb = model.encode(text).tolist()
    emb_str = "[" + ",".join(str(x) for x in emb) + "]"
    cur.execute(
      """
        INSERT INTO sbert_anchors (anchor_text, embedding, source)
        VALUES (%s, %s::vector, 'news_outcome')
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
