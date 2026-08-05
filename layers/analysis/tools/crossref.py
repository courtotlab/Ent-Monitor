"""CrossRef search tool — free, uses the 'polite pool' (email in User-Agent).

Good for finding full DOI metadata for papers discovered via DuckDuckGo.
"""

from __future__ import annotations

import logging
import re

import requests

from layers.analysis.state import EvidenceItem
from layers.analysis.tools.retry import with_retry

logger = logging.getLogger(__name__)

_BASE = "https://api.crossref.org/works"
_TIMEOUT = 15
_USER_AGENT = "ENT-Monitor/1.0 (mailto:ent-monitor@example.com)"


@with_retry()
def crossref_search(
  query: str,
  max_results: int = 3,
) -> list[EvidenceItem]:
  """Search CrossRef.  Returns list[EvidenceItem]."""
  resp = requests.get(
    _BASE,
    params={
      "query": query,
      "rows": max_results,
      "select": "DOI,title,abstract,container-title,author",
    },
    headers={"User-Agent": _USER_AGENT},
    timeout=_TIMEOUT,
  )
  resp.raise_for_status()
  items_raw = resp.json().get("message", {}).get("items", [])

  items: list[EvidenceItem] = []
  for item in items_raw:
    titles = item.get("title", [])
    title = titles[0] if titles else "Untitled"
    doi = item.get("DOI", "")
    abstract = item.get("abstract", "")

    # CrossRef abstracts sometimes contain JATS XML tags — strip naively.
    if abstract:
      abstract = re.sub(r"<[^>]+>", "", abstract)

    items.append(
      EvidenceItem(
        source="crossref",
        title=title,
        url=f"https://doi.org/{doi}" if doi else "",
        pmid=None,
        snippet=abstract[:1200],
        is_relevant=False,
        contradicts_harm=False,
      )
    )
  return items
