"""RESEARCH node — evidence gathering via tool calls.

Reads search_context (first pass) or evidence_gap (loop-back) and calls
the appropriate tool.  Appends results to state.evidence.  Deduplicates
queries via state.search_queries.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from layers.analysis.state import AgentState, EvidenceItem, ToolError
from layers.analysis.tools.crossref import crossref_search
from layers.analysis.tools.duckduckgo import duckduckgo_search
from layers.analysis.tools.pubmed import pubmed_search
from layers.analysis.tools.semantic_scholar import semantic_scholar_search

logger = logging.getLogger(__name__)

RESEARCH_MODEL = "gpt-4.1"


TOOL_MAP = {
  "pubmed_search": pubmed_search,
  "duckduckgo_search": duckduckgo_search,
  "semantic_scholar_search": semantic_scholar_search,
  "crossref_search": crossref_search,
}

_SYSTEM_PROMPT = """\
You are an evidence-gathering assistant for a pediatric ENT health trend \
surveillance system.  You have access to 4 free search tools:
- pubmed_search(query) — peer-reviewed medical literature (always try first for harm claims)
- duckduckgo_search(query) — news/web for social context
- semantic_scholar_search(query) — cross-discipline academic papers
- crossref_search(query) — DOI metadata lookup

Given the search context and any evidence gap, decide which tool to call \
and formulate the best query.  Do NOT repeat any query from the prior_queries list.
"""

_USER_PROMPT = """\
Search context: {search_context}
Evidence gap: {evidence_gap}
Prior queries (do NOT repeat): {prior_queries}
Current evidence count: {evidence_count}

Pick the best tool and query to fill the gap.
"""


class ResearchDecision(BaseModel):
  tool: Literal["pubmed_search", "duckduckgo_search", "semantic_scholar_search", "crossref_search"]
  query: str
  reasoning: str = Field(description="brief explanation of why this tool and query")


class RelevanceTag(BaseModel):
  index: int
  is_relevant: bool = Field(description="Does this evidence directly relate to the pediatric ENT behavior described?")
  contradicts_harm: bool = Field(description="Does this evidence argue the behavior is actually SAFE (not harmful)?")

class RelevanceTags(BaseModel):
  tags: list[RelevanceTag]


def research_node(state: AgentState) -> dict:
  """RESEARCH node — gathers evidence via tool calls.

  Returns state updates: evidence (appended), search_queries (appended),
  tool_errors (appended if any).
  """
  print(f"  [RESEARCH] Investigating: {state.get('search_context', 'trend')[:50]}...")
  evidence_gap = state.get("evidence_gap")
  search_context = state.get("search_context", "")
  prior_queries = state.get("search_queries", [])
  existing_evidence = list(state.get("evidence", []))
  tool_errors = list(state.get("tool_errors", []))

  # Determine tool and query — either from evidence_gap (loop-back) or LLM
  tool_name: str | None = None
  query: str | None = None

  if evidence_gap and evidence_gap.get("suggested_query"):
    tool_name = evidence_gap.get("suggested_tool", "pubmed_search")
    query = evidence_gap["suggested_query"]
    # Avoid exact repeats
    if query in prior_queries:
      query = query + " children"  # simple dedup suffix
  else:
    # First pass — ask LLM to pick tool and query
    try:
      llm = ChatOpenAI(
        model=RESEARCH_MODEL,
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0,
      ).with_structured_output(ResearchDecision)
      
      prompt = _USER_PROMPT.format(
        search_context=search_context,
        evidence_gap=str(evidence_gap) if evidence_gap else "None — first pass",
        prior_queries=str(prior_queries) if prior_queries else "[]",
        evidence_count=len(existing_evidence),
      )
      result: ResearchDecision = llm.invoke(_SYSTEM_PROMPT + "\n\n" + prompt)
      tool_name = result.tool
      query = result.query
    except Exception as exc:
      logger.warning("RESEARCH LLM failed: %s — falling back to pubmed_search", exc)
      tool_name = "pubmed_search"
      query = f"{search_context} pediatric ENT"

  if not tool_name or tool_name not in TOOL_MAP:
    tool_name = "pubmed_search"
  if not query:
    query = search_context

  # Call the tool
  logger.info("RESEARCH: calling %s with query=%r", tool_name, query)
  tool_fn = TOOL_MAP[tool_name]

  try:
    if tool_name == "duckduckgo_search":
      results: list[EvidenceItem] = tool_fn(query, tool_errors=tool_errors)
    else:
      results = tool_fn(query)
  except Exception as exc:
    logger.error("RESEARCH tool %s crashed: %s", tool_name, exc)
    tool_errors.append(
      ToolError(
        tool=tool_name,
        error_type="crash",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
      )
    )
    results = []

  # Tag relevance via LLM (lean toward LLM tagging per Open Q #2)
  if results:
    results = _tag_relevance(results, search_context)
    # Filter out irrelevant evidence to keep the final output highly targeted
    results = [r for r in results if r.get("is_relevant")]

  # Update state
  new_queries = list(prior_queries) + [query]

  # Append and cap the total strongly related evidence to 3 maximum
  new_evidence = existing_evidence + results
  new_evidence = new_evidence[:3]

  return {
    "evidence": new_evidence,
    "search_queries": new_queries,
    "tool_errors": tool_errors,
    "evidence_gap": None,  # consumed
  }


def _tag_relevance(
  items: list[EvidenceItem],
  search_context: str,
) -> list[EvidenceItem]:
  """Use LLM to tag is_relevant and contradicts_harm on evidence items."""
  if not items:
    return items

  try:
    llm = ChatOpenAI(
      model=RESEARCH_MODEL,
      api_key=os.getenv("OPENAI_API_KEY"),
      temperature=0,
    ).with_structured_output(RelevanceTags)

    evidence_summary = "\n".join(
      f"[{i}] {item['title']}: {item['snippet'][:150]}" for i, item in enumerate(items)
    )

    prompt = f"""\
You are tagging evidence relevance for a pediatric ENT health trend investigation.

Search context: {search_context}

Evidence items:
{evidence_summary}
"""
    result: RelevanceTags = llm.invoke(prompt)

    for tag in result.tags:
      idx = tag.index
      if 0 <= idx < len(items):
        items[idx]["is_relevant"] = tag.is_relevant
        items[idx]["contradicts_harm"] = tag.contradicts_harm
  except Exception as exc:
    logger.warning(
      "Relevance tagging failed: %s — leaving all as is_relevant=False", exc
    )

  return items
