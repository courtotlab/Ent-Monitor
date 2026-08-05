"""ASSESS node — deterministic evidence quality scorer.

No LLM.  Wraps compute_evidence_score() and route_after_assess() from routing.py.
This node exists purely to make the graph wiring clean — the actual logic
lives in routing.py.
"""

from __future__ import annotations

import logging

from layers.analysis.routing import compute_evidence_score, EVIDENCE_THRESHOLD
from layers.analysis.state import AgentState

logger = logging.getLogger(__name__)


def assess_node(state: AgentState) -> dict:
  """Compute evidence score and write it to state.

  The actual routing decision is made by route_after_assess() which is
  wired as a separate router node in graph.py.
  """
  score = compute_evidence_score(state)
  print(f"  [ASSESS] Evidence quality score: {score:.2f}/1.00")
  logger.info(
    "ASSESS: evidence_score=%.3f (threshold=%.2f, retries_left=%d)",
    score,
    EVIDENCE_THRESHOLD,
    state.get("research_retries_left", 0),
  )
  return {"evidence_score": score}
