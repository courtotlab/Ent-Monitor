import datetime
import io
import re
import zipfile
import asyncio
import os

import pandas as pd
import requests
import spacy
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from psycopg2.extras import Json
from apify import Actor

from layers.ingestion.shared.queries import (
  fetch_sbert_anchors_with_source,
  get_gdelt_last_polled_url,
  get_recent_gdelt_seen_urls,
  insert_news_trend_signal,
  update_gdelt_last_polled_url,
  upsert_gdelt_seen_url,
  insert_post,
)
from layers.preprocess.semantic_filter import SbertFilter
from layers.ingestion.social.tiktok import scrape_tiktok_search
from layers.ingestion.social.instagram import scrape_instagram_search

USER_AGENT = "Mozilla/5.0 (compatible; ENTSurveillanceBot/1.0)"
LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

GKG_COLUMNS = [
  "GKGRECORDID",
  "DATE",
  "SourceCollectionIdentifier",
  "SourceCommonName",
  "DocumentIdentifier",
  "Counts",
  "V2Counts",
  "Themes",
  "V2Themes",
  "Locations",
  "V2Locations",
  "Persons",
  "V2Persons",
  "Organizations",
  "V2Organizations",
  "V2Tone",
  "Dates",
  "GCAM",
  "SharingImage",
  "RelatedImages",
  "SocialImageEmbeds",
  "SocialVideoEmbeds",
  "Quotations",
  "AllNames",
  "Amounts",
  "TranslationInfo",
  "Extras",
]

HEALTH_THEMES = {
  "HEALTH",
  "MEDICAL",
  "TAX_DISEASE",
  "TAX_FNCACT_DOCTOR",
  "TAX_FNCACT_NURSE",
  "TAX_FNCACT_PEDIATRICIAN",
  "TAX_FNCACT_PHARMACIST",
  "TAX_FNCACT_SURGEON",
  "WB_678_HEALTH_NUTRITION_AND_POPULATION",
  "WB_2319_CHILD_HEALTH",
  "MEDICAL_SAFETY",
  "EPU_CATS_HEALTHCARE",
  "TAX_DISEASE_INFECTIONS",
  "CRISISLEX_T02_INJURED_OR_DEAD_PEOPLE",
  "SELF_HARM",
  "GENERAL_HEALTH",
  "ENV_HEALTH",
}

GEOGRAPHY_LOCATIONS = {"US#", "GB#", "CA#", "AU#"}

SLUG_PATTERN = re.compile(
  r"ear|hearing|tonsil|nasal|nose|sinus|throat|child|infant|toddler|"
  r"baby|teen|teenager|pediatric|tiktok|challenge|viral|trend|remedy|"
  r"home[-\s]?treat|natural[-\s]?cure|infection|injury|foreign[-\s]?body|"
  r"hospital|emergency|warning|danger|harm|safety|social[-\s]?media|"
  r"dare|stunt|prank|swallow|inhale|insert|stuck",
  re.IGNORECASE,
)

CHALLENGE_PATTERN = re.compile(
  r"(?:the\s+)?([A-Z][a-zA-Z\s]{2,30}(?:Challenge|Trend|Dare|Stunt|Hack|Method|Trick|Remedy|Cure))",
  re.IGNORECASE,
)
TIKTOK_HASHTAG_PATTERN = re.compile(r"#([A-Za-z][A-Za-z0-9]{2,40})")

BLACKLIST_TERMS = {
  "health",
  "hospital",
  "doctor",
  "patient",
  "child",
  "teen",
  "parent",
  "injury",
  "symptom",
  "treatment",
  "emergency",
  "warning",
  "report",
  "study",
  "case",
}


def poll_gdelt_lastupdate() -> str | None:
  try:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(LAST_UPDATE_URL, headers=headers, timeout=10.0)
    resp.raise_for_status()

    gkg_url = None
    for line in resp.text.splitlines():
      if "gkg.csv.zip" in line:
        gkg_url = line.split(" ")[-1]
        break

    if not gkg_url:
      return None

    last_url = get_gdelt_last_polled_url()
    if gkg_url == last_url:
      return None

    return gkg_url
  except Exception:
    return None


def download_and_parse_gkg(url: str) -> pd.DataFrame:
  headers = {"User-Agent": USER_AGENT}
  resp = requests.get(url, headers=headers, timeout=30.0)
  resp.raise_for_status()

  with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
    csv_filename = z.namelist()[0]
    with z.open(csv_filename) as f:
      df = pd.read_csv(
        f,
        sep="\t",
        header=None,
        names=GKG_COLUMNS,
        on_bad_lines="skip",
        low_memory=False,
        dtype=str,
      )

  df = df.dropna(subset=["DocumentIdentifier"])
  df = df[df["DocumentIdentifier"].str.strip() != ""]
  df = df[df["DocumentIdentifier"].str.startswith("http")]

  return df


def extract_slug(url: str) -> str:
  try:
    return url.split("?")[0].rstrip("/").split("/")[-1]
  except (IndexError, AttributeError):
    return ""


def _parse_tone(tone_str, default=0.0):
  if pd.isna(tone_str) or not str(tone_str).strip():
    return default

  try:
    return float(str(tone_str).split(",")[0])
  except ValueError:
    return default


def run_preprocessing_funnel(df: pd.DataFrame) -> pd.DataFrame:
  """
  Preprocessing Stages for GDELT data:
  - Stage 1 (Themes): Coarse filter keeping only articles with health/danger related themes.
  - Stage 2 (Geography): Filter to keep only articles from target regions (US, GB, CA, AU).
  - Stage 3 (Deduplication): Remove recently seen URLs and limit to top 3 most negative articles per source.
  - Stage 4 (Slug): Filter for URL slugs matching specific danger/health keywords.
  - Stage 5 (Tone): Keep articles with tone <= 1.0, or bypass if URL contains viral keywords.
  - Stage 6 (Proxy SBERT): Filter using SBERT on proxy texts built from metadata.
  - Stage 7 (Final SBERT): Filter using SBERT on the full scraped article text.
  """
  # Stage 1: V2Themes coarse filter
  df = df.dropna(subset=["V2Themes"])
  df = df[df["V2Themes"].apply(lambda ts: isinstance(ts, str) and not HEALTH_THEMES.isdisjoint({t.split(",")[0] for t in ts.split(";")}))]
  print(f"[GDELT] Stage 1 (Themes) survivors: {len(df)}")

  # Stage 2: Geography filter
  df = df[df["V2Locations"].apply(lambda loc: pd.isna(loc) or not str(loc).strip() or any(geo in str(loc) for geo in GEOGRAPHY_LOCATIONS))]
  print(f"[GDELT] Stage 2 (Geography) survivors: {len(df)}")

  seen_urls = get_recent_gdelt_seen_urls()
  df = df[~df["DocumentIdentifier"].isin(seen_urls)]

  df["parsed_tone"] = df["V2Tone"].apply(_parse_tone)
  df["abs_tone"] = df["parsed_tone"].abs()
  df = df.sort_values("abs_tone", ascending=False).groupby("SourceCommonName").head(3)
  df = df.drop(columns=["parsed_tone", "abs_tone"])
  print(f"[GDELT] Stage 3 (Deduplication) survivors: {len(df)}")

  # Stage 4: URL slug signal filter
  df = df[df["DocumentIdentifier"].apply(lambda url: SLUG_PATTERN.search(extract_slug(url).replace("-", " ").replace("_", " ")) is not None)]
  print(f"[GDELT] Stage 4 (Slug) survivors: {len(df)}")

  # Stage 5: V2Tone filter
  def s5(r):
    slug = extract_slug(str(r.get("DocumentIdentifier", ""))).replace("-", " ").replace("_", " ")
    if CHALLENGE_PATTERN.search(slug) or any(w in slug.lower() for w in ["tiktok", "instagram", "viral"]): return True
    return _parse_tone(r.get("V2Tone", ""), 999.0) <= 1.0

  df = df[df.apply(s5, axis=1)]
  print(f"[GDELT] Stage 5 (Tone) survivors: {len(df)}")
  return df


def build_proxy_texts(df: pd.DataFrame) -> list[str]:
  return [f"{extract_slug(str(r.get('DocumentIdentifier', ''))).replace('-', ' ').replace('_', ' ')}. {str(r.get('Quotations', '')).split('#')[0][:150].strip()}. {str(r.get('SourceCommonName', '') or '')}. {str(r.get('AllNames', '')).replace(',', ' ').replace(';', ' ')[:100]}".strip() for _, r in df.iterrows()]


def run_proxy_sbert(proxy_texts: list[str], anchors: list[tuple[int, str, list[float]]], sbert_filter: SbertFilter, threshold: float = 0.28) -> list[int]:
  if not proxy_texts or not anchors: return []
  sbert_filter.load_anchors(anchors)
  scores = sbert_filter.score_texts(proxy_texts)
  return [i for i, score in enumerate(scores) if score >= threshold]


def fetch_article_content(url: str) -> tuple[str, str]:
  try:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, timeout=4, stream=True, headers=headers)
    resp.raise_for_status()
    partial = b""
    for chunk in resp.iter_content(1024):
      partial += chunk
      if len(partial) >= 8192: break
    soup = BeautifulSoup(partial, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    snippet = ""
    for p in soup.find_all("p"):
      text = p.get_text().strip()
      if len(text) > 50:
        snippet = text[:300]
        break
    return title, snippet
  except Exception:
    return "", ""


def run_final_sbert(articles: list[dict], anchors: list[tuple[int, str, list[float]]], sbert_filter: SbertFilter, threshold: float = 0.35) -> list[dict]:
  if not articles or not anchors: return []
  sbert_filter.load_anchors(anchors)
  scores = sbert_filter.score_texts([a["full_text"] for a in articles])
  confirmed = []
  for i, score in enumerate(scores):
    if score >= threshold:
      articles[i]["sbert_score"] = float(score)
      confirmed.append(articles[i])
  return confirmed


def extract_search_terms(article: dict, nlp) -> list[str]:
  text, terms = article["full_text"], []
  if m := CHALLENGE_PATTERN.search(text): terms.append(m.group(1).strip())
  if m := TIKTOK_HASHTAG_PATTERN.search(text): terms.append(m.group(1).strip())

  chunks = [c.lemma_.lower().strip() for c in nlp(article["behavioral_extract"]).noun_chunks if c.root.pos_ == "NOUN" and not c.root.is_stop and len(c.lemma_.strip()) >= 2]
  terms.extend(sorted([c for c in chunks if c not in BLACKLIST_TERMS], key=lambda x: len(x.split()), reverse=True)[:3])
  
  final = list(dict.fromkeys(t for t in terms if t.lower().strip()))[:3]
  return final or ([article["article_title"][:50]] if article.get("article_title") else [])


def write_to_db(confirmed_articles: list[dict]):
  for article in confirmed_articles:
    url, title, source_name, date_str, score, extract, search_terms = (
      article["article_url"], article["article_title"], article["source_name"],
      article["article_date"], article["sbert_score"], article["behavioral_extract"], article["search_terms"]
    )
    try:
      dt = datetime.datetime.strptime(date_str, "%Y%m%d%H%M%S").replace(tzinfo=datetime.UTC)
    except ValueError:
      dt = datetime.datetime.now(datetime.UTC)

    for term in search_terms:
      insert_news_trend_signal(Json({"news_source_url": url, "news_source_name": source_name, "news_article_title": title, "news_article_date": dt.isoformat(), "news_sbert_score": score, "news_behavioral_extract": extract}), term)
    upsert_gdelt_seen_url(url)


async def main():
  load_dotenv()
  try:
    print("[GDELT] Polling for new batch...")
    if not (gkg_url := poll_gdelt_lastupdate()):
      print("[GDELT] No new batch found. Skipping.")
      return

    print(f"[GDELT] Downloading and parsing new batch: {gkg_url}")
    df = download_and_parse_gkg(gkg_url)
    print(f"[GDELT] Loaded {len(df)} raw rows.")

    print("[GDELT] Running preprocessing funnel (Stages 1-5)...")
    df_filtered = run_preprocessing_funnel(df)
    if df_filtered.empty: return
    print(f"[GDELT] {len(df_filtered)} rows survived the preprocessing funnel.")

    print("[GDELT] Building proxy texts for Stage 6...")
    proxy_texts = build_proxy_texts(df_filtered)
    anchors = fetch_sbert_anchors_with_source(["manual", "news_outcome"])
    sbert_filter = SbertFilter()

    print("[GDELT] Running Stage 6 (Batch Proxy SBERT)...")
    stage6_indices = run_proxy_sbert(proxy_texts, anchors, sbert_filter, threshold=0.28)
    print(f"[GDELT] {len(stage6_indices)} articles passed Stage 6.")

    print("[GDELT] Fetching article content for Stage 7 candidates...")
    stage7_candidates = []
    for idx in stage6_indices:
      row = df_filtered.iloc[idx]
      url = row["DocumentIdentifier"]
      title, snippet = fetch_article_content(url)
      if title or snippet:
        stage7_candidates.append({"article_url": url, "source_name": str(row.get("SourceCommonName", "")), "article_date": str(row.get("DATE", "")), "article_title": title, "behavioral_extract": snippet, "full_text": f"{title}. {snippet}"})

    print(f"[GDELT] Running Stage 7 (Final SBERT) on {len(stage7_candidates)} candidates...")
    if confirmed_articles := run_final_sbert(stage7_candidates, anchors, sbert_filter, threshold=0.35):
      print(f"[GDELT] {len(confirmed_articles)} articles passed final SBERT.")
      print("[GDELT] Extracting search terms...")
      try:
        nlp = spacy.load("en_core_web_sm")
      except OSError as exc:
        raise RuntimeError("The en_core_web_sm model must be installed in the runtime image.") from exc

      for art in confirmed_articles:
        art["search_terms"] = extract_search_terms(art, nlp)

      print("[GDELT] Writing results to database...")
      write_to_db(confirmed_articles)
      print(f"[GDELT] Saved {len(confirmed_articles)} actionable stories to DB.")

      if client := Actor.new_client(token=os.getenv("APIFY_TOKEN")) if os.getenv("APIFY_TOKEN") else None:
        all_terms = list(set(term for art in confirmed_articles for term in art.get("search_terms", [])))
        if all_terms:
          print(f"[GDELT] Fetching social posts inline for {len(all_terms)} extracted keywords...")
          for term in all_terms:
            try:
              results = await asyncio.gather(
                scrape_tiktok_search(client, [term], limit_posts=5, source="gdelt_news"),
                scrape_instagram_search(client, [term], limit_posts=5, source="gdelt_news"),
                return_exceptions=True,
              )
              all_posts = []
              for r in results:
                if isinstance(r, list): all_posts.extend(r)
                else: print(f"Scrape task failed for term '{term}': {r}")
              
              if all_posts:
                posts_dicts = [p.to_dict() for p in all_posts]
                post_scores = sbert_filter.score_texts([(p.get("caption_text") or "") + " " + (p.get("transcript_text") or "") for p in posts_dicts])
                
                inserted_count = 0
                for post, score in zip(posts_dicts, post_scores):
                  post["source"] = "gdelt_news"
                  if insert_post(post, float(score)): inserted_count += 1
                print(f"  -> Saved {inserted_count} new posts into DB for '{term}'")
            except Exception as e:
              print(f"[GDELT] Inline Apify fetch failed for '{term}': {e}")

    update_gdelt_last_polled_url(gkg_url)

  except Exception as e:
    print(f"Error: {e}")

if __name__ == "__main__":
  asyncio.run(main())
