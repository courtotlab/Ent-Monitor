"""Semantic Scholar search tool — free, 1 req/s without key.

Uses the public Semantic Scholar Academic Graph API.
Good for cross-discipline papers and preprints not yet indexed in PubMed.
"""

from __future__ import annotations

import logging
import time

import requests

from layers.analysis.state import EvidenceItem
from layers.analysis.tools.retry import with_retry

logger = logging.getLogger(__name__)

_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_TIMEOUT = 15

@with_retry(max_attempts=4, backoff=3.0)
def semantic_scholar_search(
  query: str,
  max_results: int = 5,
) -> list[EvidenceItem]:
  """Search Semantic Scholar.  Returns list[EvidenceItem]."""
  time.sleep(2.0)  # Pacing to avoid 429 rate limit on free tier
  resp = requests.get(
    _BASE,
    params={
      "query": query,
      "limit": max_results,
      "fields": "title,abstract,url,externalIds,year,citationCount",
    },
    timeout=_TIMEOUT,
  )
  resp.raise_for_status()
  data = resp.json().get("data", [])

  items: list[EvidenceItem] = []
  for paper in data:
    ext_ids = paper.get("externalIds") or {}
    pmid = ext_ids.get("PubMed")
    doi = ext_ids.get("DOI")

    url = paper.get("url", "")
    if not url and doi:
      url = f"https://doi.org/{doi}"

    items.append(
      EvidenceItem(
        source="semantic_scholar",
        title=paper.get("title", "Untitled"),
        url=url,
        pmid=pmid,
        snippet=(paper.get("abstract") or "")[:800],
        is_relevant=False,
        contradicts_harm=False,
      )
    )
  return items
