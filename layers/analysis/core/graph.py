"""Layer 3 Analysis - LangGraph StateGraph wiring + sequential orchestration.

This is the entry point for running the analysis pipeline.  The outer loop
processes clusters sequentially to prevent DECIDE merge-check race conditions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from layers.analysis.core.routing import (
  route_after_assess,
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
from layers.analysis.nodes.probe import probe_known
from layers.analysis.nodes.report import report_node
from layers.analysis.nodes.research import research_node
from layers.analysis.nodes.verify import verify_node
from layers.analysis.tools.duckduckgo import set_circuit_breaker
from layers.analysis.tools.retry import DuckDuckGoCircuitBreaker
from layers.analysis.tools.semantic_scholar import reset_circuit_breaker as reset_ss_circuit_breaker


load_dotenv()
logger = logging.getLogger(__name__)



def run_analysis(posts: list[dict], run_id: str | None = None) -> dict:
  """Run the full Layer 3 analysis pipeline.

  1. Calls OBSERVE once on all posts to produce a queue of clusters.
  2. The graph uses a pop_cluster loop to process clusters sequentially
     (RESEARCH → ASSESS → CLASSIFY → VERIFY → DECIDE → [REPORT]).
     REPORT runs after DECIDE so the verdict is persisted first; low-risk,
     non-flagged clusters skip it entirely (see route_after_decide).
  3. Known trends take a gated fast path: triage contradiction, resurfacing
     (>14d activity gap), or stale verdict (>30d since last classification)
     forces the full pipeline; otherwise an evidence-delta PROBE (new PubMed
     publications since last_verified_at) gates the LLM-free merge.
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
    "matched_trend_id": None,
    "triage_flag": "unclear",
    # Known-trend context (populated by OBSERVE for matched clusters)
    "db_trend_label": None,
    "db_trend_risk_score": None,
    "db_trend_post_count": None,
    "db_trend_lifecycle": None,
    "db_trend_last_seen": None,
    "db_trend_last_verified": None,
    # Research accumulators
    "search_queries": [],
    "evidence": [],
    "evidence_gap": None,
    "evidence_score": 0.0,
    "tool_errors": [],
    "harm_hypothesis": "",
    "label": None,
    "citations": [],
    "supporting_evidence_ids": [],
    "risk_score": 0.0,
    "reasoning": "",
    "out_of_scope": False,
    "verify_finding": None,
    "tool_degraded": False,
    "low_confidence": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
    "should_monitor": False,
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

  # Build a minimal state snapshot so the dashboard sees the merge
  eff_state = dict(state)
  eff_state["abstract"] = f"Merged {len(posts)} new posts into existing trend '{trend_id}'"
  eff_state["label"] = result.get("label", "MODERATE")
  eff_state["risk_score"] = result.get("risk_score", 0.5)
  eff_state["verification"] = result.get("verification_status", "CONFIRMED")
  eff_state["lifecycle"] = result.get("lifecycle_status", "Resurfacing")

  current_results = list(state.get("cluster_results", []))
  current_results.append(eff_state)

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
    "centroid": cluster.get("centroid", []),
    "matched_trend_id": cluster.get("matched_trend_id"),
    "triage_flag": cluster.get("triage_flag", "unclear"),
    
    # Known-trend context from DB match
    "db_trend_label": cluster.get("db_trend_label"),
    "db_trend_risk_score": cluster.get("db_trend_risk_score"),
    "db_trend_post_count": cluster.get("db_trend_post_count"),
    "db_trend_lifecycle": cluster.get("db_trend_lifecycle"),
    "db_trend_last_seen": cluster.get("db_trend_last_seen"),
    "db_trend_last_verified": cluster.get("db_trend_last_verified"),
    
    # Reset accumulators for the new cluster
    "search_queries": [],
    "evidence": [],
    "evidence_gap": None,
    "evidence_score": 0.0,
    "tool_errors": [],
    "harm_hypothesis": "",
    "label": None,
    "citations": [],
    "supporting_evidence_ids": [],
    "risk_score": 0.0,
    "reasoning": "",
    "mechanism_level_match": False,
    "out_of_scope": False,
    "slang_terms": [],
    "lifecycle": None,
    "verification": None,
    "verify_finding": None,
    "tool_degraded": False,
    "low_confidence": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
    "should_monitor": False,
  }

#  Verdict-freshness gates for the known-trend fast path.
#  A stored verdict is only trusted for a silent merge while ALL of these hold:
#  triage agrees with the DB label, the trend isn't resurging, the classification
#  is recent, and no new literature has appeared since it was verified.
RESURFACE_GAP_DAYS = 14  # same gap _check_resurfacing (queries.py) uses to flip lifecycle to Resurfacing
VERDICT_TTL_DAYS = 30    # full-pipeline classifications older than this are re-run before merging


def _days_since(ts: str | datetime | None) -> float | None:
  """Age of a timestamp in days; tolerates ISO strings and naive datetimes."""
  if ts is None:
    return None
  if isinstance(ts, str):
    try:
      ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
      return None
  if ts.tzinfo is None:
    ts = ts.replace(tzinfo=UTC)
  return (datetime.now(UTC) - ts).total_seconds() / 86400.0


def route_after_pop(state: AgentState) -> Command:
  """If there's an active cluster, decide: probe-gated merge or full pipeline.

  Known trends merge only when their stored verdict is trustworthy:
    - triage must not contradict the DB label
    - the trend must not be resurging (> RESURFACE_GAP_DAYS activity gap)
    - the verdict must be fresh (< VERDICT_TTL_DAYS since last full classification)
  Survivors pass through the evidence-delta PROBE before MERGE.
  """
  if state.get("cluster_id") == "DONE":
    return Command(goto=END)

  matched_id = state.get("matched_trend_id")
  triage_flag = state.get("triage_flag", "unclear")
  db_label = state.get("db_trend_label")

  if matched_id is not None:
    contradicts = (
      triage_flag == "likely_harmful" and (db_label and db_label.upper() == "LOW")
    )
    seen_days = _days_since(state.get("db_trend_last_seen"))
    resurging = (
      seen_days is not None
      and seen_days > RESURFACE_GAP_DAYS
      and state.get("db_trend_lifecycle") != "Emergence"
    )
    verified_days = _days_since(state.get("db_trend_last_verified"))
    stale = verified_days is None or verified_days > VERDICT_TTL_DAYS

    if contradicts or resurging or stale:
      logger.info(
        "ROUTE: forcing full pipeline for known trend %s (contradicts=%s resurging=%s stale=%s)",
        matched_id, contradicts, resurging, stale,
      )
      return Command(goto="research")

    return Command(goto="probe_known")

  return Command(goto="research")

def build_graph() -> StateGraph:
  """Build the full pipeline graph (Observe -> Loop(Research...Decide))."""
  graph = StateGraph(AgentState)

  #  Nodes
  graph.add_node("observe", observe_node)
  graph.add_node("pop_cluster", pop_cluster_node)
  graph.add_node("merge_known", merge_known_node)  # fast-path for known trends
  graph.add_node("probe_known", probe_known)  # evidence-delta gate before merging into a known trend
  graph.add_node("research", research_node)
  graph.add_node("assess", assess_node)  # deterministic formula - no LLM
  graph.add_node("classify", classify_node)  # single-shot Terra high-effort
  graph.add_node("verify", verify_node)
  graph.add_node("report", report_node)  # short summary, GPT-4.1-mini
  graph.add_node("decide", decide_node)  # DB writes + JSON output, no LLM

  #  Router nodes (Command-based routing)
  graph.add_node("pop_router", route_after_pop)
  graph.add_node("assess_router", route_after_assess)
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
  graph.add_edge("classify", "verify")
  graph.add_edge("verify", "verify_router")
  graph.add_edge("decide", "decide_router")
  graph.add_edge("report", "pop_cluster")

  return graph.compile()



