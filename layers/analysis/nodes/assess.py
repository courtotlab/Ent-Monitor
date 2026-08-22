"""ASSESS node - deterministic evidence quality scorer.

No LLM. Computes an evidence score based on source quality and relevance,
and determines what is missing (the "evidence gap") if the score is too low.
"""

from __future__ import annotations

import logging

from layers.analysis.core.state import AgentState, EvidenceGap

logger = logging.getLogger(__name__)

# Deliberately modest - don't demand 3 perfect papers before proceeding.
EVIDENCE_THRESHOLD = 0.45


def compute_evidence_score(state: AgentState) -> float:
  """Pure formula - no LLM. Returns a score from 0.0 to 1.0 based on evidence quality."""
  evidence = state.get("evidence", [])
  if not evidence:
    return 0.0

  pubmed_count = sum(1 for e in evidence if e["source"] == "pubmed")
  other_count = sum(1 for e in evidence if e["source"] != "pubmed")
  source_score = min(pubmed_count * 0.4 + other_count * 0.15, 1.0)

  # Use the 1-10 relevance_score to calculate a much more accurate ratio
  total_relevance = sum(e.get("relevance_score", 0) for e in evidence if e.get("is_relevant", False))
  max_possible = len(evidence) * 10
  relevance_ratio = min(total_relevance / max_possible, 1.0)

  contradictory = sum(1 for e in evidence if e.get("contradicts_harm", False))
  contradiction_penalty = min(contradictory * 0.15, 0.4)

  raw = (0.55 * source_score) + (0.45 * relevance_ratio) - contradiction_penalty
  return max(0.0, min(raw, 1.0))


def build_evidence_gap(state: AgentState, score: float) -> EvidenceGap:
  """Decide what's missing and suggest a query + tool for RESEARCH.

  Uses harm_hypothesis (if available) instead of raw search_context to keep
  retry queries in clinical/mechanism terminology rather than reverting to the
  trend's colloquial vocabulary.
  """
  evidence = state.get("evidence", [])
  pubmed_count = sum(1 for e in evidence if e["source"] == "pubmed")

  # Prefer harm_hypothesis for retry queries; fall back to search_context
  hypothesis = state.get("harm_hypothesis", "") or ""
  base_query = hypothesis if hypothesis and hypothesis != "none - benign content" else state.get("search_context", "")

  if pubmed_count == 0:
    return EvidenceGap(
      missing="No peer-reviewed literature found yet",
      suggested_query=f"{base_query} pediatric case report",
      suggested_tool="pubmed_search",
      reason="zero_pubmed_results",
    )

  relevant = sum(1 for e in evidence if e.get("is_relevant", False))
  if relevant == 0:
    return EvidenceGap(
      missing="Found literature but none directly addresses this specific behavior",
      suggested_query=f"{base_query} adverse event OR complications",
      suggested_tool="semantic_scholar_search",
      reason="low_relevance",
    )

  return EvidenceGap(
    missing="Insufficient evidence depth - trying news/social context",
    suggested_query=f"{base_query} danger warning pediatric",
    suggested_tool="duckduckgo_search",
    reason="thin_evidence",
  )


def assess_node(state: AgentState) -> dict:
  """Compute evidence score and write it to state.

  The actual routing decision is made by route_after_assess() which is
  wired as a separate router node in graph.py.
  """
  score = compute_evidence_score(state)
  print(f"  [ASSESS] Evidence quality score: {score:.2f}/1.00")
  logger.info(
    "ASSESS: evidence_score=%.3f (threshold=%.2f, retries_left=%d)",
    score,
    EVIDENCE_THRESHOLD,
    state.get("research_retries_left", 0),
  )
  return {"evidence_score": score}
