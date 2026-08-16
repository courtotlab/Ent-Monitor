import json
import logging
from typing import Any

import numpy as np
from scipy.spatial.distance import cdist
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# PYDANTIC V2 SCHEMAS
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
You are a high-context consolidation supervisor for a social media monitoring pipeline.
Your task is to holistically review a batch of cluster summaries and merge clusters that represent IDENTICAL physical or behavioral actions.

CRITICAL RULES:
1. AGGRESSIVE MERGING ACROSS VOCABULARIES: You must aggressively merge clusters representing the same behavior even if one uses viral/social media slang (e.g., "3am flashlight tonsil check") and the other uses strict clinical terminology (e.g., "acute tonsillitis diagnostic screening").
2. POLYSEMY TRAPS: Strictly avoid merging based on shared ambiguous words if the underlying action differs. For example, if a cluster mentions "flashlight" for "night hiking", NEVER merge it with medical oral checks. 
3. BRIEF REASONING: Keep your reasoning very brief to minimize output tokens.

You will receive a JSON payload of clusters, each with a `cluster_id` and representative `samples`.
Output a structured list of merges where `source_cluster_id` merges into `target_cluster_id`.
"""

# ═══════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════

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
    
    longest_idx = max(remaining_indices, key=lambda idx: len(posts[idx].get("caption_text", "")))
    
    final_indices = [closest_idx_1, closest_idx_2, furthest_idx, longest_idx]
    
    return [posts[i].get("caption_text", "") for i in final_indices]


def execute_batch_cluster_merge(clusters: list[dict], llm_model: str = "gpt-4o-mini") -> list[dict]:
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
    prompt_text = payload.model_dump_json(indent=2)
    
    # Call LLM
    llm = ChatOpenAI(model=llm_model, temperature=0.0).with_structured_output(BatchMergeResponse)
    
    try:
        response: BatchMergeResponse = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt_text)
        ])
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
    merged_groups = {}
    for c in clusters:
        root = find(c["cluster_id"])
        if root not in merged_groups:
            merged_groups[root] = {
                "cluster_id": root,
                "posts": []
            }
        merged_groups[root]["posts"].extend(c["posts"])
        
    # Recalculate centroids and build final output
    final_clusters = []
    for root_id, group_data in merged_groups.items():
        all_posts = group_data["posts"]
        if all_posts:
            # Recalculate centroid using np.mean() on the aggregated embeddings
            all_embeddings = np.array([p["embedding"] for p in all_posts])
            new_centroid = np.mean(all_embeddings, axis=0)
            
            final_clusters.append({
                "cluster_id": root_id,
                "centroid": new_centroid,
                "posts": all_posts
            })
            
    logger.info(
        "Batch merge complete: reduced %d clusters to %d clusters",
        len(clusters), len(final_clusters)
    )
    return final_clusters
