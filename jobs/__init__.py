"""Background jobs package (lifecycle and velocity monitors)."""

import logging
import sys
from pathlib import Path

_log = logging.getLogger("jobs")
if not _log.handlers:
  _log.setLevel(logging.INFO)
  _log.propagate = False
  _fmt = logging.Formatter("%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
  for _h in [logging.FileHandler(Path(__file__).parent / "jobs.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)]:
    _h.setFormatter(_fmt)
    _log.addHandler(_h)
