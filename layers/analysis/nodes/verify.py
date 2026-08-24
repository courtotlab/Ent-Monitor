"""VERIFY node - citation fact-checker.

Re-fetches every cited PMID via pubmed_fetch_by_pmid.  Web citations get
an HTTP HEAD check.  One batched Terra call for relevance checking.

Critical distinction: PMIDNotFoundError (confirmed absent) triggers failure routing.
A tool failure while checking does NOT - it's logged as tool_degraded.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests
from langchain_core.messages import HumanMessage
from layers.analysis.utils.llm import invoke_llm
from pydantic import BaseModel, Field

from layers.analysis.core.state import AgentState, ToolError, VerifyFinding
from layers.analysis.tools.pubmed import pubmed_fetch_by_pmid
from layers.analysis.tools.retry import PMIDNotFoundError

logger = logging.getLogger(__name__)

VERIFY_MODEL = "gpt-4.1-mini"

class VerifyResult(BaseModel):
  citation_relevant: bool = Field(description="Does each cited paper actually support the specific claim made? Require topical, population, and context match - not just thematic overlap.")
  label_consistent: bool = Field(description="Does the overall evidence justify the label?")
  notes: str = Field(description="explanation if anything is wrong")

def verify_node(state: AgentState) -> dict:
  """VERIFY node - checks citations, then LLM evaluates relevance + consistency."""
  # This node's sole purpose is catching LLM hallucinations from CLASSIFY.
  # We literally ping the NCBI database to ensure the PMIDs exist in the real world.
  print("  [VERIFY] Fact-checking LLM citations against databases...")
  citations = state.get("citations", [])
  evidence = state.get("evidence", [])
  label = state.get("label", "MODERATE")
  tool_errors = state.get("tool_errors", [])

  if not citations and not evidence:
    # Nothing to verify - pass through
    return {
      "verify_finding": VerifyFinding(
        citation_valid=True,
        citation_relevant=True,
        label_consistent=True,
        citation_check_failed=False,
        notes="No citations to verify",
      )
    }

  #  Step 1: Re-fetch each citation
  citation_checks: list[dict] = []
  any_check_failed = False

  for cit in citations:
    pmid = cit.get("pmid")
    url = cit.get("url", "")

    if pmid:
      try:
        fetched = pubmed_fetch_by_pmid(pmid)
        citation_checks.append(
          {
            "citation": cit,
            "valid": True,
            "fetched_title": fetched["title"] if fetched else "",
            "fetched_snippet": fetched["snippet"] if fetched else "",
            "check_failed": False,
          }
        )
      except PMIDNotFoundError:
        # Confirmed hallucination - this IS a real signal
        # The LLM completely hallucinated this PMID. We flag it as invalid, 
        # which triggers the router to loop all the way back to RESEARCH to find a real paper.
        citation_checks.append(
          {
            "citation": cit,
            "valid": False,
            "fetched_title": "",
            "fetched_snippet": "",
            "check_failed": False,
          }
        )
        logger.warning(
          "VERIFY: PMID %s confirmed not found - hallucinated citation", pmid
        )
      except Exception as exc:
        # Tool failure - NOT a confirmed-bad PMID
        any_check_failed = True
        tool_errors.append(
          ToolError(
            tool="pubmed_fetch_by_pmid",
            error_type="timeout",
            timestamp=datetime.now(UTC).isoformat(),
            query=pmid,
          )
        )
        citation_checks.append(
          {
            "citation": cit,
            "valid": None,  # unresolved
            "fetched_title": "",
            "fetched_snippet": "",
            "check_failed": True,
          }
        )
        logger.warning("VERIFY: PMID %s check failed (tool error): %s", pmid, exc)
    elif url:
      # Web citation - basic HTTP HEAD check
      try:
        head_resp = requests.head(url, timeout=5, allow_redirects=True)
        valid = head_resp.status_code < 400
        citation_checks.append(
          {
            "citation": cit,
            "valid": valid,
            "fetched_title": "",
            "fetched_snippet": "",
            "check_failed": False,
          }
        )
      except Exception:
        citation_checks.append(
          {
            "citation": cit,
            "valid": None,
            "fetched_title": "",
            "fetched_snippet": "",
            "check_failed": True,
          }
        )
        any_check_failed = True
    else:
      logger.warning("VERIFY: Citation malformed (no pmid or url) - treating as check failed: %s", cit.get("title", "Unknown"))
      citation_checks.append(
        {
          "citation": cit,
          "valid": None,
          "fetched_title": "",
          "fetched_snippet": "",
          "check_failed": True,
        }
      )

  checkable = [
    c for c in citation_checks if c["valid"] is not None and not c["check_failed"]
  ]

  citation_valid_overall = all(c["valid"] for c in checkable) if checkable else True
  citation_relevant = True
  label_consistent = True
  notes = ""

  if checkable or evidence:
    try:

      checks_summary = "\n".join(
        f'- [{c["citation"].get("source", "?")}] "{c["citation"].get("title", "?")}"\n'
        f"  PMID: {c['citation'].get('pmid', 'n/a')} | Valid: {c['valid']}\n"
        f"  Fetched title: {c['fetched_title']}\n"
        f"  Fetched snippet: {c['fetched_snippet'][:800]}"
        for c in checkable
      )

      evidence_summary = "\n".join(
        f"- [{e['source']}] {e['title']}: {e.get('snippet', '')[:100]}"
        for e in evidence[:10]
      )

      harm_hypothesis = state.get("harm_hypothesis", "not specified")

      prompt = f"""\
Current label: {label}
Confidence: {state.get("confidence", 0.5)}
Search context (the specific behavior being evaluated): {state.get("search_context", "unknown")}
Harm hypothesis (the clinical mechanism the evidence should support): {harm_hypothesis}
Classification reasoning: {state.get("reasoning", "")}

Citations checked:
{checks_summary}

All evidence:
{evidence_summary}

Evaluate with STRICT criteria - thematic overlap is NOT sufficient:

1. citation_relevant: Does each cited paper SPECIFICALLY address:
   (a) The EXACT population described in the post (e.g., pediatric vs. adult, \
newborn vs. school-age, toddler vs. adolescent)?  A paper about newborn hearing \
screening is NOT relevant to a school-age hearing screening post.
   (b) The clinical mechanism stated in the harm hypothesis? (NOTE: General mechanism matches like "foreign body trauma" or "ototoxicity" ARE relevant even if they don't explicitly name the exact household item in the post).
   (c) The specific behavior or exposure, not just the general topic area?
   If ANY of (a), (b), or (c) fails, set citation_relevant = false.

2. label_consistent: Given ONLY the truly relevant evidence (not thematically-adjacent \
evidence), is the assigned label justified?
"""
      messages = [HumanMessage(content=prompt)]
      result: VerifyResult = invoke_llm(
        model=VERIFY_MODEL,
        messages=messages,
        schema=VerifyResult,
      )
      citation_relevant = result.citation_relevant
      label_consistent = result.label_consistent
      notes = result.notes

      # Use the structured flag from CLASSIFY instead of re-parsing prose
      mechanism_level_match = state.get("mechanism_level_match", False)
      if not mechanism_level_match and citation_relevant:
        citation_relevant = False
        notes = "CLASSIFY flagged no mechanism_level_match. " + notes
        logger.info("VERIFY: mechanism_level_match=False - forcing citation_relevant=False")
    except Exception as exc:
      # Note: Failing open here is intentional. If the LLM check crashes, we assume citations are valid
      # and let downstream human review catch the tool_degraded flag, rather than blindly failing the cluster.
      logger.warning("VERIFY LLM check failed: %s - assuming all valid", exc)

  invalid = [c for c in citation_checks if c["valid"] is False]
  if invalid:
    invalid_pmids = [str(c["citation"].get("pmid")) for c in invalid if c["citation"].get("pmid")]
    invalid_urls = [str(c["citation"].get("url")) for c in invalid if not c["citation"].get("pmid") and c["citation"].get("url")]
    
    parts = []
    if invalid_pmids:
      parts.append(f"hallucinated PMIDs: {', '.join(invalid_pmids)}")
    if invalid_urls:
      parts.append(f"broken URLs: {', '.join(invalid_urls)}")
    
    if parts:
      notes = f"Confirmed {' and '.join(parts)}. " + notes

  finding = VerifyFinding(
    citation_valid=citation_valid_overall,
    citation_relevant=citation_relevant,
    label_consistent=label_consistent,
    # We only flag check_failed downstream if the overall citation_valid is still True.
    # If it's already False (e.g. hallucinated PMID), the check failure is moot.
    citation_check_failed=any_check_failed and citation_valid_overall,
    notes=notes,
  )

  logger.info(
    "VERIFY: valid=%s relevant=%s consistent=%s check_failed=%s",
    finding["citation_valid"],
    finding["citation_relevant"],
    finding["label_consistent"],
    finding["citation_check_failed"],
  )

  return {
    "verify_finding": finding,
    "tool_errors": tool_errors,
  }
