"""DECIDE node — classification gate only.

No LLM. Determines the final label/flags and updates state.
Writing the full JSON output is now REPORT's responsibility so that only
dashboard-worthy clusters (HARMFUL / CONCERNING / high-risk) get a file.
"""

from __future__ import annotations

import logging

from layers.analysis.state import AgentState

logger = logging.getLogger(__name__)


def decide_node(state: AgentState) -> dict:
  """DECIDE node — sets final classification flags in state.

  Does NOT write any files.  The decide_router will decide whether to proceed
  to REPORT (which writes the file + appends to cluster_results) or skip
  straight back to pop_cluster.
  """
  cluster_id = state.get("cluster_id", "unknown")
  posts = state.get("posts", [])
  tool_errors = state.get("tool_errors", [])
  vf = state.get("verify_finding")

  no_evidence = state.get("no_evidence_found", False)
  label = state.get("label", "CONCERNING")
  confidence = state.get("confidence", 0.0)
  downgraded = state.get("downgrade_reason") is not None and "HARMFUL" in (
    state.get("downgrade_reason") or ""
  )

  verify_passed = (
    vf is not None
    and vf.get("citation_valid", True) is not False
    and vf.get("citation_relevant", True)
  )

  needs_human_review = (
    label in ("HARMFUL", "CONCERNING")
    or downgraded
    or (no_evidence and label == "SAFE" and confidence < 0.7)
    or not verify_passed
  )

  tool_degraded = bool(tool_errors) or (
    vf is not None and vf.get("citation_check_failed", False)
  )

  logger.info(
    "DECIDE: cluster=%s label=%s risk=%.3f needs_review=%s",
    cluster_id,
    state.get("label"),
    state.get("risk_score", 0.0),
    needs_human_review,
  )

  # Push computed flags back into state so REPORT and the router can read them
  return {
    "needs_human_review": needs_human_review,
    "tool_degraded": tool_degraded,
  }
