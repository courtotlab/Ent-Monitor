import json
import numpy as np


def serialize(embedding) -> str:
  """Serialize a numpy array or list embedding to a JSON string for DB storage."""
  if isinstance(embedding, np.ndarray):
    embedding = embedding.tolist()
  return json.dumps(embedding)


def deserialize(embedding) -> list[float]:
  """Deserialize a JSON string or pgvector string from DB into a list of floats."""
  if not embedding:
    return []
  if isinstance(embedding, list):
    return [float(x) for x in embedding]
  text = str(embedding).strip("[]")
  return [float(x) for x in text.split(",") if x.strip()]
