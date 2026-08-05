"""RESEARCH node — evidence gathering via tool calls.

Reads search_context (first pass) or evidence_gap (loop-back) and calls
the appropriate tool.  Appends results to state.evidence.  Deduplicates
queries via state.search_queries.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
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
- duckduckgo_search(query) — news/web for social context, FDA/CPSC alerts, ER reports
- semantic_scholar_search(query) — cross-discipline academic papers
- crossref_search(query) — DOI metadata lookup

CRITICAL: Social media trends use colloquial language that will NEVER appear in \
academic literature.  You MUST translate the behavior into its underlying clinical \
harm mechanism before generating a search query.

Examples of the required translation:
- "onion sock for earache" → harm_hypothesis: "delayed treatment of acute otitis media" \
  → query: "delayed treatment otitis media complications pediatric"
- "ear candling toddler" → harm_hypothesis: "thermal injury to external auditory canal" \
  → query: "ear candling complications case report"
- "q-tip challenge ear" → harm_hypothesis: "tympanic membrane perforation from cotton swab" \
  → query: "cotton swab tympanic membrane perforation pediatric"

Do NOT search using the trend's own vocabulary (e.g., "onion sock", "TikTok trend").
Do NOT repeat any query from the prior_queries list.
"""

_USER_PROMPT = """\
First state ALL underlying physical/clinical harm mechanisms this behavior could \
plausibly cause - in general medical terms, NOT the trend's vocabulary. E.g., if a \
trend risks both "delayed treatment of acute otitis media" and "thermal skin injury", \
list both and provide a distinct search query for each mechanism.

If the behavior is clearly benign (educational content, clinical question, anatomy \
explainer with no risky action), state harm_hypothesis as "none - benign content" \
and provide a single search for evidence confirming the behavior is safe instead.

Search context: {search_context}
Harm hypothesis: {harm_hypothesis}
Evidence gap: {evidence_gap}
Prior queries (do NOT repeat): {prior_queries}
Current evidence count: {evidence_count}
"""


class ResearchQuery(BaseModel):
  harm_hypothesis: str = Field(description="The underlying clinical harm mechanism in medical terms. E.g., 'delayed treatment of acute otitis media' or 'none - benign content'.")
  tool: Literal["pubmed_search", "duckduckgo_search", "semantic_scholar_search", "crossref_search"]
  query: str = Field(description="Search query derived from harm_hypothesis, using medical/clinical terminology")
  reasoning: str = Field(description="brief explanation of why this tool and query")

class ResearchDecision(BaseModel):
  queries: list[ResearchQuery] = Field(description="List of queries. Provide one for EACH plausible harm mechanism (up to 2).")


class RelevanceTag(BaseModel):
  index: int
  is_relevant: bool = Field(description="Does this evidence directly relate to the pediatric ENT behavior described?")
  contradicts_harm: bool = Field(description="Does this evidence argue the behavior is actually SAFE (not harmful)?")

class RelevanceTags(BaseModel):
  tags: list[RelevanceTag]


def research_node(state: AgentState) -> dict:
  """RESEARCH node — gathers evidence via tool calls.

  Returns state updates: evidence (appended), search_queries (appended),
  tool_errors (appended if any), harm_hypothesis (set on first pass).
  """
  # We never search PubMed using TikTok slang (e.g. "onion sock"). 
  # The LLM must first translate the slang into a clinical harm_hypothesis here.
  print(f"  [RESEARCH] Investigating: {state.get('search_context', 'trend')[:50]}...")
  evidence_gap = state.get("evidence_gap")
  search_context = state.get("search_context", "")
  prior_queries = state.get("search_queries", [])
  existing_evidence = list(state.get("evidence", []))
  tool_errors = list(state.get("tool_errors", []))
  harm_hypothesis = state.get("harm_hypothesis", "")

  queries_to_run = []

  if evidence_gap and evidence_gap.get("suggested_query"):
    tool_name = evidence_gap.get("suggested_tool", "pubmed_search")
    query = evidence_gap["suggested_query"]
    while query in prior_queries:
      query = query + " children"  # simple dedup suffix
    queries_to_run.append({"tool_name": tool_name, "query": query, "harm_hypothesis": harm_hypothesis})
  else:
    # First pass — ask LLM to pick tool and query with mechanism-hypothesis
    try:
      llm = ChatOpenAI(
        model=RESEARCH_MODEL,
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0,
      ).with_structured_output(ResearchDecision)
      
      prompt = _USER_PROMPT.format(
        search_context=search_context,
        harm_hypothesis=harm_hypothesis or "Not yet determined — generate one now",
        evidence_gap=str(evidence_gap) if evidence_gap else "None — first pass",
        prior_queries=str(prior_queries) if prior_queries else "[]",
        evidence_count=len(existing_evidence),
      )
      result: ResearchDecision = llm.invoke(_SYSTEM_PROMPT + "\n\n" + prompt)
      for rq in result.queries[:2]: # limit to max 2 parallel queries
        queries_to_run.append({"tool_name": rq.tool, "query": rq.query, "harm_hypothesis": rq.harm_hypothesis})
      # Capture harm_hypothesis on first pass
      if not harm_hypothesis and result.queries:
        harm_hypothesis = " ; ".join(dict.fromkeys(rq.harm_hypothesis for rq in result.queries))
    except Exception as exc:
      logger.warning("RESEARCH LLM failed: %s - falling back to pubmed_search", exc)
      queries_to_run.append({"tool_name": "pubmed_search", "query": f"{search_context} pediatric ENT harm mechanism", "harm_hypothesis": ""})

  if not queries_to_run:
    queries_to_run.append({"tool_name": "pubmed_search", "query": search_context, "harm_hypothesis": ""})

  results: list[EvidenceItem] = []
  new_queries = list(prior_queries)

  for q_data in queries_to_run:
    tool_name = q_data.get("tool_name", "pubmed_search")
    query = q_data.get("query", search_context)
    if not tool_name or tool_name not in TOOL_MAP:
      tool_name = "pubmed_search"

    logger.info("RESEARCH: calling %s with query=%r (hypothesis=%r)", tool_name, query, harm_hypothesis)
    tool_fn = TOOL_MAP[tool_name]

    try:
      if tool_name == "duckduckgo_search":
        results.extend(tool_fn(query, tool_errors=tool_errors))
      else:
        results.extend(tool_fn(query))
    except Exception as exc:
      logger.error("RESEARCH tool %s crashed: %s", tool_name, exc)
      tool_errors.append(
        ToolError(
          tool=tool_name,
          error_type="exception",
          timestamp=datetime.now(UTC).isoformat(),
          query=query,
        )
      )

    # On the first pass, also run DuckDuckGo in parallel to catch fast-moving social/news trends
    # Medical literature is slow. We force a parallel DuckDuckGo news search 
    # to catch breaking FDA/CPSC warnings that haven't reached academia yet.
    if not evidence_gap and tool_name != "duckduckgo_search":
      ddg_query = f"{query} news OR warning"
      logger.info("RESEARCH: parallel first-pass calling duckduckgo_search with query=%r", ddg_query)
      try:
        ddg_results = TOOL_MAP["duckduckgo_search"](ddg_query, tool_errors=tool_errors)
        results.extend(ddg_results)
      except Exception as exc:
        logger.warning("RESEARCH parallel duckduckgo_search failed: %s", exc)

    new_queries.append(query)

  # Tag relevance via LLM (lean toward LLM tagging per Open Q #2)
  if results:
    # We strictly filter out evidence that doesn't explicitly match the harm_hypothesis.
    # This prevents dumping 20 irrelevant papers into the massive CLASSIFY model downstream.
    results = _tag_relevance(results, search_context, harm_hypothesis)
    results = [r for r in results if r.get("is_relevant")]

  # Dedup by PMID (or title if no PMID) and cap to prevent LLM context confusion.
  seen = set()
  unique_evidence = []
  for item in existing_evidence + results:
    key = item.get("pmid") or item.get("title", "").strip().lower()
    if key and key not in seen:
      seen.add(key)
      unique_evidence.append(item)
    elif not key:
      unique_evidence.append(item)

  # Capping saves massive token costs downstream. Cap at 3 for first pass, 5 for loop-backs.
  cap = 5 if evidence_gap else 3
  new_evidence = unique_evidence[:cap]

  return {
    "evidence": new_evidence,
    "search_queries": new_queries,
    "tool_errors": tool_errors,
    "evidence_gap": None,  # consumed
    "harm_hypothesis": harm_hypothesis,
  }


def _tag_relevance(
  items: list[EvidenceItem],
  search_context: str,
  harm_hypothesis: str = "",
) -> list[EvidenceItem]:
  """Use LLM to tag is_relevant and contradicts_harm on evidence items.

  Uses harm_hypothesis (when available) to enforce mechanism-level relevance,
  not just keyword/topic overlap.
  """
  if not items:
    return items

  try:
    llm = ChatOpenAI(
      model=RESEARCH_MODEL,
      api_key=os.getenv("OPENAI_API_KEY"),
      temperature=0,
    ).with_structured_output(RelevanceTags)

    evidence_summary = "\n".join(
      f"[{i}] {item['title']}\n    Source: {item['source']}\n    {item['snippet'][:800]}"
      for i, item in enumerate(items)
    )

    hypothesis_block = ""
    if harm_hypothesis and not harm_hypothesis.strip().lower().startswith("none"):
      hypothesis_block = f"""\nHarm hypothesis (the clinical mechanism being investigated): {harm_hypothesis}

CRITICAL: An evidence item is ONLY relevant if it directly addresses the harm \
hypothesis above — not just a shared keyword or topic area. For example:
- A paper about laryngeal foreign body aspiration is NOT relevant to a cluster \
about flu season / sore throat / allergy management, even though both involve \
ENT anatomy.
- A paper about newborn hearing screening is NOT relevant to school-age hearing \
screening, even though both mention "hearing screening."
- A paper about atopic dermatitis sleep disturbance is NOT relevant to snoring \
from adenotonsillar hypertrophy, even though both mention "sleep."
"""

    prompt = f"""\
You are tagging evidence relevance for a pediatric ENT health trend investigation.

Search context: {search_context}
{hypothesis_block}
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
