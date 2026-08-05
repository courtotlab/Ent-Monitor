import datetime
import io
import re
import zipfile

import pandas as pd
import requests
import spacy
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from psycopg2.extras import Json

from layers.preprocess.queries import fetch_active_anchors
from layers.preprocess.semantic_filter import SbertFilter
from layers.shared.db import get_connection

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

    with get_connection() as conn, conn.cursor() as cur:
      cur.execute("SELECT state_value->>'last_url' FROM pipeline_state WHERE state_key = 'gdelt_poll'")
      row = cur.fetchone()
      last_url = row[0] if row else None
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

  def has_health_theme(themes_str):
    if not isinstance(themes_str, str):
      return False
    themes_set = {t.split(",")[0] for t in themes_str.split(";")}
    return len(themes_set.intersection(HEALTH_THEMES)) > 0

  df = df[df["V2Themes"].apply(has_health_theme)]
  print(f"[GDELT] Stage 1 (Themes) survivors: {len(df)}")


  # Stage 2: Geography filter
  def has_geography(loc_str):
    if pd.isna(loc_str) or not str(loc_str).strip():
      return True
    return any(geo in str(loc_str) for geo in GEOGRAPHY_LOCATIONS)

  df = df[df["V2Locations"].apply(has_geography)]
  print(f"[GDELT] Stage 2 (Geography) survivors: {len(df)}")


  # Stage 3: Source deduplication
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      "SELECT url FROM gdelt_seen_articles WHERE seen_at >= NOW() - INTERVAL '48 hours'"
    )
    seen_urls = {row[0] for row in cur.fetchall()}

  df = df[~df["DocumentIdentifier"].isin(seen_urls)]

  df["parsed_tone"] = df["V2Tone"].apply(_parse_tone)
  df["abs_tone"] = df["parsed_tone"].abs()

  df = df.sort_values("abs_tone", ascending=False).groupby("SourceCommonName").head(3)
  df = df.drop(columns=["parsed_tone", "abs_tone"])
  print(f"[GDELT] Stage 3 (Deduplication) survivors: {len(df)}")


  # Stage 4: URL slug signal filter
  def matches_slug(url):
    slug = extract_slug(url).replace("-", " ").replace("_", " ")
    return SLUG_PATTERN.search(slug) is not None

  df = df[df["DocumentIdentifier"].apply(matches_slug)]
  print(f"[GDELT] Stage 4 (Slug) survivors: {len(df)}")


  # Stage 5: V2Tone filter
  def stage5_filter(row):
    url = str(row.get("DocumentIdentifier", ""))
    slug = extract_slug(url).replace("-", " ").replace("_", " ")

    # Bypass tone filter if it matches the formal challenge pattern or social media platforms
    if CHALLENGE_PATTERN.search(slug) or any(
      w in slug.lower() for w in ["tiktok", "instagram", "viral"]
    ):
      return True  # Bypass tone filter entirely for high-signal keywords

    tone_str = row.get("V2Tone", "")
    return _parse_tone(tone_str, default=999.0) <= 1.0

  df = df[df.apply(stage5_filter, axis=1)]
  print(f"[GDELT] Stage 5 (Tone) survivors: {len(df)}")

  return df


def build_proxy_texts(df: pd.DataFrame) -> list[str]:
  texts = []
  for _, row in df.iterrows():
    slug = extract_slug(str(row.get("DocumentIdentifier", "")))
    slug_readable = slug.replace("-", " ").replace("_", " ")
    source = str(row.get("SourceCommonName", "") or "")

    quotations = str(row.get("Quotations", "") or "")
    first_quote = quotations.split("#")[0][:150].strip()

    all_names = str(row.get("AllNames", "") or "")
    names_readable = all_names.replace(",", " ").replace(";", " ")[:100]

    texts.append(f"{slug_readable}. {first_quote}. {source}. {names_readable}".strip())
  return texts


def run_proxy_sbert(
  proxy_texts: list[str],
  anchors: list[tuple[str, list[float]]],
  sbert_filter: SbertFilter,
  threshold: float = 0.28,
) -> list[int]:
  if not proxy_texts or not anchors:
    return []

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
      if len(partial) >= 8192:
        break

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


def run_final_sbert(
  articles: list[dict],
  anchors: list[tuple[str, list[float]]],
  sbert_filter: SbertFilter,
  threshold: float = 0.35,
) -> list[dict]:
  if not articles or not anchors:
    return []

  sbert_filter.load_anchors(anchors)
  texts = [a["full_text"] for a in articles]
  scores = sbert_filter.score_texts(texts)

  confirmed = []
  for i, score in enumerate(scores):
    if score >= threshold:
      articles[i]["sbert_score"] = float(score)
      confirmed.append(articles[i])

  return confirmed


def extract_search_terms(article: dict, nlp) -> list[str]:
  terms = []
  text = article["full_text"]

  challenge_match = CHALLENGE_PATTERN.search(text)
  if challenge_match:
    terms.append(challenge_match.group(1).strip())

  hashtag_match = TIKTOK_HASHTAG_PATTERN.search(text)
  if hashtag_match:
    terms.append(hashtag_match.group(1).strip())

  doc = nlp(article["behavioral_extract"])
  chunks = [
    chunk.lemma_.lower().strip()
    for chunk in doc.noun_chunks
    if chunk.root.pos_ == "NOUN"
    and not chunk.root.is_stop
    and len(chunk.lemma_.strip()) >= 2
  ]

  filtered_chunks = [c for c in chunks if c not in BLACKLIST_TERMS]
  filtered_chunks.sort(key=lambda x: len(x.split()), reverse=True)

  terms.extend(filtered_chunks[:3])

  seen = set()
  final_terms = []
  for t in terms:
    t_clean = t.lower().strip()
    if t_clean not in seen:
      seen.add(t_clean)
      final_terms.append(t)

  final_terms = final_terms[:3]

  if not final_terms:
    title = article["article_title"]
    final_terms = [title[:50]] if title else []

  return final_terms


def write_to_db(confirmed_articles: list[dict]):
  if not confirmed_articles:
    return

  with get_connection() as conn, conn.cursor() as cur:
    for article in confirmed_articles:
      url = article["article_url"]
      title = article["article_title"]
      source_name = article["source_name"]
      date_str = article["article_date"]
      score = article["sbert_score"]
      extract = article["behavioral_extract"]
      search_terms = article["search_terms"]

      try:
        dt = datetime.datetime.strptime(date_str, "%Y%m%d%H%M%S").replace(tzinfo=datetime.UTC)
      except ValueError:
        dt = datetime.datetime.now(datetime.UTC)

      for term in search_terms:
        cur.execute(
          """
            INSERT INTO trend_signals (
              signal_type, signal_data,
              search_query, search_platforms,
              search_status, detected_at
            ) VALUES (
              'news_match', %s,
              %s, '["tiktok","instagram"]', 'pending', NOW()
            )
            ON CONFLICT DO NOTHING
          """,
          (
            Json({
              "news_source_url": url,
              "news_source_name": source_name,
              "news_article_title": title,
              "news_article_date": dt.isoformat(),
              "news_sbert_score": score,
              "news_behavioral_extract": extract,
            }),
            term,
          ),
        )

      cur.execute(
        """
          INSERT INTO gdelt_seen_articles (url, seen_at)
            VALUES (%s, NOW())
          ON CONFLICT (url) DO UPDATE SET seen_at = NOW()
        """,
        (url,),
      )


def main():
  load_dotenv()

  try:
    print("[GDELT] Polling for new batch...")
    gkg_url = poll_gdelt_lastupdate()
    if not gkg_url:
      print("[GDELT] No new batch found. Skipping.")
      return

    print(f"[GDELT] Downloading and parsing new batch: {gkg_url}")
    df = download_and_parse_gkg(gkg_url)
    print(f"[GDELT] Loaded {len(df)} raw rows.")

    print("[GDELT] Running preprocessing funnel (Stages 1-5)...")
    df_filtered = run_preprocessing_funnel(df)
    print(f"[GDELT] {len(df_filtered)} rows survived the preprocessing funnel.")

    if not df_filtered.empty:
      print("[GDELT] Building proxy texts for Stage 6...")
      proxy_texts = build_proxy_texts(df_filtered)

      anchors = fetch_active_anchors(['manual', 'news_outcome'])
      sbert_filter = SbertFilter()

      print("[GDELT] Running Stage 6 (Batch Proxy SBERT)...")
      stage6_indices = run_proxy_sbert(
        proxy_texts, anchors, sbert_filter, threshold=0.28
      )
      print(f"[GDELT] {len(stage6_indices)} articles passed Stage 6.")

      print("[GDELT] Fetching article content for Stage 7 candidates...")
      stage7_candidates = []
      for idx in stage6_indices:
        row = df_filtered.iloc[idx]
        url = row["DocumentIdentifier"]
        title, snippet = fetch_article_content(url)
        if not title and not snippet:
          continue

        stage7_candidates.append(
          {
            "article_url": url,
            "source_name": str(row.get("SourceCommonName", "")),
            "article_date": str(row.get("DATE", "")),
            "article_title": title,
            "behavioral_extract": snippet,
            "full_text": f"{title}. {snippet}",
          }
        )

      print(
        f"[GDELT] Running Stage 7 (Final SBERT) on {len(stage7_candidates)} candidates..."
      )
      confirmed_articles = run_final_sbert(
        stage7_candidates, anchors, sbert_filter, threshold=0.35
      )
      print(f"[GDELT] {len(confirmed_articles)} articles passed final SBERT.")

      if confirmed_articles:
        print("[GDELT] Extracting search terms...")
        try:
          nlp = spacy.load("en_core_web_sm")
        except OSError as exc:
          raise RuntimeError(
            "The en_core_web_sm model must be installed in the runtime image."
          ) from exc

        for art in confirmed_articles:
          art["search_terms"] = extract_search_terms(art, nlp)

        print("[GDELT] Writing results to database...")
        write_to_db(confirmed_articles)
        print(f"[GDELT] Saved {len(confirmed_articles)} actionable stories to DB.")

    with get_connection() as conn, conn.cursor() as cur:
      cur.execute(
          "UPDATE pipeline_state SET state_value = jsonb_build_object('last_url', %s, 'last_polled_at', NOW()), updated_at = NOW() WHERE state_key = 'gdelt_poll'",
          (gkg_url,),
        )

  except Exception as e: 
    print(f"Error: {e}")


if __name__ == "__main__":
  main()
