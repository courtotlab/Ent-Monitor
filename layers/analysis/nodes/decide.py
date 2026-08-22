"""DECIDE node - deterministic classification gate.

No LLM. No human review. Every cluster resolves to a final label automatically.
Sets tool_degraded flag and handles LOW post DB writes.
"""

from __future__ import annotations

import logging

from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import write_cluster_to_db
from layers.analysis.utils.formatters import build_cluster_json

logger = logging.getLogger(__name__)


def decide_node(state: AgentState) -> dict:
  """DECIDE node - sets final classification flags in state.

  Every cluster auto-resolves. No deferred/pending states.
  The decide_router determines whether to proceed to REPORT or skip to pop_cluster.
  """
  cluster_id = state.get("cluster_id", "unknown")
  posts = state.get("posts", [])
  tool_errors = state.get("tool_errors", [])
  vf = state.get("verify_finding")
  label = state.get("label", "MODERATE")

  tool_degraded = bool(tool_errors) or (
    vf is not None and vf.get("citation_check_failed", False)
  )

  logger.info(
    "DECIDE: cluster=%s label=%s risk=%.3f low_confidence=%s",
    cluster_id,
    label,
    state.get("risk_score", 0.0),
    state.get("low_confidence", False),
  )

  current_results = list(state.get("cluster_results", []))

  if label == "LOW" and not state.get("low_confidence", False):
    try:
      minimal_cluster_json = build_cluster_json(
          state=state,
          abstract="No detailed report generated (LOW risk).",
      )
      write_cluster_to_db(minimal_cluster_json, centroid=state.get("centroid"))
    except Exception as exc:
      logger.warning("DECIDE: failed to write LOW posts/cluster to DB - %s", exc)
    
  # Append a minimal cluster_json so it appears in run_summary.json
  current_results.append({
      "cluster_id": cluster_id,
      "classification": {
          "label": label,
          "lifecycle": state.get("lifecycle", "Isolated incident"),
          "verification": state.get("verification", "PROVISIONAL"),
          "confidence": state.get("confidence", 1.0),
          "risk_score": state.get("risk_score", 0.0),
          "evidence_status": "skipped_low",
      }
  })

  return {
    "tool_degraded": tool_degraded,
    "cluster_results": current_results,
  }


