from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
SBERT_THRESHOLD = 0.38


class SbertFilter:
  def __init__(self, model: SentenceTransformer | None = None):
    self.model = model or SentenceTransformer(MODEL_NAME)
    self._anchor_matrix: np.ndarray | None = None
    self._anchor_ids: list[int] = []

  def load_anchors(self, anchors: list[tuple[int, str, list[float]]]) -> None:
    """Load anchors as (anchor_id, anchor_text, embedding) triples."""
    if not anchors:
      raise ValueError(
        "No active SBERT anchors found in database. Run init/002_seed_anchors.py first."
      )
    self._anchor_ids = [anchor_id for anchor_id, _, _ in anchors]
    matrix = np.array([emb for _, _, emb in anchors], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    self._anchor_matrix = matrix / norms

  def score_texts(self, texts: list[str]) -> list[float]:
    if self._anchor_matrix is None:
      raise RuntimeError("Anchors not loaded. Call load_anchors() first.")

    if not texts:
      return []

    embeddings = self.model.encode(
      texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True
    )
    scores = embeddings @ self._anchor_matrix.T
    max_scores = np.max(scores, axis=1)

    return [float(score) for score in max_scores]

  def score_posts(self, posts: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float, int | None]]:
    """Score posts against anchors.

    Returns a list of (post, max_score, best_anchor_id) triples.
    best_anchor_id is None only if no anchors are loaded.
    """
    if self._anchor_matrix is None:
      raise RuntimeError("Anchors not loaded. Call load_anchors() first.")

    texts = [(post.get("caption_text") or "").strip() for post in posts]
    if not texts:
      return []

    embeddings = self.model.encode(
      texts, convert_to_numpy=True, normalize_embeddings=True
    )
    scores = embeddings @ self._anchor_matrix.T  # shape: (n_posts, n_anchors)
    max_indices = np.argmax(scores, axis=1)
    max_scores = scores[np.arange(len(posts)), max_indices]

    results = []
    for post, score, anchor_idx in zip(posts, max_scores, max_indices):
      best_anchor_id = self._anchor_ids[int(anchor_idx)] if self._anchor_ids else None
      results.append((post, float(score), best_anchor_id))

    return results

  @staticmethod
  def passes_threshold(score: float) -> bool:
    return score >= SBERT_THRESHOLD
