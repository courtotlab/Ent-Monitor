"""DECIDE node - deterministic classification gate.

No LLM. No human review. Every cluster resolves to a final label automatically.
Sets tool_degraded flag and handles LOW post DB writes.
"""

from __future__ import annotations

import logging

from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import write_cluster_to_db, write_safe_posts_to_db
from layers.shared.paths import get_run_dir
from layers.shared.posts import get_engagement

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
    _log_skipped_low(state)
    try:
      write_safe_posts_to_db(posts)
      minimal_cluster_json = {
        "run_id": state.get("run_id"),
        "cluster_id": cluster_id,
        "trend": {
          "trend_name": state.get("search_context") or cluster_id,
          "is_known_trend": state.get("is_known_trend", False),
          "matched_trend_id": state.get("matched_trend_id"),
          "post_count": len(posts),
          "platforms": list(set(p.get("platform", "unknown") for p in posts)),
        },
        "classification": {
          "label": label,
          "lifecycle": state.get("lifecycle", "Isolated incident"),
          "verification": state.get("verification", "PROVISIONAL"),
          "risk_score": state.get("risk_score", 0.0),
        },
        "posts": posts,
        "search_context": state.get("search_context", ""),
        "reasoning": {
          "why_this_label": state.get("reasoning", ""),
        },
        "evidence": [
          {
            "source": e["source"],
            "pmid": e.get("pmid"),
            "title": e["title"],
            "url": e["url"],
            "relevance_note": e.get("snippet", "")[:150],
            "is_relevant": e.get("is_relevant", False),
            "contradicts_harm": e.get("contradicts_harm", False),
          }
          for e in state.get("evidence", [])
        ],
      }
      write_cluster_to_db(minimal_cluster_json, centroid=state.get("centroid"))
      
      # Also save as a standalone JSON file for manual review
      import json

      from layers.shared.paths import get_run_dir
      output_dir = get_run_dir(state.get("run_id"), "final")
      output_dir.mkdir(parents=True, exist_ok=True)
      output_path = output_dir / f"{cluster_id}_low.json"
      
      with open(output_path, "w", encoding="utf-8") as f:
        json.dump(minimal_cluster_json, f, indent=2, ensure_ascii=False)
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
        },
        "flags": {
            "low_confidence": False,
        }
    })

  return {
    "tool_degraded": tool_degraded,
    "cluster_results": current_results,
  }

def _log_skipped_low(state: AgentState) -> None:
  """Append skipped LOW clusters to an auditable JSON file."""
  import json
  run_id = state.get("run_id", "unknown_run")
  output_dir = get_run_dir(run_id, "final")
  output_dir.mkdir(parents=True, exist_ok=True)
  skipped_file = output_dir / "skipped_low.json"

  entry = {
    "cluster_id": state.get("cluster_id", "unknown"),
    "trend_name": state.get("search_context", "Unknown trend"),
    "post_count": len(state.get("posts", [])),
    "risk_score": state.get("risk_score", 0.0),
    "evidence_score": state.get("evidence_score", 0.0),
    "low_confidence": state.get("low_confidence", False),
    "posts": [
      {
        "post_id": p.get("post_id", ""),
        "platform": p.get("platform", ""),
        "caption_text": (p.get("caption_text") or "")[:200],
        "sbert_score": p.get("sbert_score", 0.0),
        "likes": get_engagement(p, "likes"),
        "views": get_engagement(p, "views"),
      }
      for p in state.get("posts", [])
    ],
  }

  skipped = []
  if skipped_file.exists():
    try:
      with open(skipped_file, "r", encoding="utf-8") as f:
        skipped = json.load(f)
    except Exception:
      pass

  skipped.append(entry)

  with open(skipped_file, "w", encoding="utf-8") as f:
    json.dump(skipped, f, indent=2, ensure_ascii=False)
