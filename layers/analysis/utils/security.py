import logging

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
  "ignore previous",
  "ignore all",
  "system:",
  "assistant:",
  "new instructions",
  "disregard",
  "you are now",
]


def check_output_for_injection(text: str, cluster_id: str) -> bool:
  """Best-effort heuristic to catch lazy injections. Real defense is XML-escaping + system-prompt."""
  lower = text.lower()
  if any(p in lower for p in INJECTION_PATTERNS):
    logger.warning("[SECURITY] Possible injection in output for %s", cluster_id)
    return True
  return False
