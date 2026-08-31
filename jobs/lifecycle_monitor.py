"""
jobs/lifecycle_monitor.py
─────────────────────────
Scans all active trends and transitions stale ones through two lifecycle stages:

  - Declining : no new posts linked to the trend in the last 14 days
  - Latent    : already Declining AND no new posts in the last 21 days

A trend can only move Declining → Latent (never jump straight from active to Latent).
This job is designed to run once a day via crontab.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from layers.shared.db import get_connection

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s | %(name)-36s | %(levelname)-7s | %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Tunables
DECLINING_THRESHOLD_DAYS = 14   # No new posts in 14 days → Declining
LATENT_THRESHOLD_DAYS    = 21   # Already Declining + no new posts in 21 days → Latent
# ──────────────────────────────────────────────

# Only real growing trends can go Declining — they had a rise so they can fade
DECLINABLE_STATUSES = ("Emergence", "Growth", "Resurfacing")

# Isolated incidents never rose, so they skip Declining and go straight to Latent
ISOLATED_STATUS  = "Isolated incident"

DECLINING_STATUS = "Declining"
LATENT_STATUS    = "Latent"


def fetch_candidate_trends() -> list[dict]:
  """Fetch all trends that are still in an active or Declining state."""
  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        SELECT trend_id, trend_name, lifecycle_status, last_seen_at, lifecycle_history
        FROM trends
        WHERE lifecycle_status NOT IN ('Latent')
        ORDER BY last_seen_at ASC NULLS FIRST
      """
    )
    rows = cur.fetchall()
    return [
      {
        "trend_id":         r[0],
        "trend_name":       r[1],
        "lifecycle_status": r[2],
        "last_seen_at":     r[3],
        "lifecycle_history": r[4] or [],
      }
      for r in rows
    ]


def update_lifecycle(trend_id: str, new_status: str, history: list) -> None:
  """Write the new lifecycle status and append to lifecycle_history."""
  import json
  now = datetime.now(UTC)
  history_entry = {"date": now.isoformat(), "status": new_status}
  history.append(history_entry)

  with get_connection() as conn, conn.cursor() as cur:
    cur.execute(
      """
        UPDATE trends
        SET lifecycle_status = %s,
            lifecycle_history = %s::jsonb
        WHERE trend_id = %s
      """,
      (new_status, json.dumps(history), trend_id),
    )
    conn.commit()


def days_since(ts) -> float:
  """Return how many days ago a timestamp was (UTC-aware)."""
  if ts is None:
    return float("inf")
  if ts.tzinfo is None:
    ts = ts.replace(tzinfo=UTC)
  return (datetime.now(UTC) - ts).total_seconds() / 86400.0


def run_lifecycle_monitor() -> None:
  trends = fetch_candidate_trends()
  if not trends:
    logger.info("Lifecycle monitor: no active trends to evaluate.")
    return

  logger.info("Lifecycle monitor: evaluating %d trends...", len(trends))
  declining_count = 0
  latent_count    = 0

  for trend in trends:
    trend_id   = trend["trend_id"]
    name       = trend["trend_name"] or trend_id
    status     = trend["lifecycle_status"]
    last_seen  = trend["last_seen_at"]
    history    = trend["lifecycle_history"]
    silence    = days_since(last_seen)

    if status == DECLINING_STATUS:
      # Already Declining — promote to Latent if silence exceeds 21 days
      if silence >= LATENT_THRESHOLD_DAYS:
        logger.info(
          "Trend '%s' [%s]: %.1f days silent → Latent", name, trend_id, silence
        )
        update_lifecycle(trend_id, LATENT_STATUS, history)
        latent_count += 1
      else:
        logger.debug(
          "Trend '%s' [%s]: %.1f days silent (still Declining)",
          name, trend_id, silence
        )

    elif status in DECLINABLE_STATUSES:
      # Real trend (Emergence/Growth/Resurfacing) — mark Declining if silent for 14 days
      if silence >= DECLINING_THRESHOLD_DAYS:
        logger.info(
          "Trend '%s' [%s]: %.1f days silent → Declining", name, trend_id, silence
        )
        update_lifecycle(trend_id, DECLINING_STATUS, history)
        declining_count += 1
      else:
        logger.debug(
          "Trend '%s' [%s]: %.1f days silent (still active)", name, trend_id, silence
        )

    elif status == ISOLATED_STATUS:
      # Isolated incidents never grew, so skip Declining entirely — go straight to Latent
      if silence >= LATENT_THRESHOLD_DAYS:
        logger.info(
          "Trend '%s' [%s]: Isolated incident, %.1f days silent → Latent (no Declining stage)",
          name, trend_id, silence
        )
        update_lifecycle(trend_id, LATENT_STATUS, history)
        latent_count += 1
      else:
        logger.debug(
          "Trend '%s' [%s]: Isolated incident, %.1f days silent (not yet Latent)",
          name, trend_id, silence
        )

  logger.info(
    "Lifecycle monitor done. Marked %d Declining, %d Latent.",
    declining_count, latent_count,
  )


if __name__ == "__main__":
  run_lifecycle_monitor()
