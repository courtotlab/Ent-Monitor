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


def l2_normalize(vector: np.ndarray) -> np.ndarray:
  """Normalize a 1D vector or 2D matrix of row-vectors to unit length (L2 norm)."""
  if vector.ndim == 1:
    norm = np.linalg.norm(vector)
    if norm > 0:
      return vector / norm
  else:
    # 2D case
    norms = np.linalg.norm(vector, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vector / norms
