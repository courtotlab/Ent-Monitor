from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from layers.analysis.core.state import AgentState
from layers.shared.posts import get_engagement


def build_cluster_json(
  state: AgentState,
  abstract: str = "",
  harm_mechanism: str = "",
  rising_non_trend: bool = False,
  is_fast_path: bool = False,
  overrides: dict[str, Any] | None = None,
) -> dict:
  """Build a standard, schema-compliant cluster JSON dictionary.

  Used universally across the pipeline (report.py, decide.py, graph.py) to
  ensure identical output structure and avoid DRY violations.
  """
  cluster_id = state.get("cluster_id", "unknown")
  run_id = state.get("run_id", "unknown_run")
  posts = state.get("posts", [])
  platforms = list(set(p.get("platform", "unknown") for p in posts))

  # Apply overrides (useful for fast-path merge which pulls from DB instead of state)
  eff_state = dict(state)
  if overrides:
    eff_state.update(overrides)

  vf = eff_state.get("verify_finding")
  verify_passed = bool(vf and vf.get("citation_valid") and vf.get("citation_relevant") and vf.get("label_consistent"))
  evidence_status = "verified" if verify_passed else "unverified"
  
  if is_fast_path:
    evidence_status = "skipped_fast_path"
    verify_passed = True
  elif eff_state.get("label") == "LOW":
    evidence_status = "skipped_low"
    verify_passed = True

  # Format evidence array
  evidence_list = []
  for e in eff_state.get("evidence", []):
    evidence_list.append({
      "source": e.get("source"),
      "pmid": e.get("pmid"),
      "title": e.get("title"),
      "url": e.get("url"),
      "is_relevant": e.get("is_relevant", False),
      "contradicts_harm": e.get("contradicts_harm", False),
    })
    
  reasoning_text = eff_state.get("reasoning", "")
  if is_fast_path:
    reasoning_text = f"Fast-path merge into existing trend (DB label: {eff_state.get('label')})"

  return {
    "run_id": run_id,
    "cluster_id": cluster_id,
    "processed_at": datetime.now(UTC).isoformat(),
    "classification": {
      "label": eff_state.get("label", "MODERATE"),
      "lifecycle": eff_state.get("lifecycle", "Isolated incident"),
      "verification": eff_state.get("verification", "PROVISIONAL"),
      "confidence": eff_state.get("confidence", 1.0),
      "risk_score": eff_state.get("risk_score", 0.0),
      "evidence_status": evidence_status,
      "no_evidence_found": eff_state.get("no_evidence_found", False),
      "verify_passed": verify_passed,
      "verify_failure_reason": vf.get("notes", "") if (vf and not verify_passed) else "",
      "slang_terms": eff_state.get("slang_terms", []),
      "mechanism_level_match": eff_state.get("mechanism_level_match", False),
    },
    "trend": {
      "trend_name": eff_state.get("trend_name") or cluster_id,
      "is_known_trend": eff_state.get("is_known_trend", False),
      "matched_trend_id": eff_state.get("matched_trend_id"),
      "post_count": len(posts),
      "platforms": platforms,
    },
    "posts": [
      {
        "post_id": p.get("post_id", ""),
        "platform": p.get("platform", ""),
        "caption_text": (p.get("caption_text") or "")[:200],
        "sbert_score": p.get("sbert_score", 0.0),
        "likes": get_engagement(p, "likes"),
        "views": get_engagement(p, "views"),
      }
      for p in posts
    ],
    "evidence": evidence_list,
    "reasoning": {
      "why_this_label": reasoning_text,
    },
    "abstract": abstract,
    "search_context": eff_state.get("search_context", ""),
    "harm_mechanism": harm_mechanism,
    "rising_non_trend": rising_non_trend,
  }
