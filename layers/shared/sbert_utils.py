import json
import numpy as np


def serialize(embedding) -> str:
  """Serialize a numpy array or list embedding to a JSON string for DB storage."""
  if isinstance(embedding, np.ndarray):
    embedding = embedding.tolist()
  return json.dumps(embedding)


def deserialize(embedding_str: str) -> list[float]:
  """Deserialize a JSON string from DB into a list of floats."""
  if not embedding_str:
    return []
  try:
    return json.loads(embedding_str)
  except Exception:
    # Fallback for old ast.literal_eval format if necessary
    import ast

    return ast.literal_eval(embedding_str)
