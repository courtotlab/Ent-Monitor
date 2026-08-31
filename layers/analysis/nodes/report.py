"""REPORT node short structured summary + final JSON output."""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from layers.analysis.utils.llm import invoke_llm
from pydantic import BaseModel, Field

from layers.analysis.core.state import AgentState
from layers.analysis.db.queries import write_cluster_to_db

logger = logging.getLogger(__name__)

REPORT_MODEL = "gpt-4.1-mini"

_PROMPT = """\
You are generating a short structured summary for a pediatric ENT health trend \
that has been analyzed and classified.  This is for human review.

Cluster: {cluster_id}
Label: {label}
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
  """REPORT node generates summary and appends to cluster_results."""
  cluster_id = state.get("cluster_id", "unknown")
  label = state.get("label", "MODERATE")
  risk_score = state.get("risk_score", 0.0)
  evidence = state.get("evidence", [])

  #  Determine evidence status
  if not evidence:
    evidence_status = "no_literature_found"
  elif any(e.get("source") == "pubmed" and e.get("is_relevant") for e in evidence):
    evidence_status = "pubmed_confirmed"
  else:
    evidence_status = "web_only"

  citations_used = state.get("supporting_evidence_ids", [])
  supporting_evidence = [
    e for e in evidence
    if (e.get("title") in citations_used or e.get("pmid") in citations_used)
    and not e.get("contradicts_harm")
  ]
  # fallback if LLM failed to populate supporting_evidence_ids
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
      "summary": f"Classification: {label}",
      "harm_mechanism": "Unable to generate LLM error",
      "key_evidence": [],
    }

  logger.info("REPORT: generated summary for %s", cluster_id)

  # Create an effective state snapshot with the report findings
  eff_state = dict(state)
  eff_state["trend_name"] = report.get("trend_name")
  eff_state["abstract"] = report.get("summary", "")
  eff_state["harm_mechanism"] = report.get("harm_mechanism", "")

  # Persist to DB (trends + posts)
  try:
    write_cluster_to_db(eff_state, centroid=eff_state.get("centroid"))
    if state.get("should_monitor", False):
      if state.get("slang_terms"):
        logger.info(
          "REPORT: cluster %s flagged for velocity monitoring (slang_terms=%d)",
          cluster_id, len(state["slang_terms"]),
        )
      else:
        logger.info(
          "REPORT: cluster %s is should_monitor=True but has no slang_terms",
          cluster_id,
        )
  except Exception as exc:
    logger.warning("REPORT: DB write failed for %s %s (local JSON saved)", cluster_id, exc)

  current_results = list(state.get("cluster_results", []))
  current_results.append(eff_state)

  return {"cluster_results": current_results}
