"""Routing logic for the Layer 3 Analysis graph.

Contains:
- route_after_assess()       - ASSESS → CLASSIFY or RESEARCH
- route_after_verify()       - VERIFY → DECIDE, RESEARCH, or CLASSIFY
- route_after_decide()       - DECIDE → REPORT or pop_cluster
"""

from __future__ import annotations

from langgraph.types import Command

from layers.analysis.core.state import AgentState, EvidenceGap

from layers.analysis.nodes.assess import EVIDENCE_THRESHOLD, build_evidence_gap


#  Route: after ASSESS
def route_after_assess(state: AgentState) -> Command:
  """ASSESS routes to CLASSIFY (sufficient) or RESEARCH (gap)."""
  score = state.get("evidence_score", 0.0)  # computed by assess_node
  retries_left = state["research_retries_left"]

  if score >= EVIDENCE_THRESHOLD or retries_left <= 0:
    return Command(goto="classify")

  gap = build_evidence_gap(state, score)
  return Command(
    goto="research",
    update={
      "evidence_gap": gap,
      "research_retries_left": retries_left - 1,
    },
  )


#  Route: after VERIFY
def route_after_verify(state: AgentState) -> Command:
  """VERIFY routes to DECIDE, RESEARCH, or CLASSIFY."""
  finding = state.get("verify_finding") or {}
  retries_left = state.get("verify_retries_left", 0) > 0

  # A citation that couldn't be checked (tool failure) is NOT a confirmed-bad
  # PMID - must not trigger failure routing or consume verify_retries_left.
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
    # Retries exhausted and citation is still invalid/irrelevant - do NOT
    # silently confirm. Flag low_confidence so DECIDE/REPORT surface this
    # distinctly instead of writing it as a clean CONFIRMED trend.
    return Command(goto="decide", update={"low_confidence": True})

  if not finding.get("label_consistent"):
    if retries_left:
      return Command(
        goto="classify",
        update={
          "verify_retries_left": state.get("verify_retries_left", 1) - 1,
        },
      )
    # Same failure mode: exhausted retries with an unresolved inconsistency.
    return Command(goto="decide", update={"low_confidence": True})

  return Command(goto="decide")


#  Route: after DECIDE
def route_after_decide(state: AgentState) -> Command:
  """LOW + not low_confidence → skip report. Everything else → report."""
  if state.get("label", "MODERATE") == "LOW" and not state.get("low_confidence", False):
    return Command(goto="pop_cluster")
  return Command(goto="report")
