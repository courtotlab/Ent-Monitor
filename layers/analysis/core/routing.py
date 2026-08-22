"""Routing logic for the Layer 3 Analysis graph.

Contains:
- EVIDENCE_THRESHOLD constant
- compute_evidence_score()   - deterministic formula (ASSESS)
- build_evidence_gap()       - picks next query + tool when score is low
- route_after_assess()       - ASSESS → CLASSIFY or RESEARCH
- route_after_classify()     - CLASSIFY → VERIFY or RESEARCH
- route_after_verify()       - VERIFY → DECIDE, RESEARCH, or CLASSIFY
- route_after_decide()       - DECIDE → REPORT or pop_cluster
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.types import Command

from layers.analysis.core.state import EvidenceGap

if TYPE_CHECKING:
  from layers.analysis.core.state import AgentState

# Deliberately modest - don't demand 3 perfect papers before proceeding.
EVIDENCE_THRESHOLD = 0.45


#  Deterministic evidence-quality formula (ASSESS)
def compute_evidence_score(state: AgentState) -> float:
  """Pure formula - no LLM.  Returns 0.0-1.0."""
  evidence = state["evidence"]
  if not evidence:
    return 0.0

  pubmed_count = sum(1 for e in evidence if e["source"] == "pubmed")
  other_count = sum(1 for e in evidence if e["source"] != "pubmed")
  source_score = min(pubmed_count * 0.4 + other_count * 0.15, 1.0)

  # Use the new 1-10 relevance_score to calculate a much more accurate ratio!
  total_relevance = sum(e.get("relevance_score", 0) for e in evidence if e.get("is_relevant", False))
  max_possible = len(evidence) * 10
  relevance_ratio = min(total_relevance / max_possible, 1.0)

  contradictory = sum(1 for e in evidence if e.get("contradicts_harm", False))
  contradiction_penalty = min(contradictory * 0.15, 0.4)

  raw = (0.55 * source_score) + (0.45 * relevance_ratio) - contradiction_penalty
  return max(0.0, min(raw, 1.0))


#  Build the next evidence gap struct (ASSESS)
def build_evidence_gap(state: AgentState, score: float) -> EvidenceGap:
  """Decide what's missing and suggest a query + tool for RESEARCH.

  Uses harm_hypothesis (if available) instead of raw search_context to keep
  retry queries in clinical/mechanism terminology rather than reverting to the
  trend's colloquial vocabulary.
  """
  evidence = state["evidence"]
  pubmed_count = sum(1 for e in evidence if e["source"] == "pubmed")

  # Prefer harm_hypothesis for retry queries; fall back to search_context
  hypothesis = state.get("harm_hypothesis", "") or ""
  base_query = hypothesis if hypothesis and hypothesis != "none - benign content" else state["search_context"]

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


#  Route: after ASSESS
def route_after_assess(state: AgentState) -> Command:
  """Edge (1) - ASSESS routes to CLASSIFY (sufficient) or RESEARCH (gap)."""
  score = compute_evidence_score(state)
  retries_left = state["research_retries_left"]

  if score >= EVIDENCE_THRESHOLD or retries_left <= 0:
    no_evidence = score == 0.0 and retries_left <= 0
    return Command(
      goto="classify",
      update={
        "evidence_score": score,
        "no_evidence_found": no_evidence,
      },
    )

  gap = build_evidence_gap(state, score)
  return Command(
    goto="research",
    update={
      "evidence_score": score,
      "evidence_gap": gap,
      "research_retries_left": retries_left - 1,
    },
  )


#  Route: after CLASSIFY
def route_after_classify(state: AgentState) -> Command:
  """Edge (2) - CLASSIFY routes to VERIFY or back to RESEARCH."""
  if state.get("needs_more_evidence") and state["research_retries_left"] > 0:
    return Command(
      goto="research",
      update={
        "research_retries_left": state["research_retries_left"] - 1,
        "needs_more_evidence": False,
      },
    )
  return Command(goto="verify")


#  Route: after VERIFY
def route_after_verify(state: AgentState) -> Command:
  """Edges (3) (4) - VERIFY routes to DECIDE, RESEARCH, or CLASSIFY."""
  finding = state.get("verify_finding") or {}
  retries_left = state.get("verify_retries_left", 0) > 0

  # A citation that couldn't be checked (tool failure) is NOT a confirmed-bad
  # PMID - must not trigger edge (3) or consume verify_retries_left.
  if finding.get("citation_check_failed"):
    return Command(goto="decide")

  if finding.get("citation_valid") is False or not finding.get("citation_relevant"):
    if retries_left:
      return Command(
        goto="research",
        update={
          "evidence_gap": EvidenceGap(
            missing=finding.get("notes", "Citation invalid or irrelevant."),
            suggested_query=f"{state.get('harm_hypothesis', state.get('search_context', ''))} alternative citation",
            suggested_tool="pubmed_search",
            reason="bad_citation",
          ),
          "verify_retries_left": state.get("verify_retries_left", 1) - 1,
        },
      )
    return Command(goto="decide")

  if not finding.get("label_consistent") and retries_left:
    return Command(
      goto="classify",
      update={
        "verify_retries_left": state.get("verify_retries_left", 1) - 1,
      },
    )

  return Command(goto="decide")


#  Route: after DECIDE
def route_after_decide(state: AgentState) -> Command:
  """Deterministic severity-based routing.

  LOW + not low_confidence → skip report (cost saving).
  Everything else → report.
  low_confidence tier-up: treated as one severity tier higher for routing.
  """
  label = state.get("label", "MODERATE")
  low_confidence = state.get("low_confidence", False)

  # LOW with no confidence issues → skip report entirely
  if label == "LOW" and not low_confidence:
    return Command(goto="pop_cluster")

  return Command(goto="report")
