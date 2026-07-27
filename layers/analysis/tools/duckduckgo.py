"""DuckDuckGo search tool — free, no API key.

Uses the ``duckduckgo-search`` Python package.  Checks the run-level
circuit breaker before every call; if the breaker is open, returns []
immediately and logs a ``circuit_open`` ToolError.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from duckduckgo_search import DDGS

from layers.analysis.state import EvidenceItem, ToolError
from layers.analysis.tools.retry import DuckDuckGoCircuitBreaker, with_retry

logger = logging.getLogger(__name__)

# Module-level default — overridden by the orchestrator per run.
_circuit_breaker = DuckDuckGoCircuitBreaker()


def set_circuit_breaker(cb: DuckDuckGoCircuitBreaker) -> None:
  """Inject a run-scoped circuit breaker instance."""
  global _circuit_breaker
  _circuit_breaker = cb


@with_retry()
def _raw_ddg_search(query: str, max_results: int = 5) -> list[dict]:
  """Internal: call DDG and return raw result dicts."""
  with DDGS() as ddgs:
    results = list(ddgs.text(query, max_results=max_results))
  return results


def duckduckgo_search(
  query: str,
  max_results: int = 5,
  tool_errors: list[ToolError] | None = None,
) -> list[EvidenceItem]:
  """Search DuckDuckGo.  Returns list[EvidenceItem].

  If the circuit breaker is open, returns [] immediately and appends a
  ``circuit_open`` entry to ``tool_errors`` (if provided).
  """
  if _circuit_breaker.is_open:
    if tool_errors is not None:
      tool_errors.append(
        ToolError(
          tool="duckduckgo_search",
          error_type="circuit_open",
          timestamp=datetime.now(timezone.utc).isoformat(),
          query=query,
        )
      )
    return []

  raw = _raw_ddg_search(query, max_results)

  if raw is None or (isinstance(raw, list) and len(raw) == 0):
    # _raw_ddg_search returned [] after exhausting retries — record failure.
    _circuit_breaker.record_failure()
    return []

  items: list[EvidenceItem] = []
  for r in raw:
    items.append(
      EvidenceItem(
        source="duckduckgo",
        title=r.get("title", ""),
        url=r.get("href", r.get("link", "")),
        pmid=None,
        snippet=(r.get("body", r.get("snippet", "")))[:300],
        is_relevant=False,  # tagged by RESEARCH LLM later
        contradicts_harm=False,
      )
    )
  return items
