"""RESEARCH node - evidence gathering via fixed tool cascade.

: Fixed order regardless of LLM: PubMed first → Semantic Scholar if needed →
CrossRef for DOI enrichment → DuckDuckGo only if zero clinical sources.

The LLM still generates the harm_hypothesis (clinical translation) but no longer
chooses which tools to run. Source tier tagging is applied after gathering.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from langchain_core.messages import SystemMessage, HumanMessage
from layers.analysis.utils.llm import invoke_llm
from pydantic import BaseModel, Field

from layers.analysis.core.state import AgentState, EvidenceItem, ToolError
from layers.analysis.tools.crossref import crossref_search
from layers.analysis.tools.duckduckgo import duckduckgo_search
from layers.analysis.tools.pubmed import pubmed_search
from layers.analysis.tools.semantic_scholar import semantic_scholar_search

logger = logging.getLogger(__name__)

RESEARCH_MODEL = "gpt-4.1"

# Source tier classification
CLINICAL_SOURCES = frozenset({"pubmed", "semantic_scholar"})

_SYSTEM_PROMPT = """\
You are an evidence-gathering assistant for a pediatric ENT health trend \
surveillance system.

CRITICAL: Social media trends use colloquial language that will NEVER appear in \
academic literature.  You MUST translate the behavior into its underlying clinical \
harm mechanism before we can search for evidence.

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
plausibly cause - in general medical terms, NOT the trend's vocabulary.

If the behavior is clearly benign (educational content, clinical question, anatomy \
explainer with no risky action), state harm_hypothesis as "none - benign content" \
and provide a single search query for confirming safety.

Search context: {search_context}
Harm hypothesis: {harm_hypothesis}
Evidence gap: {evidence_gap}
Prior queries (do NOT repeat): {prior_queries}
Current evidence count: {evidence_count}
{known_trend_context}
"""

class ResearchQuery(BaseModel):
  harm_hypothesis: str = Field(description="The underlying clinical harm mechanism in medical terms.")
  query: str = Field(description="Search query derived from harm_hypothesis, using medical/clinical terminology")
  reasoning: str = Field(description="brief explanation of why this query")

class ResearchDecision(BaseModel):
  queries: list[ResearchQuery] = Field(description="List of queries. Provide one for EACH plausible harm mechanism (up to 2).")

class RelevanceTag(BaseModel):
  index: int
  is_relevant: bool = Field(description="Does this evidence directly relate to the pediatric ENT behavior described?")
  contradicts_harm: bool = Field(description="Does this evidence argue the behavior is actually SAFE (not harmful)?")

class RelevanceTags(BaseModel):
  tags: list[RelevanceTag]

def _tag_source_tier(item: EvidenceItem) -> EvidenceItem:
  """Tag each evidence item with its source tier."""
  item["source_tier"] = "clinical" if item.get("source") in CLINICAL_SOURCES else "web_only"
  return item

def research_node(state: AgentState) -> dict:
  """RESEARCH node - gathers evidence via fixed tool cascade.

  tool order:
  1. PubMed first (always)
  2. Semantic Scholar if PubMed returns < 2 relevant clinical sources
  3. CrossRef to validate/enrich DOIs (not a search step)
  4. DuckDuckGo only if steps 1-3 return zero clinical sources
  """
  print(f"  [RESEARCH] Investigating: {state.get('search_context', 'trend')[:50]}...")
  evidence_gap = state.get("evidence_gap")
  search_context = state.get("search_context", "")
  prior_queries = state.get("search_queries", [])
  existing_evidence = list(state.get("evidence", []))
  tool_errors = list(state.get("tool_errors", []))
  harm_hypothesis = state.get("harm_hypothesis", "")

  # Step 0: Get harm_hypothesis + clinical queries from LLM
  queries_to_run = []

  if evidence_gap and evidence_gap.get("suggested_query"):
    query = evidence_gap["suggested_query"]
    original_query = query
    attempt = 1
    while query in prior_queries and attempt <= 3:
      query = f"{original_query} filter {attempt}"
      attempt += 1
    queries_to_run.append({"query": query, "harm_hypothesis": harm_hypothesis})
  else:
    try:

      known_trend_context = ""
      if state.get("is_known_trend") and state.get("matched_trend_id"):
        db_posts = state.get("db_trend_post_count", 0)
        db_label = state.get("db_trend_label", "unknown")
        known_trend_context = f"Known trend: {state['matched_trend_id']} ({db_posts} existing posts, label: {db_label})"

      prompt_text = _USER_PROMPT.format(
        search_context=search_context,
        harm_hypothesis=harm_hypothesis or "Not yet determined - generate one now",
        evidence_gap=str(evidence_gap) if evidence_gap else "None - first pass",
        prior_queries=str(prior_queries) if prior_queries else "[]",
        evidence_count=len(existing_evidence),
        known_trend_context=known_trend_context,
      )
      messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=prompt_text)
      ]
      result: ResearchDecision = invoke_llm(
        model=RESEARCH_MODEL,
        messages=messages,
        schema=ResearchDecision,
      )
      for rq in result.queries[:2]:
        queries_to_run.append({"query": rq.query, "harm_hypothesis": rq.harm_hypothesis})
      if not harm_hypothesis and result.queries:
        harm_hypothesis = " ; ".join(dict.fromkeys(rq.harm_hypothesis for rq in result.queries))
    except Exception as exc:
      logger.warning("RESEARCH LLM failed: %s - falling back to pubmed_search", exc)
      queries_to_run.append({"query": f"{search_context} pediatric ENT harm mechanism", "harm_hypothesis": ""})

  if not queries_to_run:
    queries_to_run.append({"query": search_context, "harm_hypothesis": ""})

  # Fixed cascade: PubMed → DuckDuckGo → Semantic Scholar → CrossRef
  results: list[EvidenceItem] = []
  new_queries = list(prior_queries)

  for q_data in queries_to_run:
    query = q_data.get("query", search_context)

    # Step 1: Always PubMed first
    logger.info("RESEARCH: step 1 - pubmed_search with query=%r", query)
    try:
      pubmed_results = pubmed_search(query)
      results.extend(pubmed_results)
    except Exception as exc:
      logger.error("RESEARCH pubmed_search crashed: %s", exc)
      tool_errors.append(ToolError(tool="pubmed_search", error_type="exception", timestamp=datetime.now(UTC).isoformat(), query=query))

    new_queries.append(query)

  # Tag source tiers so we can count clinical sources
  for item in results:
    _tag_source_tier(item)

  # Tag relevance via LLM
  if results:
    results = _tag_relevance(results, search_context, harm_hypothesis)

  # Step 2: DuckDuckGo (Always run for new trends that might not be in PubMed yet)
  logger.info("RESEARCH: step 2 - duckduckgo_search (always run for emerging trends)")
  for q_data in queries_to_run:
    query = q_data.get("query", search_context)
    ddg_query = f"{query} FDA OR hospital OR official warning OR news"
    try:
      ddg_results = duckduckgo_search(ddg_query, tool_errors=tool_errors)
      for item in ddg_results:
        _tag_source_tier(item)
      results.extend(ddg_results)
    except Exception as exc:
      logger.warning("RESEARCH duckduckgo_search failed: %s", exc)

  # Re-tag relevance for web results
  if results:
    results = _tag_relevance(results, search_context, harm_hypothesis)

  # Step 3: Semantic Scholar if PubMed returned < 2 relevant clinical sources
  clinical_relevant = sum(
    1 for e in results
    if e.get("source_tier") == "clinical" and e.get("is_relevant", False)
  )

  if clinical_relevant < 2:
    logger.info("RESEARCH: step 3 - semantic_scholar_search (only %d clinical sources from PubMed)", clinical_relevant)
    for q_data in queries_to_run:
      query = q_data.get("query", search_context)
      try:
        ss_results = semantic_scholar_search(query)
        for item in ss_results:
          _tag_source_tier(item)
        results.extend(ss_results)
      except Exception as exc:
        logger.error("RESEARCH semantic_scholar_search crashed: %s", exc)
        tool_errors.append(ToolError(tool="semantic_scholar_search", error_type="exception", timestamp=datetime.now(UTC).isoformat(), query=query))

    # Re-tag relevance for new items
    if results:
      results = _tag_relevance(results, search_context, harm_hypothesis)

  # Step 4: CrossRef to validate/enrich DOIs already found (not a search step)
  dois_found = [e for e in results if e.get("pmid") or "doi.org" in e.get("url", "")]
  if dois_found:
    logger.info("RESEARCH: step 4 - crossref DOI enrichment for %d items", len(dois_found))
    for e in dois_found[:3]:  # limit enrichment calls
      doi_query = e.get("pmid") or e.get("title", "")
      if doi_query:
        try:
          cr_results = crossref_search(doi_query)
          for item in cr_results:
            _tag_source_tier(item)
          results.extend(cr_results)
        except Exception as exc:
          logger.warning("RESEARCH crossref enrichment failed: %s", exc)

  # Filter to relevant only
  results = [r for r in results if r.get("is_relevant")]

  # Dedup by PMID or title
  seen = set()
  unique_evidence = []
  for item in results + existing_evidence:
    key = item.get("pmid") or item.get("title", "").strip().lower()
    if key and key not in seen:
      seen.add(key)
      unique_evidence.append(item)
    elif not key:
      unique_evidence.append(item)

  # Cap at 5 to control downstream token cost
  new_evidence = unique_evidence[:5]

  return {
    "evidence": new_evidence,
    "search_queries": new_queries,
    "tool_errors": tool_errors,
    "evidence_gap": None,
    "harm_hypothesis": harm_hypothesis,
  }

def _tag_relevance(
  items: list[EvidenceItem],
  search_context: str,
  harm_hypothesis: str = "",
) -> list[EvidenceItem]:
  """Use LLM to tag is_relevant and contradicts_harm on evidence items."""
  if not items:
    return items

  try:

    evidence_summary = "\n".join(
      f"[{i}] {item['title']}\n    Source: {item['source']} (tier: {item.get('source_tier', 'unknown')})\n    {item['snippet'][:800]}"
      for i, item in enumerate(items)
    )

    hypothesis_block = ""
    if harm_hypothesis and not harm_hypothesis.strip().lower().startswith("none"):
      hypothesis_block = f"""\nHarm hypothesis (the clinical mechanism being investigated): {harm_hypothesis}

CRITICAL: An evidence item is ONLY relevant if it directly addresses the harm \
hypothesis above (or the core trend behavior) - not just a shared keyword or topic area.
- Authoritative warnings (e.g., FDA, CDC, certified hospitals) in news articles that explicitly address the trend ARE highly relevant.
- A paper about laryngeal foreign body aspiration is NOT relevant to a cluster \
about flu season / sore throat / allergy management.
- A paper about newborn hearing screening is NOT relevant to school-age hearing screening.
"""

    prompt_text = f"""\
You are tagging evidence relevance for a pediatric ENT health trend investigation.

Search context: {search_context}
{hypothesis_block}
Evidence items:
{evidence_summary}
"""
    messages = [HumanMessage(content=prompt_text)]
    result: RelevanceTags = invoke_llm(
      model=RESEARCH_MODEL,
      messages=messages,
      schema=RelevanceTags,
    )

    for tag in result.tags:
      idx = tag.index
      if 0 <= idx < len(items):
        items[idx]["is_relevant"] = tag.is_relevant
        items[idx]["contradicts_harm"] = tag.contradicts_harm
  except Exception as exc:
    logger.warning(
      "Relevance tagging failed: %s - leaving all as is_relevant=False", exc
    )

  return items
