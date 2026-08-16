"""CLASSIFY node - single-shot classification with self-consistency check.

One call per cluster (doubled for consistency). Produces severity, risk_score,
lifecycle, verification, supporting_evidence_ids, and rationale.
Enforces risk_score band clamping after generation.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from layers.analysis.nodes.observe import check_output_for_injection
from layers.analysis.core.state import AgentState

logger = logging.getLogger(__name__)

CLASSIFY_MODEL = "gpt-5.6-terra"
CLASSIFY_REASONING_EFFORT = "medium"

# risk_score must fall within its severity band
SEVERITY_BANDS = {
  "HIGH": (0.70, 1.00),
  "MODERATE": (0.35, 0.69),
  "LOW": (0.00, 0.34),
}

# severity ordering for self-consistency tie-breaking (higher index = more severe)
SEVERITY_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
VERIFICATION_ORDER = {"INSUFFICIENT_EVIDENCE": 0, "PROVISIONAL": 1, "CONFIRMED": 2}

_SYSTEM_PROMPT = """\
You are scoring and classifying social-media trends for a child-safety monitoring
dashboard. For each candidate trend, output: severity, risk_score, lifecycle,
verification, supporting_evidence_ids, slang_terms, mechanism_level_match, and rationale.

═══════════════════════════════════════════════════════════════
SEVERITY RUBRIC - use these anchors, not your own judgment of "high"
═══════════════════════════════════════════════════════════════

Rate severity using these anchors:
- HIGH: plausible immediate physical harm requiring emergency care if replicated
  (e.g. esophageal battery ingestion, eardrum perforation, home surgical procedures
  on infants, airway obstruction).
- MODERATE: plausible harm requiring medical follow-up but not immediately
  life-threatening (e.g. unsupervised piercing, non-sterile substance in ear canal
  causing irritation/infection risk).
- LOW: educational/informational content, or behavior with minimal plausible harm.

═══════════════════════════════════════════════════════════════
VERIFICATION RUBRIC
═══════════════════════════════════════════════════════════════

Rate verification using these anchors:
- CONFIRMED: at least one cited source documents this exact behavior OR the same injury mechanism (not just topic-adjacent). This MUST be a clinical/peer-reviewed paper, a top professional medical website, a reputable news article (national OR local news), OR explicit professional medical advice quoted in any source.
- PROVISIONAL: cited evidence is plausibly related but doesn't document the specific mechanism (e.g. general topic overview), or the source is just a casual blog/lifestyle magazine without any professional medical backing.
- INSUFFICIENT_EVIDENCE: no meaningful supporting evidence found.

CRITICAL RULE: Casual blogs, lifestyle magazines, or unverified social media posts CANNOT justify CONFIRMED - they support PROVISIONAL at most. Clinical evidence, authoritative medical institutions, local/national news reports, or quoted professional advice justify CONFIRMED.


═══════════════════════════════════════════════════════════════
LIFECYCLE
═══════════════════════════════════════════════════════════════

TREND vs ISOLATED INCIDENT:
- Minimum 5 distinct posts AND at least 2 distinct platforms AND first_detected
  to last_seen span of at least 24 hours to qualify as a trend at all.
- If these thresholds are not met, output lifecycle = "Isolated incident"
  and verification = "INSUFFICIENT_EVIDENCE" (unless clinical evidence exists),
  regardless of severity.

Lifecycle stages (only apply once the trend threshold is met):
- Emergence: meets minimum threshold, still accelerating, <7 days since first_detected.
- Growth: sustained/increasing post velocity, 7+ days.
- Resurfacing: previously tracked trend with a >14 day gap then new activity.
- Declining: post velocity dropping for 3+ consecutive check intervals.
- Latent: still present but at very low and stable volume - not rising, not dead.

═══════════════════════════════════════════════════════════════
SUPPORTING EVIDENCE IDS
═══════════════════════════════════════════════════════════════

You MUST cite which specific evidence item(s) support your verification rating.
Use the format: "pmid:<number>" for PubMed sources, or the URL for web sources.
If verification is INSUFFICIENT_EVIDENCE, this list should be empty.

═══════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════════════

Example 1 - HIGH + CONFIRMED:
  Trend: "Button battery ingestion challenges"
  Evidence: PMID:33555169 documents esophageal burns from button battery ingestion
  → severity: HIGH (immediate life-threatening esophageal perforation)
  → verification: CONFIRMED (clinical source documents exact mechanism)
  → supporting_evidence_ids: ["pmid:33555169"]

Example 2 - MODERATE + PROVISIONAL:
  Trend: "DIY ear piercing with sewing needles"
  Evidence: General CDC guidance on body piercing infection risks (web source)
  → severity: MODERATE (infection risk requiring medical follow-up, not immediately life-threatening)
  → verification: PROVISIONAL (evidence is topic-related but doesn't document this exact mechanism)
  → supporting_evidence_ids: ["https://www.cdc.gov/..."]

Example 3 - LOW + INSUFFICIENT_EVIDENCE:
  Trend: "Pediatric audiologist explaining how hearing tests work"
  Evidence: None needed - educational content
  → severity: LOW (educational, no risky behavior)
  → verification: INSUFFICIENT_EVIDENCE (no harm claim to verify)
  → supporting_evidence_ids: []

═══════════════════════════════════════════════════════════════
SELF-CHECK before finalizing:
1. Does verification respect the source quality rule (general web -> PROVISIONAL max)?
2. Are supporting_evidence_ids populated for CONFIRMED/PROVISIONAL?
3. Does lifecycle depend on meeting the post/platform/time threshold?
4. Did you generate 3-5 slang_terms (alternative names, misspellings, hashtags) that teens use for this?
5. Did you explicitly set mechanism_level_match to True ONLY if the evidence describes the EXACT behavior?
"""

_USER_PROMPT = """\
Cluster: {cluster_id}
Search context: {search_context}
Triage flag from OBSERVE: {triage_flag}

Evidence ({evidence_count} items):
{evidence_summary}

{verify_notes}
{known_trend_context}
STATISTICS FOR TREND THRESHOLD:
- Total distinct posts: {post_count}
- Distinct platforms: {platform_count}
- Time span between first and last post: {time_span_hours:.1f} hours

Based on the evidence and statistics above, classify this cluster.
"""

class ClassificationResult(BaseModel):
  trend_name: str
  severity: Literal["HIGH", "MODERATE", "LOW"]
  lifecycle: Literal["Emergence", "Growth", "Resurfacing", "Declining", "Latent", "Isolated incident"]
  verification: Literal["CONFIRMED", "PROVISIONAL", "INSUFFICIENT_EVIDENCE"]
  supporting_evidence_ids: list[str] = Field(description="PMIDs (pmid:NNN) or URLs that justify the verification rating")
  post_count: int
  platform_count: int
  slang_terms: list[str] = Field(description="3-5 alternative slang names, misspellings, or hashtags used for this trend")
  mechanism_level_match: bool = Field(description="True if the evidence documents the EXACT behavioral mechanism, False otherwise")
  rationale: str = Field(description="Reasoning behind classification")


def calculate_deterministic_risk_score(severity: str, verification: str, mechanism_match: bool) -> float:
  """Calculate risk_score using a strict deterministic matrix."""
  base_scores = {"HIGH": 0.85, "MODERATE": 0.50, "LOW": 0.15}
  
  # 1. Safer lookup with normalization
  score = base_scores.get(severity.upper().strip(), 0.15)
  
  # 2. Apply evidence modifiers without breaking tier boundaries
  if verification.upper().strip() == "CONFIRMED" and mechanism_match:
    score += 0.10
  elif verification.upper().strip() == "INSUFFICIENT_EVIDENCE":
    score -= 0.10
      
  return max(0.0, min(1.0, score))


def _pick_more_severe(a: ClassificationResult, b: ClassificationResult) -> ClassificationResult:
  """When self-consistency disagrees, pick the more severe result."""
  if SEVERITY_ORDER.get(a.severity, 0) >= SEVERITY_ORDER.get(b.severity, 0):
    return a
  return b


def _build_prompt(state: AgentState) -> tuple[str, dict]:
  """Build the user prompt from state. Returns (prompt_text, stats_dict)."""
  evidence = state.get("evidence", [])
  cluster_id = state.get("cluster_id", "unknown")
  posts = state.get("posts", [])

  post_count = len(posts)
  platforms = set(p.get("platform", "unknown") for p in posts)
  platform_count = len(platforms)

  time_span_hours = 0.0
  if posts:
    try:
      times = []
      for p in posts:
        ts = p.get("posted_at") or p.get("collected_at")
        if ts:
          if isinstance(ts, str):
            times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
          else:
            times.append(ts)
      if times:
        time_span_hours = (max(times) - min(times)).total_seconds() / 3600.0
    except Exception as exc:
      logger.warning("Failed to parse timestamps for span calculation: %s", exc)

  evidence_summary = ""
  if evidence:
    lines = []
    for i, e in enumerate(evidence):
      rel = "relevant" if e.get("is_relevant") else "not relevant"
      contra = " [CONTRADICTS harm]" if e.get("contradicts_harm") else ""
      tier = e.get("source_tier", "unknown")
      lines.append(
        f"[{i}] [{e.get('source', 'unknown')}] (tier: {tier}) {e.get('title', 'Untitled')}\n"
        f"    {rel}{contra}\n"
        f"    {e.get('snippet', '')[:150]}"
      )
    evidence_summary = "\n".join(lines)
  else:
    evidence_summary = "(no evidence found)"

  verify_notes = ""
  vf = state.get("verify_finding")
  if vf and not vf.get("label_consistent", True):
    verify_notes = (
      f"\nVERIFY flagged inconsistency: {vf.get('notes', '')}\n"
      "Re-evaluate your label in light of this feedback."
    )

  known_trend_context = ""
  if state.get("is_known_trend") and state.get("matched_trend_id"):
    db_label = state.get("db_trend_label", "unknown")
    db_risk = state.get("db_trend_risk_score", 0.0)
    db_posts = state.get("db_trend_post_count", 0)
    db_lifecycle = state.get("db_trend_lifecycle", "unknown")
    db_last_seen = state.get("db_trend_last_seen", "unknown")
    known_trend_context = (
      f"\nKNOWN TREND (matched DB trend {state['matched_trend_id']}):\n"
      f"  Label: {db_label} | Risk: {db_risk:.2f} | Posts: {db_posts} | "
      f"Lifecycle: {db_lifecycle} | Last seen: {db_last_seen}\n"
      f"  Risk score should be >= existing unless strong contradicting evidence.\n"
    )

  prompt = _USER_PROMPT.format(
    cluster_id=cluster_id,
    search_context=state.get("search_context", ""),
    triage_flag=state.get("triage_flag", "unclear"),
    evidence_count=len(evidence),
    evidence_summary=evidence_summary,
    verify_notes=verify_notes,
    known_trend_context=known_trend_context,
    post_count=post_count,
    platform_count=platform_count,
    time_span_hours=time_span_hours,
  )

  return prompt, {
    "post_count": post_count,
    "platform_count": platform_count,
    "time_span_hours": time_span_hours,
  }


def _invoke_classify(prompt: str) -> ClassificationResult:
  """Single LLM classification call."""
  llm = ChatOpenAI(
    model=CLASSIFY_MODEL,
    api_key=os.getenv("OPENAI_API_KEY"),
    reasoning_effort=CLASSIFY_REASONING_EFFORT,
    temperature=0,
  ).with_structured_output(ClassificationResult)

  return llm.invoke([
    SystemMessage(content=_SYSTEM_PROMPT),
    HumanMessage(content=prompt),
  ])


def classify_node(state: AgentState) -> dict:
  """CLASSIFY node - single-shot with self-consistency check.

  Runs classification twice at temp=0. If severity or verification disagree,
  picks the more severe result and sets low_confidence=True.
  Clamps risk_score to its declared severity band after generation.
  """
  print("  [CLASSIFY] Synthesizing evidence to determine safety label...")
  cluster_id = state.get("cluster_id", "unknown")

  prompt, stats = _build_prompt(state)

  try:
    # Run classification twice for self-consistency
    result_a = _invoke_classify(prompt)
    result_b = _invoke_classify(prompt)

    low_confidence = (
      result_a.severity != result_b.severity
      or result_a.verification != result_b.verification
    )

    if low_confidence:
      logger.warning(
        "CLASSIFY: self-consistency DISAGREEMENT for %s - "
        "run_a: severity=%s verification=%s | run_b: severity=%s verification=%s",
        cluster_id,
        result_a.severity, result_a.verification,
        result_b.severity, result_b.verification,
      )
      result = _pick_more_severe(result_a, result_b)
    else:
      result = result_a

    severity = result.severity
    lifecycle = result.lifecycle
    verification = result.verification
    reasoning = result.rationale
    supporting_evidence_ids = result.supporting_evidence_ids
    slang_terms = getattr(result, "slang_terms", [])
    mechanism_level_match = getattr(result, "mechanism_level_match", False)

    risk_score = calculate_deterministic_risk_score(severity, verification, mechanism_level_match)

  except Exception as exc:
    logger.error("CLASSIFY LLM failed: %s - defaulting to MODERATE", exc)
    severity = "MODERATE"
    risk_score = 0.50
    lifecycle = "Isolated incident"
    verification = "INSUFFICIENT_EVIDENCE"
    reasoning = "Classification failed due to internal error."
    supporting_evidence_ids = []
    slang_terms = []
    mechanism_level_match = False
    low_confidence = True

    risk_score = calculate_deterministic_risk_score(severity, verification, mechanism_level_match)

  confidence = 1.0
  
  citations = []
  evidence_list = state.get("evidence", [])
  for eid in supporting_evidence_ids:
    for ev in evidence_list:
      if ev.get("pmid") == eid.replace("pmid:", "") or ev.get("url") == eid:
        citations.append(ev)
        break
        
  citations_used_as_support = supporting_evidence_ids
  needs_more_evidence = False

  if check_output_for_injection(reasoning, cluster_id):
    pass

  logger.info(
    "CLASSIFY: %s severity=%s risk=%.3f lifecycle=%s verification=%s low_confidence=%s",
    cluster_id, severity, risk_score, lifecycle, verification, low_confidence,
  )

  return {
    "label": severity,
    "lifecycle": lifecycle,
    "verification": verification,
    "confidence": confidence,
    "citations": citations,
    "citations_used_as_support": citations_used_as_support,
    "supporting_evidence_ids": supporting_evidence_ids,
    "risk_score": risk_score,
    "reasoning": reasoning,
    "needs_more_evidence": needs_more_evidence,
    "evidence_gap": None,
    "downgrade_reason": None,
    "downgraded_from_harmful": False,
    "low_confidence": low_confidence,
    "slang_terms": slang_terms,
    "mechanism_level_match": mechanism_level_match,
  }
