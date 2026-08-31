"""Mathematical clustering utilities (SBERT -> UMAP -> HDBSCAN and centroid math)."""

import logging
import numpy as np
import torch
import hdbscan
import umap
from sentence_transformers import SentenceTransformer

from layers.shared.embedding import l2_normalize

logger = logging.getLogger(__name__)

# Tunable parameters
MIN_CLUSTER_SIZE = 3 # Min posts for a valid cluster
MIN_SAMPLES = 2 # HDBSCAN noise tolerance (lower = looser)
UMAP_N_COMPONENTS = 8 # Target dimensions for UMAP reduction
UMAP_N_NEIGHBORS = 10 # UMAP local neighborhood size
UMAP_MIN_DIST = 0.0 # Forces dense packing in UMAP
CENTROID_MARGIN = 0.05 # Margin for misclassification check
MERGE_SIMILARITY_THRESHOLD = 0.98 # Cosine similarity to merge clusters
EW_SIMILARITY_THRESHOLD = 0.80 # Cosine similarity for early warnings

def cluster_posts(
  posts: list[dict],
  sbert_model: SentenceTransformer,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
  """Run SBERT → UMAP → HDBSCAN.

  Returns:
    embeddings: (N, 384) original SBERT embeddings
    umap_embeddings: (N, 5) UMAP-reduced embeddings
    labels: (N,) HDBSCAN cluster labels (-1 = noise)
  """
  texts = [(p.get("caption_text") or "").strip() for p in posts]
  torch.manual_seed(42)
  embeddings = sbert_model.encode(
    texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=32, show_progress_bar=False
  )

  n_samples = len(texts)
  effective_neighbors = min(UMAP_N_NEIGHBORS, n_samples - 1)
  if effective_neighbors < 2 or n_samples <= UMAP_N_COMPONENTS:
    umap_embeddings = embeddings
  else:
    reducer = umap.UMAP(
      n_components=UMAP_N_COMPONENTS,
      n_neighbors=effective_neighbors,
      min_dist=UMAP_MIN_DIST,
      metric="cosine",
      random_state=42,
      init="spectral" if effective_neighbors > UMAP_N_COMPONENTS else "random",
    )
    umap_embeddings = reducer.fit_transform(embeddings)

  clusterer = hdbscan.HDBSCAN(
    min_cluster_size=MIN_CLUSTER_SIZE,
    min_samples=MIN_SAMPLES,
    cluster_selection_method="eom",
    metric="euclidean",
    core_dist_n_jobs=1,
  )
  labels = clusterer.fit_predict(umap_embeddings)

  return embeddings, umap_embeddings, labels


def compute_centroids(
  embeddings: np.ndarray,
  labels: np.ndarray,
) -> dict[int, np.ndarray]:
  """Compute centroid (mean embedding) per cluster in original 384d space."""
  centroids: dict[int, np.ndarray] = {}
  unique_labels = set(labels)
  unique_labels.discard(-1)  # skip noise
  for lbl in unique_labels:
    mask = labels == lbl
    centroids[lbl] = l2_normalize(embeddings[mask].mean(axis=0))
  return centroids


def misclassification_check(
  embeddings: np.ndarray,
  labels: np.ndarray,
  centroids: dict[int, np.ndarray],
) -> np.ndarray:
  """Relocate posts closer to another cluster's centroid by > margin.

  Returns updated labels array (modifies in-place too).
  """
  if len(centroids) < 2:
    return labels

  centroid_ids = np.array(sorted(centroids.keys()))
  centroid_matrix = np.array([centroids[c] for c in centroid_ids])

  norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
  norms[norms == 0] = 1.0
  normed_embeddings = embeddings / norms

  sims = normed_embeddings @ centroid_matrix.T  # (N, K) cosine similarities

  for i in range(len(embeddings)):
    if labels[i] == -1:
      continue

    own_idx = np.searchsorted(centroid_ids, labels[i])
    own_sim = sims[i, own_idx]

    sims[i, own_idx] = -np.inf
    best_other_idx = np.argmax(sims[i])
    best_other_sim = sims[i, best_other_idx]

    if best_other_sim > own_sim + CENTROID_MARGIN:
      old_label = labels[i]
      new_label = centroid_ids[best_other_idx]
      labels[i] = new_label
      logger.debug(
        "Relocated post %d: cluster %d → %d (own=%.3f, other=%.3f)",
        i, old_label, new_label, own_sim, best_other_sim,
      )

  return labels


def merge_similar_clusters(
  embeddings: np.ndarray,
  labels: np.ndarray,
  centroids: dict[int, np.ndarray],
  threshold: float = MERGE_SIMILARITY_THRESHOLD,
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
  """Merge clusters whose centroids have cosine similarity > threshold."""
  if len(centroids) < 2:
    return labels, centroids

  labels = labels.copy()
  centroids = dict(centroids)  # mutable copy

  merged = True
  while merged:
    merged = False
    cluster_ids = sorted(centroids.keys())
    if len(cluster_ids) < 2:
      break

    centroid_matrix = np.array([centroids[c] for c in cluster_ids])
    sim_matrix = centroid_matrix @ centroid_matrix.T
    sim_matrix[np.tril_indices_from(sim_matrix)] = -np.inf

    best_idx = np.unravel_index(np.argmax(sim_matrix), sim_matrix.shape)
    best_sim = sim_matrix[best_idx]

    if best_sim >= threshold:
      id_a = cluster_ids[best_idx[0]]
      id_b = cluster_ids[best_idx[1]]

      count_a = int(np.sum(labels == id_a))
      count_b = int(np.sum(labels == id_b))
      keep, drop = (id_a, id_b) if count_a >= count_b else (id_b, id_a)

      labels[labels == drop] = keep
      del centroids[drop]
      
      mask = labels == keep
      centroids[keep] = l2_normalize(embeddings[mask].mean(axis=0))

      logger.info(
        "Merged cluster %d into %d (sim=%.3f, new_size=%d)",
        drop, keep, best_sim, int(np.sum(mask)),
      )
      merged = True

  return labels, centroids


def group_by_similarity(
  vectors: np.ndarray, 
  threshold: float = EW_SIMILARITY_THRESHOLD
) -> list[list[int]]:
  """Greedy grouping of L2-normalized vectors: each vector joins the first group whose seed it resembles."""
  groups: list[list[int]] = []
  seeds: list[np.ndarray] = []
  for idx in range(len(vectors)):
    v = vectors[idx]
    for g_idx, seed in enumerate(seeds):
      if float(seed @ v) >= threshold:
        groups[g_idx].append(idx)
        break
    else:
      groups.append([idx])
      seeds.append(v)
  return groups
