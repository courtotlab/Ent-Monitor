"""Velocity tracking worker - runs on a schedule (e.g. every 30 min via cron).

Picks up trends where velocity_next_check_at <= NOW() and:
1. Fetches all posts in the last 12h in a SINGLE query
2. Buckets them into 0-3h, 3-6h, 6-12h windows in Python
3. Computes velocity_growth_rate = (recent_rate - historical_rate) / historical_rate
4. Evaluates lifecycle transitions:
   - velocity > 0 sustained → Growth
   - velocity dropping 3+ consecutive checks → Declining
   - stable near-zero, still trickling → Latent
   - gap > 14 days then new posts → Resurfacing (handled in merge, not here)
5. Schedules next check (3h for active bursts, 24h for stable trends)
6. Logs lifecycle_change events in trend_lifecycle_history

Usage:
  uv run python jobs/velocity_worker.py
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add the root directory to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from layers.analysis.db.queries import (
  fetch_trends_due_for_velocity,
  fetch_posts_last_12h,
  update_trend_velocity,
)


# Thresholds for lifecycle transitions
GROWTH_RATE_THRESHOLD = 0.2       # +20% → Growth
DECLINING_RATE_THRESHOLD = -0.15  # -15% → Declining candidate
LATENT_MAX_RATE = 1.0             # <=1 post/hour sustained → Latent candidate


def compute_velocity(post_timestamps: list[datetime]) -> dict:
  """Bucket posts into 0-3h, 3-6h, 6-12h windows and compute velocity.

  Returns:
    rate_0_3h: posts/hour in last 3 hours
    rate_3_6h: posts/hour in 3-6h window
    rate_6_12h: posts/hour in 6-12h window
    growth_rate: (recent - historical) / historical
    total_12h: total posts in 12h
  """
  now = datetime.now(UTC)

  posts_0_3h = [t for t in post_timestamps if (now - t) <= timedelta(hours=3)]
  posts_3_6h = [t for t in post_timestamps if timedelta(hours=3) < (now - t) <= timedelta(hours=6)]
  posts_6_12h = [t for t in post_timestamps if timedelta(hours=6) < (now - t) <= timedelta(hours=12)]

  rate_0_3h = len(posts_0_3h) / 3.0    # posts/hour
  rate_3_6h = len(posts_3_6h) / 3.0
  rate_6_12h = len(posts_6_12h) / 6.0

  # Growth rate: compare recent (0-3h) vs historical (6-12h)
  # Fall back to 3-6h if 6-12h is empty
  historical_rate = rate_6_12h if rate_6_12h > 0 else rate_3_6h

  if historical_rate > 0:
    growth_rate = (rate_0_3h - historical_rate) / historical_rate
  else:
    growth_rate = rate_0_3h  # no baseline - raw rate is the signal

  return {
    "rate_0_3h": rate_0_3h,
    "rate_3_6h": rate_3_6h,
    "rate_6_12h": rate_6_12h,
    "growth_rate": growth_rate,
    "total_12h": len(post_timestamps),
  }


def decide_lifecycle_transition(
  current_lifecycle: str,
  growth_rate: float,
  prev_growth_rate: float | None,
  total_12h: int,
  rate_0_3h: float,
) -> str | None:
  """Decide if a lifecycle transition should occur based on velocity data.

  Returns the new lifecycle stage, or None if no transition.
  """
  # Don't touch Resurfacing - that's handled by the merge path
  if current_lifecycle == "Resurfacing":
    # After resurfacing, evaluate normally on next check
    if growth_rate > GROWTH_RATE_THRESHOLD:
      return "Growth"
    return None

  # Insufficient signal → can only transition if we now have enough data
  if current_lifecycle == "Insufficient signal":
    if total_12h >= 5 and growth_rate > 0:
      return "Emergence"
    return None

  # Emergence → Growth (sustained positive velocity)
  if current_lifecycle == "Emergence":
    if growth_rate > GROWTH_RATE_THRESHOLD:
      return "Growth"
    if total_12h == 0 and rate_0_3h == 0:
      return "Declining"
    return None

  # Growth → Declining (velocity dropping)
  if current_lifecycle == "Growth":
    if growth_rate < DECLINING_RATE_THRESHOLD:
      # Check if prev was also declining (need 3+ consecutive for Declining)
      if prev_growth_rate is not None and prev_growth_rate < DECLINING_RATE_THRESHOLD:
        return "Declining"
    return None

  # Declining → Latent (low but stable)
  if current_lifecycle == "Declining":
    if 0 < rate_0_3h <= LATENT_MAX_RATE and abs(growth_rate) < 0.1:
      return "Latent"
    if rate_0_3h == 0 and total_12h == 0:
      # Still declining, no transition yet - keep checking
      return None
    if growth_rate > GROWTH_RATE_THRESHOLD:
      return "Growth"  # recovery
    return None

  # Latent → Growth (if it picks up again) or stay Latent
  if current_lifecycle == "Latent":
    if growth_rate > GROWTH_RATE_THRESHOLD and rate_0_3h > LATENT_MAX_RATE:
      return "Growth"
    return None

  return None


def run_velocity_checks() -> int:
  """Run velocity checks for all due trends. Returns number of trends processed."""
  trends = fetch_trends_due_for_velocity()
  if not trends:
    # print("No trends due for velocity check")
    return 0

  # print(f"Processing {len(trends)} trends for velocity check")
  processed = 0

  for trend in trends:
    trend_id = trend["trend_id"]
    current_lifecycle = trend["lifecycle_status"]
    prev_growth_rate = trend["prev_growth_rate"]

    # Single read: all posts in 12h window
    timestamps = fetch_posts_last_12h(trend_id)
    velocity = compute_velocity(timestamps)

    growth_rate = velocity["growth_rate"]
    new_lifecycle = decide_lifecycle_transition(
      current_lifecycle=current_lifecycle,
      growth_rate=growth_rate,
      prev_growth_rate=prev_growth_rate,
      total_12h=velocity["total_12h"],
      rate_0_3h=velocity["rate_0_3h"],
    )

    # Schedule next check: 3h if actively bursting, 24h if stable
    if velocity["rate_0_3h"] > 2.0:  # >2 posts/hour → check again in 3h
      next_check_hours = 3
    elif velocity["total_12h"] > 0:  # some activity → check in 6h
      next_check_hours = 6
    else:  # dormant → check in 24h
      next_check_hours = 24

    update_trend_velocity(
      trend_id=trend_id,
      growth_rate=growth_rate,
      new_lifecycle=new_lifecycle,
      next_check_hours=next_check_hours,
    )

    # status_msg = f"→ {new_lifecycle}" if new_lifecycle else "(no change)"
    # print(f"Velocity: {trend_id} | rate={velocity['rate_0_3h']:.2f}/h | growth={growth_rate:.2f} | lifecycle={current_lifecycle} {status_msg} | next check in {next_check_hours}h")
    processed += 1

  return processed


if __name__ == "__main__":
  count = run_velocity_checks()
  print(f"\nVelocity worker completed. Processed {count} trends.")
