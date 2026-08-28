"""Shared retry infrastructure for Layer 3 search tools.

Contains:
- PMIDNotFoundError       - domain exception for confirmed-absent PMIDs
- @with_retry decorator   - exponential backoff, parameterized empty return
- DuckDuckGoCircuitBreaker - run-level singleton, opens after 3 failures
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


#  Domain exception: confirmed-absent PMID
class PMIDNotFoundError(Exception):
  """Raised when NCBI cleanly confirms a PMID does not exist.

  Non-retriable and NOT caught by @with_retry - must propagate so
  VERIFY can distinguish 'confirmed absent' from 'tool failed'.
  """
  pass


#  Retry decorator
def with_retry(
  max_attempts: int = 3,
  backoff: float = 1.0,
  empty_return: Callable = list,
):
  """Decorator: retry on transient errors, return ``empty_return()`` when exhausted.

  - ``PMIDNotFoundError`` is never caught - it propagates as a real signal.
  - Transient/generic errors are retried with exponential backoff.
  - Fails and returns empty when max_attempts is exhausted.
  """

  def decorator(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
      for attempt in range(max_attempts):
        try:
          return fn(*args, **kwargs)
        except PMIDNotFoundError:
          raise  # never retry, never swallow
        except Exception as exc:
          if attempt == max_attempts - 1:
            logger.warning("[TOOL] %s exhausted retries: %s", fn.__name__, exc)
            return empty_return()
          time.sleep(backoff * (2**attempt))

    return wrapper

  return decorator


#  DuckDuckGo circuit breaker (run-level singleton)
class DuckDuckGoCircuitBreaker:
  """Opens after ``threshold`` failures in one run; skips DDG for the remainder.

  Thread-safe - uses a lock for the counter.  Instantiated once per run
  in the orchestration loop, *not* stored in AgentState (persists across
  clusters within the same run, resets between runs).
  """

  def __init__(self, threshold: int = 3):
    self._threshold = threshold
    self._failures = 0
    self._open = False
    self._lock = threading.Lock()

  @property
  def is_open(self) -> bool:
    return self._open

  def record_failure(self) -> None:
    with self._lock:
      self._failures += 1
      if self._failures == self._threshold:
        self._open = True
        logger.warning(
          "[CIRCUIT] DuckDuckGo circuit breaker OPEN after %d failures - "
          "skipping DDG for remainder of run",
          self._failures,
        )
