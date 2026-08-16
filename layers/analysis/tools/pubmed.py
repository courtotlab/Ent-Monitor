"""PubMed search tools - uses NCBI E-utilities (free, no key required for 3 req/s).

Two functions:
- pubmed_search(query)           - esearch + efetch; returns list[EvidenceItem]
- pubmed_fetch_by_pmid(pmid)     - efetch only; returns EvidenceItem | None
                                   Raises PMIDNotFoundError on confirmed absence.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from layers.analysis.core.state import EvidenceItem
from layers.analysis.tools.retry import PMIDNotFoundError, with_retry

logger = logging.getLogger(__name__)

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 15  # seconds


#  Internal: parse PubMed XML into EvidenceItems
def _parse_articles(xml_text: str) -> list[EvidenceItem]:
  """Parse efetch XML response into a list of EvidenceItem dicts."""
  items: list[EvidenceItem] = []
  try:
    root = ET.fromstring(xml_text)
  except ET.ParseError:
    logger.warning("[PUBMED] Failed to parse XML response")
    return items

  for article in root.findall(".//PubmedArticle"):
    pmid_el = article.find(".//PMID")
    title_el = article.find(".//ArticleTitle")

    pmid = pmid_el.text if pmid_el is not None else None
    title = title_el.text if title_el is not None else "Untitled"

    abstract_parts = []
    for el in article.findall(".//AbstractText"):
      text = "".join(el.itertext()).strip()
      if not text:
        continue
      label = el.get("Label")
      abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = " ".join(abstract_parts)

    items.append(
      EvidenceItem(
        source="pubmed",
        title=title or "Untitled",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        pmid=pmid,
        snippet=(abstract or "")[:800],
        is_relevant=False,  # tagged by RESEARCH LLM later
        contradicts_harm=False,
      )
    )
  return items


#  Public API
@with_retry()
def pubmed_search(query: str, max_results: int = 5) -> list[EvidenceItem]:
  """Search PubMed via esearch → efetch pipeline.  Returns list[EvidenceItem]."""
  # Step 1: esearch - get PMIDs
  search_resp = requests.get(
    f"{_BASE}/esearch.fcgi",
    params={
      "db": "pubmed",
      "term": query,
      "retmax": max_results,
      "retmode": "json",
      "sort": "relevance",
    },
    timeout=_TIMEOUT,
  )
  search_resp.raise_for_status()
  id_list = search_resp.json().get("esearchresult", {}).get("idlist", [])

  if not id_list:
    return []

  # Step 2: efetch - get abstracts
  fetch_resp = requests.get(
    f"{_BASE}/efetch.fcgi",
    params={
      "db": "pubmed",
      "id": ",".join(id_list),
      "retmode": "xml",
      "rettype": "abstract",
    },
    timeout=_TIMEOUT,
  )
  fetch_resp.raise_for_status()
  return _parse_articles(fetch_resp.text)


@with_retry(empty_return=lambda: None)
def pubmed_fetch_by_pmid(pmid: str) -> EvidenceItem | None:
  """Fetch a single PubMed article by PMID.

  Returns:
    EvidenceItem if found.
    None only on retry-exhausted tool failure (network/timeout).

  Raises:
    PMIDNotFoundError - if NCBI cleanly confirms the PMID doesn't exist.
    This is a domain signal, not a tool error, and propagates through @with_retry.
  """
  resp = requests.get(
    f"{_BASE}/efetch.fcgi",
    params={
      "db": "pubmed",
      "id": pmid,
      "retmode": "xml",
      "rettype": "abstract",
    },
    timeout=_TIMEOUT,
  )
  resp.raise_for_status()

  articles = _parse_articles(resp.text)
  if not articles:
    # NCBI responded cleanly but returned no article - confirmed not found.
    raise PMIDNotFoundError(f"PMID {pmid} does not exist in PubMed")

  return articles[0]
