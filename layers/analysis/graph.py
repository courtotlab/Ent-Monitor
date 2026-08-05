"""Layer 3 Analysis — LangGraph StateGraph wiring + sequential orchestration.

This is the entry point for running the analysis pipeline.  The outer loop
processes clusters sequentially to prevent DECIDE merge-check race conditions.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from layers.analysis.nodes.assess import assess_node
from layers.analysis.nodes.classify import classify_node
from layers.analysis.nodes.decide import decide_node
from layers.analysis.nodes.observe import observe_node
from layers.analysis.nodes.report import report_node
from layers.analysis.nodes.research import research_node
from layers.analysis.nodes.verify import verify_node
from layers.analysis.routing import (
  route_after_assess,
  route_after_classify,
  route_after_decide,
  route_after_verify,
)
from layers.analysis.state import AgentState
from layers.shared.paths import get_run_dir
from layers.analysis.tools.duckduckgo import set_circuit_breaker
from layers.analysis.tools.retry import DuckDuckGoCircuitBreaker

load_dotenv()
logger = logging.getLogger(__name__)



def run_analysis(posts: list[dict], run_id: str | None = None) -> dict:
  """Run the full Layer 3 analysis pipeline.

  1. Calls OBSERVE once on all posts to produce a queue of clusters.
  2. The graph uses a pop_cluster loop to process clusters sequentially
     (RESEARCH → ASSESS → CLASSIFY → VERIFY → REPORT → DECIDE).
  """
  if not run_id:
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

  # Fresh circuit breaker per run
  circuit_breaker = DuckDuckGoCircuitBreaker()
  set_circuit_breaker(circuit_breaker)

  # Initialize state with raw posts for OBSERVE to consume
  initial_state = {
    "run_id": run_id,
    "clusters_queue": [],
    "cluster_results": [],
    "cluster_id": "observe_batch",
    "posts": posts,
    "search_context": "",
    "is_known_trend": False,
    "triage_flag": "unclear",
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
    "risk_score": 0.0,
    "reasoning": "",
    "needs_more_evidence": False,
    "no_evidence_found": False,
    "downgrade_reason": None,
    "downgraded_from_harmful": False,
    "verify_finding": None,
    "report": None,
    "needs_human_review": False,
    "tool_degraded": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
  }

  logger.info("Invoking Unified Graph for %d posts...", len(posts))
  app = build_graph()
  final_state = app.invoke(initial_state)

  cluster_results = final_state.get("cluster_results", [])
  
  #  Write run summary
  _write_run_summary(run_id, cluster_results)

  return {"run_id": run_id, "clusters": cluster_results}


def pop_cluster_node(state: AgentState) -> dict:
  """Pops the next cluster from the queue and resets research state."""
  # This acts as our Queue Manager. We process clusters one at a time 
  # sequentially to prevent race conditions during DB writes and graph state merges.
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
    "search_context": cluster.get("search_context", ""),
    "is_known_trend": cluster.get("is_known_trend", False),
    "triage_flag": cluster.get("triage_flag", "unclear"),
    
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
    "risk_score": 0.0,
    "reasoning": "",
    "needs_more_evidence": False,
    "no_evidence_found": False,
    "downgrade_reason": None,
    "downgraded_from_harmful": False,
    "verify_finding": None,
    "report": None,
    "needs_human_review": False,
    "tool_degraded": False,
    "research_retries_left": 3,
    "verify_retries_left": 3,
  }

def route_after_pop(state: AgentState) -> Command:
  """If there's an active cluster, go to research. Otherwise END."""
  if state.get("cluster_id") == "DONE":
    return Command(goto=END)
  return Command(goto="research")

def build_graph() -> StateGraph:
  """Build the full pipeline graph (Observe -> Loop(Research...Decide))."""
  graph = StateGraph(AgentState)

  #  Nodes
  graph.add_node("observe", observe_node)
  graph.add_node("pop_cluster", pop_cluster_node)
  graph.add_node("research", research_node)
  graph.add_node("assess", assess_node)  # deterministic formula — no LLM
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
  
  # The core agentic loop. Notice the conditional routers (AssessRouter, 
  # ClassifyRouter, VerifyRouter) — they can all force the graph backward to RESEARCH 
  # if the evidence is weak or hallucinated, acting as strict guardrails.
  graph.add_edge("research", "assess")
  graph.add_edge("assess", "assess_router")
  graph.add_edge("classify", "classify_router")
  graph.add_edge("verify", "verify_router")
  graph.add_edge("decide", "decide_router")  # New: DECIDE gates REPORT
  graph.add_edge("report", "pop_cluster")    # REPORT loops back directly

  return graph.compile()


def _write_run_summary(run_id: str, cluster_results: list[dict]) -> None:
  """Write the run_summary.json file."""
  output_dir = get_run_dir(run_id, "final")
  output_dir.mkdir(parents=True, exist_ok=True)

  labels = {"HARMFUL": 0, "CONCERNING": 0, "SAFE": 0}
  needs_review = []
  for r in cluster_results:
    classification = r.get("classification", {})
    lbl = classification.get("label", "CONCERNING")
    labels[lbl] = labels.get(lbl, 0) + 1
    flags = r.get("flags", {})
    if isinstance(flags, dict) and flags.get("needs_human_review"):
      needs_review.append(r.get("cluster_id", "unknown"))

  summary = {
    "run_id": run_id,
    "completed_at": datetime.now(UTC).isoformat(),
    "total_clusters": len(cluster_results),
    "labels": labels,
    "needs_human_review": needs_review,
    "clusters": [
      {
        "cluster_id": r.get("cluster_id", "unknown"),
        "label": r.get("classification", {}).get("label", "CONCERNING"),
        "risk_score": r.get("classification", {}).get("risk_score", 0.0),
      }
      for r in cluster_results
    ],
  }

  summary_path = output_dir / "run_summary.json"
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

  logger.info("Run summary written to %s", summary_path)
