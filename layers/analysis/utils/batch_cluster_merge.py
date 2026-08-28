import logging

import numpy as np
from collections import defaultdict
from langchain_core.messages import HumanMessage, SystemMessage
from layers.analysis.utils.llm import invoke_llm
from pydantic import BaseModel, Field
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)

# PYDANTIC V2 SCHEMAS

class ClusterMergeInstruction(BaseModel):
  source_cluster_id: int = Field(description="The ID of the cluster to be merged (will be deleted).")
  target_cluster_id: int = Field(description="The ID of the cluster to merge into (will be kept).")
  reasoning: str = Field(description="Brief reason for merge.")

class BatchMergeResponse(BaseModel):
  merges: list[ClusterMergeInstruction] = Field(description="List of cluster merges to perform.")

class ClusterSummary(BaseModel):
  cluster_id: int
  samples: list[str]

class BatchClusterPayload(BaseModel):
  clusters: list[ClusterSummary]

_SYSTEM_PROMPT = """\
You are a high-context consolidation supervisor for a social media monitoring pipeline.
Your task is to holistically review a batch of cluster summaries and merge clusters ONLY IF they represent the exact same behavioral action and intent.

CRITICAL RULES:
1. INTENT SEPARATION: Never merge clusters if their primary intent differs. For example, never merge a cluster of parents asking questions about ear infections with a cluster of medical professionals demonstrating earwax removal procedures.
2. POLYSEMY TRAPS: Strictly avoid merging based on shared ambiguous words if the underlying action differs.
3. ANATOMY AND CONDITION BOUNDARIES: Never merge clusters that involve different body parts (e.g., ears vs. mouth) or treat different underlying conditions (e.g., ear infection vs. tongue tie). Swallowing an object is completely different from inserting an object into the ear.
4. BRIEF REASONING: Keep your reasoning very brief to minimize output tokens.

You will receive a JSON payload of clusters, each with a `cluster_id` and representative `samples`.
Output a structured list of merges where `source_cluster_id` merges into `target_cluster_id`.
"""

# FUNCTIONS

def _sample_cluster_posts(centroid: np.ndarray, posts: list[dict]) -> list[str]:
  """
  Deterministic Local Sampling (0 Cost)
  Selects exactly 4 representative captions based on cosine distance from centroid:
  - 2 closest (The Pure Core Nucleus)
  - 1 furthest (The Cluster Edge Bound)
  - 1 longest by character length from remaining (The Semantic Variance Anchor)
  """
  if not posts:
    return []
  
  if len(posts) <= 4:
    return [p.get("caption_text", "") for p in posts]

  # Extract embeddings for distance calculation
  embeddings = np.array([p["embedding"] for p in posts])
  
  # Calculate cosine distance (1 - cosine_similarity). cdist expects 2D arrays.
  distances = cdist([centroid], embeddings, metric='cosine')[0]
  
  # Sort indices by distance (ascending)
  sorted_indices = np.argsort(distances)
  
  # 1. Core Nucleus: 2 closest
  closest_idx_1 = sorted_indices[0]
  closest_idx_2 = sorted_indices[1]
  
  # 2. Edge Bound: 1 absolute furthest
  furthest_idx = sorted_indices[-1]
  
  # 3. Semantic Variance Anchor: longest from remaining middle-tier
  selected_indices = {closest_idx_1, closest_idx_2, furthest_idx}
  remaining_indices = [i for i in range(len(posts)) if i not in selected_indices]
  
  captions = [p.get("caption_text", "") for p in posts]
  longest_idx = max(remaining_indices, key=lambda idx: len(captions[idx]))
  
  final_indices = [closest_idx_1, closest_idx_2, furthest_idx, longest_idx]
  
  return [captions[i] for i in final_indices]


def execute_batch_cluster_merge(clusters: list[dict], llm_model: str = "gpt-4.1-mini") -> list[dict]:
  """
  Executes a Batch Cluster Merge using an LLM to find semantic overlaps 
  missed by pure mathematical clustering.
  
  Args:
    clusters: List of dicts, each with keys 'cluster_id', 'centroid', 'posts'.
  Returns:
    Consolidated list of cluster dicts.
  """
  if len(clusters) < 2:
    return clusters

  # 1. Deterministic Local Sampling
  payload_clusters = []
  for c in clusters:
    samples = _sample_cluster_posts(c["centroid"], c["posts"])
    payload_clusters.append(ClusterSummary(cluster_id=c["cluster_id"], samples=samples))

  # 2. Ultra-Lean I/O Payload
  payload = BatchClusterPayload(clusters=payload_clusters)
  prompt_text = payload.model_dump_json()
  
  # Call LLM
  try:
    response: BatchMergeResponse = invoke_llm(
      model=llm_model,
      messages=[
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=prompt_text)
      ],
      schema=BatchMergeResponse,
    )
    merges = response.merges
  except Exception as e:
    logger.error("LLM batch merge failed: %s", e)
    return clusters

  # 3. In-Memory Cluster Graph Merge Execution (Union-Find)
  # parent dict maps cluster_id -> root cluster_id
  parent = {c["cluster_id"]: c["cluster_id"] for c in clusters}
  
  def find(i):
    if parent[i] == i:
      return i
    parent[i] = find(parent[i])
    return parent[i]
    
  def union(source, target):
    root_s = find(source)
    root_t = find(target)
    if root_s != root_t:
      # Merge source INTO target
      parent[root_s] = root_t
      
  for merge in merges:
    s = merge.source_cluster_id
    t = merge.target_cluster_id
    if s in parent and t in parent:
      union(s, t)
      
  # Group posts by their new root cluster
  merged_groups = defaultdict(list)
  for c in clusters:
    root = find(c["cluster_id"])
    merged_groups[root].extend(c["posts"])
    
  # Recalculate centroids and build final output
  final_clusters = []
  for root_id, posts in merged_groups.items():
    if not posts:
      continue
    centroid = np.mean([p["embedding"] for p in posts], axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
      centroid = centroid / norm
    final_clusters.append({
      "cluster_id": root_id,
      "centroid": centroid,
      "posts": posts
    })
      
  logger.info(
    "Batch merge complete: reduced %d clusters to %d clusters",
    len(clusters), len(final_clusters)
  )
  return final_clusters
