"""Layer 3 Analysis - LangGraph StateGraph wiring + sequential orchestration.

This is the entry point for running the analysis pipeline.  The outer loop
processes clusters sequentially to prevent DECIDE merge-check race conditions.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from layers.analysis.core.routing import (
  route_after_assess,
  route_after_classify,
  route_after_decide,
  route_after_verify,
)
from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import (
  complete_agent_run,
  create_agent_run,
  merge_posts_into_trend,
)
from layers.analysis.nodes.assess import assess_node
from layers.analysis.nodes.classify import classify_node
from layers.analysis.nodes.decide import decide_node
from layers.analysis.nodes.observe import observe_node
from layers.analysis.nodes.report import report_node
from layers.analysis.nodes.research import research_node
from layers.analysis.nodes.verify import verify_node
from layers.analysis.tools.duckduckgo import set_circuit_breaker
from layers.analysis.tools.retry import DuckDuckGoCircuitBreaker
from layers.analysis.tools.semantic_scholar import reset_circuit_breaker as reset_ss_circuit_breaker
from layers.analysis.utils.formatters import build_cluster_json
from layers.shared.paths import get_run_dir

load_dotenv()
logger = logging.getLogger(__name__)



def run_analysis(posts: list[dict], run_id: str | None = None) -> dict:
  """Run the full Layer 3 analysis pipeline.

  1. Calls OBSERVE once on all posts to produce a queue of clusters.
  2. The graph uses a pop_cluster loop to process clusters sequentially
     (RESEARCH → ASSESS → CLASSIFY → VERIFY → REPORT → DECIDE).
  3. Known trends take a fast-path merge (skip LLM pipeline).
  """
  if not run_id:
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

  # Fresh circuit breaker per run
  circuit_breaker = DuckDuckGoCircuitBreaker()
  set_circuit_breaker(circuit_breaker)
  reset_ss_circuit_breaker()

  # Record the agent run in the database
  create_agent_run(run_id, len(posts))

  # Initialize state with raw posts for OBSERVE to consume
  initial_state = {
    "run_id": run_id,
    "clusters_queue": [],
    "cluster_results": [],
    "cluster_id": "observe_batch",
    "posts": posts,
    "trend_name": "",
    "search_context": "",
    "is_known_trend": False,
    "matched_trend_id": None,
    "triage_flag": "unclear",
    # Known-trend context (populated by OBSERVE for matched clusters)
    "db_trend_label": None,
    "db_trend_risk_score": None,
    "db_trend_post_count": None,
    "db_trend_lifecycle": None,
    "db_trend_last_seen": None,
    # Research accumulators
    "search_queries": [],
    "evidence": [],
    "evidence_gap": None,
    "evidence_score": 0.0,
    "tool_errors": [],
    "harm_hypothesis": "",
    "label": None,
    "confidence": 0.0,
    "citations": [],
    "citations_used_as_support": [],
    "supporting_evidence_ids": [],
    "risk_score": 0.0,
    "reasoning": "",
    "needs_more_evidence": False,
    "no_evidence_found": False,
    "verify_finding": None,
    "report": None,
    "tool_degraded": False,
    "low_confidence": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
  }

  logger.info("Invoking Unified Graph for %d posts...", len(posts))
  app = build_graph()

  error_message = None
  status = "completed"
  try:
    final_state = app.invoke(initial_state)
  except Exception as exc:
    logger.error("Graph invocation failed: %s", exc)
    error_message = str(exc)
    status = "failed"
    complete_agent_run(run_id, [], status=status, error_message=error_message)
    raise

  cluster_results = final_state.get("cluster_results", [])

  # Finalise the agent run in the database
  complete_agent_run(run_id, cluster_results, status=status)

  #  Write run summary (local file - kept as-is)
  _write_run_summary(run_id, cluster_results)

  return {"run_id": run_id, "clusters": cluster_results}


def merge_known_node(state: AgentState) -> dict:
  """Fast-path: merge new posts into an existing trend without LLM calls.

  Skips RESEARCH → ASSESS → CLASSIFY → VERIFY → REPORT entirely.
  Calls merge_posts_into_trend() which handles:
  - Post count increment + platform merge
  - Weighted centroid merge
  - Resurfacing detection (>14 day gap)
  - Burst-triggered velocity scheduling
  - Lifecycle event logging
  """
  cluster_id = state.get("cluster_id", "unknown")
  trend_id = state.get("matched_trend_id")
  posts = state.get("posts", [])
  centroid = state.get("centroid")

  print(f"  [MERGE] Fast-path: merging {len(posts)} posts into existing trend {trend_id}")

  result = merge_posts_into_trend(trend_id, posts, new_centroid=centroid)

  if result is None:
    logger.warning("MERGE: fast-path failed for trend %s - will appear as skipped", trend_id)
    return {"cluster_results": list(state.get("cluster_results", []))}

  # Build a minimal cluster_result entry so the dashboard sees the merge
  cluster_json = build_cluster_json(
      state=state,
      abstract=f"Merged {len(posts)} new posts into existing trend '{trend_id}'",
      is_fast_path=True,
      overrides={
          "label": result.get("label", "MODERATE"),
          "risk_score": result.get("risk_score", 0.5),
          "verification": result.get("verification_status", "CONFIRMED"),
          "lifecycle": result.get("lifecycle_status", "Resurfacing"),
      }
  )

  current_results = list(state.get("cluster_results", []))
  current_results.append(cluster_json)

  logger.info("MERGE: fast-path completed for trend %s - %d posts merged", trend_id, len(posts))
  return {"cluster_results": current_results}


def pop_cluster_node(state: AgentState) -> dict:
  """Pops the next cluster from the queue and resets research state."""
  queue = state.get("clusters_queue", [])
  if not queue:
    logger.info("No more clusters in queue. Finishing run.")
    return {"cluster_id": "DONE"}
  
  cluster = queue[0]
  remaining = queue[1:]
  
  logger.info("Popped cluster: %s (%d posts)", cluster.get("cluster_id"), len(cluster.get("posts", [])))
  
  return {
    "clusters_queue": remaining,
    "cluster_id": cluster.get("cluster_id", "unknown"),
    "posts": cluster.get("posts", []),
    "trend_name": cluster.get("cluster_name", ""),
    "search_context": cluster.get("search_context", ""),
    "is_known_trend": cluster.get("is_known_trend", False),
    "matched_trend_id": cluster.get("matched_trend_id"),
    "centroid": cluster.get("centroid", []),
    "triage_flag": cluster.get("triage_flag", "unclear"),
    
    # Known-trend context from DB match
    "db_trend_label": cluster.get("db_trend_label"),
    "db_trend_risk_score": cluster.get("db_trend_risk_score"),
    "db_trend_post_count": cluster.get("db_trend_post_count"),
    "db_trend_lifecycle": cluster.get("db_trend_lifecycle"),
    "db_trend_last_seen": cluster.get("db_trend_last_seen"),
    
    # Reset accumulators for the new cluster
    "search_queries": [],
    "evidence": [],
    "evidence_gap": None,
    "evidence_score": 0.0,
    "tool_errors": [],
    "harm_hypothesis": "",
    "label": None,
    "confidence": 0.0,
    "citations": [],
    "citations_used_as_support": [],
    "supporting_evidence_ids": [],
    "risk_score": 0.0,
    "reasoning": "",
    "needs_more_evidence": False,
    "no_evidence_found": False,
    "mechanism_level_match": False,
    "slang_terms": [],
    "lifecycle": None,
    "verification": None,
    "verify_finding": None,
    "report": None,
    "tool_degraded": False,
    "low_confidence": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
  }

def route_after_pop(state: AgentState) -> Command:
  """If there's an active cluster, decide: fast-path merge or full pipeline."""
  if state.get("cluster_id") == "DONE":
    return Command(goto=END)
  
  is_known = state.get("is_known_trend", False)
  matched_id = state.get("matched_trend_id")
  triage_flag = state.get("triage_flag", "unclear")
  db_label = state.get("db_trend_label")

  # Fast-path merge IF known trend AND triage doesn't contradict DB label
  # Override: if triage says likely_harmful but DB says Low, force full pipeline
  if is_known and matched_id:
    contradicts = (
      triage_flag == "likely_harmful" and (db_label and db_label.upper() == "LOW")
    )
    if not contradicts:
      return Command(goto="merge_known")
    else:
      logger.info(
        "ROUTE: known trend %s but triage=%s contradicts DB label=%s - forcing full pipeline",
        matched_id, triage_flag, db_label,
      )

  return Command(goto="research")

def build_graph() -> StateGraph:
  """Build the full pipeline graph (Observe -> Loop(Research...Decide))."""
  graph = StateGraph(AgentState)

  #  Nodes
  graph.add_node("observe", observe_node)
  graph.add_node("pop_cluster", pop_cluster_node)
  graph.add_node("merge_known", merge_known_node)  # fast-path for known trends
  graph.add_node("research", research_node)
  graph.add_node("assess", assess_node)  # deterministic formula - no LLM
  graph.add_node("classify", classify_node)  # single-shot Terra high-effort
  graph.add_node("verify", verify_node)
  graph.add_node("report", report_node)  # short summary, GPT-4.1-mini
  graph.add_node("decide", decide_node)  # DB writes + JSON output, no LLM

  #  Router nodes (Command-based routing)
  graph.add_node("pop_router", route_after_pop)
  graph.add_node("assess_router", route_after_assess)
  graph.add_node("classify_router", route_after_classify)
  graph.add_node("verify_router", route_after_verify)
  graph.add_node("decide_router", route_after_decide)

  #  Edges
  graph.set_entry_point("observe")
  graph.add_edge("observe", "pop_cluster")
  graph.add_edge("pop_cluster", "pop_router")
  
  # Fast-path: merge_known → back to pop_cluster
  graph.add_edge("merge_known", "pop_cluster")

  # Full agentic loop
  graph.add_edge("research", "assess")
  graph.add_edge("assess", "assess_router")
  graph.add_edge("classify", "classify_router")
  graph.add_edge("verify", "verify_router")
  graph.add_edge("decide", "decide_router")
  graph.add_edge("report", "pop_cluster")

  return graph.compile()


def _write_run_summary(run_id: str, cluster_results: list[dict]) -> None:
  """Write the run_summary.json file."""
  output_dir = get_run_dir(run_id, "final")
  output_dir.mkdir(parents=True, exist_ok=True)

  labels = {"HIGH": 0, "MODERATE": 0, "LOW": 0}
  for r in cluster_results:
    classification = r.get("classification", {})
    lbl = classification.get("label", "MODERATE")
    labels[lbl] = labels.get(lbl, 0) + 1

  summary = {
    "run_id": run_id,
    "completed_at": datetime.now(UTC).isoformat(),
    "total_clusters": len(cluster_results),
    "labels": labels,
    "clusters": [
      {
        "cluster_id": r.get("cluster_id", "unknown"),
        "label": r.get("classification", {}).get("label", "MODERATE"),
        "risk_score": r.get("classification", {}).get("risk_score", 0.0),
        "low_confidence": r.get("classification", {}).get("confidence", 1.0) < 0.75,
      }
      for r in cluster_results
    ],
  }

  summary_path = output_dir / "run_summary.json"
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

  logger.info("Run summary written to %s", summary_path)
