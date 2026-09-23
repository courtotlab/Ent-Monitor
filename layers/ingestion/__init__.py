"""Layer 1 - Ingestion (Social media scrapers, GDELT, Google Trends)."""

import logging
import sys
from pathlib import Path

_log = logging.getLogger("layers.ingestion")
if not _log.handlers:
  _log.setLevel(logging.INFO)
  _log.propagate = False
  _fmt = logging.Formatter("%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
  for _h in [logging.FileHandler(Path(__file__).parent / "ingestion.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)]:
    _h.setFormatter(_fmt)
    _log.addHandler(_h)
