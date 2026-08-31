"""DECIDE node - deterministic classification gate. Handles final labels and LOW DB writes."""

from __future__ import annotations

import logging

from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import write_cluster_to_db, write_safe_posts_to_db, get_recent_post_count

logger = logging.getLogger(__name__)


def decide_node(state: AgentState) -> dict:
  """DECIDE node - sets final classification flags in state."""
  cluster_id = state.get("cluster_id", "unknown")
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
    eff_state = dict(state)
    eff_state["abstract"] = "No detailed report generated (LOW risk)."
    
    lifecycle = state.get("lifecycle", "Isolated incident")
    out_of_scope = state.get("out_of_scope", False)
    
    if out_of_scope or lifecycle == "Isolated incident":
      logger.info(
        "DECIDE: Skipping DB write for LOW trend '%s' (out_of_scope=%s, lifecycle=%s)",
        cluster_id, out_of_scope, lifecycle
      )
      try:
        write_safe_posts_to_db(eff_state.get("posts", []))
      except Exception as exc:
        logger.warning("DECIDE: failed to mark skipped LOW posts as SAFE - %s", exc)
    else:
      try:
        write_cluster_to_db(eff_state, centroid=eff_state.get("centroid"))
      except Exception as exc:
        logger.warning("DECIDE: failed to write LOW posts/cluster to DB - %s", exc)
    
    current_results.append(eff_state)

  # Calculate true post count including historical DB state
  post_count = len(state.get("posts", []))
  if state.get("matched_trend_id") is not None:
    post_count += state.get("db_trend_post_count", 0)
    
  recent_post_count = len(state.get("posts", []))
  if state.get("matched_trend_id") is not None:
    recent_post_count += get_recent_post_count(state.get("matched_trend_id"), days=7)
    
  lifecycle = state.get("lifecycle", "Isolated incident")

  # Smart Velocity Monitor Scheduling Rule
  should_monitor = (
    label == "HIGH" or
    (label == "MODERATE" and (lifecycle in ("Emergence", "Growth", "Resurfacing") or recent_post_count >= 7)) or
    (label == "LOW" and lifecycle in ("Emergence", "Growth") and post_count > 50)
  )

  return {
    "tool_degraded": tool_degraded,
    "cluster_results": current_results,
    "should_monitor": should_monitor,
  }


