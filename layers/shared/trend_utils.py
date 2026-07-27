import hashlib
import re


def slugify(text: str) -> str:
  text = text.lower()
  text = re.sub(r"[^a-z0-9]+", "_", text)
  return text.strip("_")

def make_trend_id(trend_name: str) -> str:
  """Generate a consistent trend_id slug from a trend name."""
  slug = slugify(trend_name)[:30]
  hash_str = hashlib.sha256(trend_name.encode("utf-8")).hexdigest()[:6]
  return f"trend_{slug}_{hash_str}"
