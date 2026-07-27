"""REPORT node — short structured summary + final JSON output.

GPT-4.1-mini at low effort.  Only runs for clusters that cleared the
decide_router threshold (HARMFUL / CONCERNING / risk >= 0.5 / no_evidence).
Writes the full cluster JSON to results/final/<run_id>/ and appends to
cluster_results so the dashboard sees it.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from layers.analysis.state import AgentState

logger = logging.getLogger(__name__)

REPORT_MODEL = "gpt-4.1-mini"


_PROMPT = """\
You are generating a short structured summary for a pediatric ENT health trend \
that has been analyzed and classified.  This is for human review.

Cluster: {cluster_id}
Label: {label} (confidence: {confidence:.2f})
Risk score: {risk_score:.3f}
Evidence status: {evidence_status}

Key evidence:
{evidence_summary}

Classification reasoning:
{reasoning}

Generate a structured summary for this cluster.
"""

class ReportSummary(BaseModel):
  cluster_id: str
  label: str
  risk_score: float
  trend_name: str = Field(description="short behavioral name")
  summary: str = Field(description="2-3 sentence plain-English description")
  harm_mechanism: str = Field(description="1 sentence: why this is potentially harmful to pediatric ENT health")
  key_evidence: list[str] = Field(description="List of key evidence e.g., 'Paper 1 (PMID: ...)', 'Source 2'")
  confidence: float
  evidence_status: str
  post_count: int
  platforms: list[str]
  is_rising: bool


def report_node(state: AgentState) -> dict:
  """REPORT node — generates summary, writes full JSON, appends to cluster_results.

  Only called for clusters that crossed the dashboard threshold in decide_router.
  """
  print("  [REPORT] Generating summary report...")

  run_id = state.get("run_id", "unknown_run")
  cluster_id = state.get("cluster_id", "unknown")
  label = state.get("label", "CONCERNING")
  confidence = state.get("confidence", 0.5)
  risk_score = state.get("risk_score", 0.0)
  evidence = state.get("evidence", [])
  posts = state.get("posts", [])
  tool_errors = state.get("tool_errors", [])
  vf = state.get("verify_finding")

  #  Determine evidence status
  if state.get("no_evidence_found"):
    evidence_status = "no_literature_found"
  elif any(e.get("source") == "pubmed" and e.get("is_relevant") for e in evidence):
    evidence_status = "pubmed_confirmed"
  elif evidence:
    evidence_status = "web_only"
  else:
    evidence_status = "no_literature_found"

  platforms = list(set(p.get("platform", "unknown") for p in posts))

  evidence_summary = (
    "\n".join(
      f"- [{e['source']}] {e['title']}"
      + (f" (PMID: {e['pmid']})" if e.get("pmid") else "")
      + f"\n  {e.get('snippet', '')[:150]}"
      for e in evidence[:5]
    )
    or "(no evidence)"
  )

  prompt = _PROMPT.format(
    cluster_id=cluster_id,
    label=label,
    confidence=confidence,
    risk_score=risk_score,
    evidence_status=evidence_status,
    evidence_summary=evidence_summary,
    reasoning=state.get("reasoning", ""),
  )

  #  LLM call
  try:
    llm = ChatOpenAI(
      model=REPORT_MODEL,
      api_key=os.getenv("OPENAI_API_KEY"),
      temperature=0,
    ).with_structured_output(ReportSummary)
    
    result_obj: ReportSummary = llm.invoke(prompt)
    report = result_obj.model_dump()
  except Exception as exc:
    logger.warning("REPORT LLM failed: %s — generating minimal report", exc)
    report = {
      "cluster_id": cluster_id,
      "label": label,
      "risk_score": risk_score,
      "trend_name": state.get("search_context", "Unknown trend"),
      "summary": f"Classification: {label} with confidence {confidence:.2f}",
      "harm_mechanism": "Unable to generate — LLM error",
      "key_evidence": [],
      "confidence": confidence,
      "evidence_status": evidence_status,
      "post_count": len(posts),
      "platforms": platforms,
      "is_rising": False,
    }

  logger.info("REPORT: generated summary for %s", cluster_id)

  #  Build and write full cluster JSON
  no_evidence = state.get("no_evidence_found", False)
  needs_human_review = state.get("needs_human_review", False)
  tool_degraded = state.get("tool_degraded", False)
  downgraded = state.get("downgrade_reason") is not None and "HARMFUL" in (
    state.get("downgrade_reason") or ""
  )

  cluster_json = {
    "run_id": run_id,
    "cluster_id": cluster_id,
    "processed_at": datetime.now(timezone.utc).isoformat(),
    "classification": {
      "label": label,
      "confidence": confidence,
      "risk_score": risk_score,
      "evidence_status": evidence_status,
      "no_evidence_found": no_evidence,
      "verify_passed": (
        vf is not None
        and vf.get("citation_valid", True) is not False
        and vf.get("citation_relevant", True)
      ),
    },
    "trend": {
      "trend_name": report.get("trend_name", cluster_id),
      "is_known_trend": state.get("is_known_trend", False),
      "is_rising": report.get("is_rising", False),
      "post_count": len(posts),
      "platforms": platforms,
    },
    "posts": [
      {
        "post_id": p.get("post_id", ""),
        "platform": p.get("platform", ""),
        "caption_text": (p.get("caption_text") or "")[:200],
        "sbert_score": p.get("sbert_score", 0.0),
        "likes": p.get("likes", 0),
        "views": p.get("views", 0),
      }
      for p in posts[:20]
    ],
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
      for e in evidence
    ],
    "reasoning": {
      "research_retries_left": state.get("research_retries_left", 0),
      "verify_retries_left": state.get("verify_retries_left", 0),
      "evidence_score_at_assess": state.get("evidence_score", 0.0),
      "why_this_label": state.get("reasoning", ""),
      "downgrade_reason": state.get("downgrade_reason"),
    },
    "report_summary": {
      "summary": report.get("summary", ""),
      "harm_mechanism": report.get("harm_mechanism", ""),
      "key_evidence": report.get("key_evidence", []),
    },
    "flags": {
      "needs_human_review": needs_human_review,
      "rising_non_trend": False,
      "no_literature_found": no_evidence,
      "downgraded_from_harmful": downgraded,
      "tool_degraded": tool_degraded,
    },
  }

  if tool_errors:
    cluster_json["tool_errors"] = [
      {
        "tool": te["tool"],
        "error_type": te["error_type"],
        "timestamp": te["timestamp"],
        "query": te["query"],
      }
      for te in tool_errors
    ]

  output_dir = Path("results") / "final" / run_id
  output_dir.mkdir(parents=True, exist_ok=True)
  output_path = output_dir / f"{cluster_id}.json"
  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(cluster_json, f, indent=2, ensure_ascii=False)
  logger.info("REPORT: wrote %s", output_path)

  current_results = list(state.get("cluster_results", []))
  current_results.append(cluster_json)

  return {"report": report, "cluster_results": current_results}
