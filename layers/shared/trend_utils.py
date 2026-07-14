import hashlib


def make_trend_id(prefix: str, identifier: str) -> str:
  """Generate a consistent trend_id slug from a prefix and an identifier (e.g. url)."""
  hash_str = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8]
  return f"{prefix}_{hash_str}"
