"""PROBE node - evidence-delta check gating the known-trend fast-path merge.

Runs ONE date-restricted PubMed query covering everything published since the
trend's last full verification. Any new hit escalates the cluster to RESEARCH
(the literature changed - the stored verdict must be re-examined); silence
allows the LLM-free MERGE to proceed.

Fail-open policy: on tool errors the cluster merges anyway. Availability beats
marginal safety here because the contradiction/surge/staleness gates in
route_after_pop remain active upstream.
"""

from __future__ import annotations

import logging
from datetime import datetime

from langgraph.types import Command

from layers.analysis.core.state import AgentState
from layers.analysis.tools.pubmed import pubmed_search

logger = logging.getLogger(__name__)

PROBE_MAX_RESULTS = 3  # existence check only - one new paper is enough to escalate


def _pubmed_date_filter(query: str, since_iso: str | None) -> str:
    """Append a publication-date restriction to a PubMed esearch term."""
    if not since_iso:
        return query
    try:
        since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("PROBE: unparseable last_verified_at %r - probing without date filter", since_iso)
        return query
    cutoff = since.strftime("%Y/%m/%d")
    return f'{query} AND ("{cutoff}"[Date - Publication] : "3000"[Date - Publication])'


def probe_known(state: AgentState) -> Command:
    """Cheap freshness probe for known trends whose verdict passed the route gates."""
    matched_id = state.get("matched_trend_id") or "unknown"
    query = state.get("search_context", "") or state.get("trend_name", "")
    since_iso = state.get("db_trend_last_verified")

    if not query.strip():
        # Nothing meaningful to search - merging is cheaper than escalating blind.
        logger.warning("PROBE: no search context for trend %s - failing open to merge", matched_id)
        return Command(goto="merge_known")

    dated_query = _pubmed_date_filter(query, since_iso)
    cutoff_label = (since_iso or "all time")[:10]

    print(f"  [PROBE] Evidence delta for known trend {matched_id} since {cutoff_label}...")
    try:
        results = pubmed_search(dated_query, max_results=PROBE_MAX_RESULTS)
    except Exception as exc:
        logger.warning("PROBE: pubmed_search failed (%s) - failing open to merge", exc)
        return Command(goto="merge_known")

    if results:
        logger.info(
            "PROBE: %d new publication(s) for trend %s since %s - escalating to RESEARCH",
            len(results), matched_id, cutoff_label,
        )
        return Command(goto="research")

    logger.info("PROBE: no new publications for trend %s since %s - proceeding to MERGE", matched_id, cutoff_label)
    return Command(goto="merge_known")
