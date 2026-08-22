"""REPORT node short structured summary + final JSON output.

GPT-4.1-mini at low effort.  Only runs for clusters that cleared the
decide_router threshold (HARMFUL / CONCERNING / risk >= 0.5 / no_evidence).
Appends to cluster_results so the dashboard sees it.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from layers.analysis.utils.llm import invoke_llm
from pydantic import BaseModel, Field

from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import write_cluster_to_db
from layers.analysis.utils.formatters import build_cluster_json

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

CRITICAL: Ensure the summary and harm mechanism ONLY describe the exact behaviors mentioned in the provided Key evidence and classification reasoning. Do not pull in unrelated clinical terms or behaviors.

Generate a structured summary for this cluster.
"""

class ReportSummary(BaseModel):
  trend_name: str = Field(description="short behavioral name")
  summary: str = Field(description="2-3 sentence plain-English description")
  harm_mechanism: str = Field(description="1 sentence: why this is potentially harmful to pediatric ENT health")
  key_evidence: list[str] = Field(description="List of key evidence e.g., 'Paper 1 (PMID: ...)', 'Source 2'")

def report_node(state: AgentState) -> dict:
  """REPORT node generates summary and appends to cluster_results.

  Only called for clusters that crossed the dashboard threshold in decide_router.
  """
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

  citations_used = state.get("citations_used_as_support", [])
  supporting_evidence = [
    e for e in evidence
    if (e.get("title") in citations_used or e.get("pmid") in citations_used)
    and not e.get("contradicts_harm")
  ]
  # fallback if LLM failed to populate citations_used_as_support but we have relevant evidence
  if not supporting_evidence and evidence:
    supporting_evidence = [e for e in evidence if e.get("is_relevant") and not e.get("contradicts_harm")]

  evidence_summary = (
    "\n".join(
      f"- [{e['source']}] {e['title']}"
      + (f" (PMID: {e['pmid']})" if e.get("pmid") else "")
      + f"\n  {e.get('snippet', '')[:150]}"
      for e in supporting_evidence[:5]
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
    messages = [HumanMessage(content=prompt)]
    result_obj: ReportSummary = invoke_llm(model=REPORT_MODEL, messages=messages, schema=ReportSummary)
    report = result_obj.model_dump()
  except Exception as exc:
    logger.warning("REPORT LLM failed: %s generating minimal report", exc)
    report = {
      "trend_name": state.get("trend_name", "Unknown trend"),
      "summary": f"Classification: {label} with confidence {confidence:.2f}",
      "harm_mechanism": "Unable to generate LLM error",
      "key_evidence": [],
    }

  logger.info("REPORT: generated summary for %s", cluster_id)

  #  Build full cluster JSON
  cluster_json = build_cluster_json(
      state=state,
      abstract=report.get("summary", ""),
      harm_mechanism=report.get("harm_mechanism", ""),
      rising_non_trend=False,
      overrides={"trend_name": report.get("trend_name")} if report.get("trend_name") else None,
  )

  if tool_errors:
    cluster_json["tool_errors"] = [
      {
        "tool": te.get("tool", "unknown"),
        "error_type": te.get("error_type", "unknown"),
        "timestamp": te.get("timestamp", ""),
        "query": te.get("query", ""),
      }
      for te in tool_errors
    ]



  #  Persist to database (trends + posts tables)
  try:
    write_cluster_to_db(cluster_json, centroid=state.get("centroid"))
  except Exception as exc:
    logger.warning("REPORT: DB write failed for %s %s (local JSON saved)", cluster_id, exc)

  current_results = list(state.get("cluster_results", []))
  current_results.append(cluster_json)

  return {"report": report, "cluster_results": current_results}
