def get_engagement(post: dict, field: str, default: int = 0) -> int:
  """Read an engagement metric from either post['engagement'][field] or post[field]."""
  eng = post.get("engagement")
  if isinstance(eng, dict):
    val = eng.get(field)
    if val is not None:
      return int(val)
  # Fallback: flat key (e.g. from fetch_unprocessed_posts DB path)
  return int(post.get(field, default))
