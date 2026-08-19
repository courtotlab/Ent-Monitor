"""Semantic Scholar search tool - free, 1 req/s without key.

Uses the public Semantic Scholar Academic Graph API.
Good for cross-discipline papers and preprints not yet indexed in PubMed.
"""

from __future__ import annotations

import logging
import time

import requests

from layers.analysis.core.state import EvidenceItem
from layers.analysis.tools.retry import with_retry

logger = logging.getLogger(__name__)

_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_TIMEOUT = 15

_CIRCUIT_OPEN = False

def reset_circuit_breaker() -> None:
  global _CIRCUIT_OPEN
  _CIRCUIT_OPEN = False

@with_retry(max_attempts=4, backoff=3.0)
def semantic_scholar_search(
  query: str,
  max_results: int = 5,
) -> list[EvidenceItem]:
  """Search Semantic Scholar.  Returns list[EvidenceItem]."""
  global _CIRCUIT_OPEN
  if _CIRCUIT_OPEN:
    return []

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
  try:
    resp.raise_for_status()
  except requests.exceptions.HTTPError as e:
    if e.response.status_code in (429, 500, 502, 503, 504):
      logger.warning("[CIRCUIT] Semantic Scholar %s received, opening circuit breaker for remainder of run", e.response.status_code)
      _CIRCUIT_OPEN = True
      return []
    raise e
  except requests.exceptions.Timeout:
    logger.warning("[CIRCUIT] Semantic Scholar timeout, opening circuit breaker for remainder of run")
    _CIRCUIT_OPEN = True
    return []
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
        source_tier="clinical",
        title=paper.get("title", "Untitled"),
        url=url,
        pmid=pmid,
        snippet=(paper.get("abstract") or "")[:800],
        is_relevant=False,
        contradicts_harm=False,
        relevance_score=0,
      )
    )
  return items
