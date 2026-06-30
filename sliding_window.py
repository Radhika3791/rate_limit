"""
Sliding Window Rate Limiter
============================
Two implementations:

1. Log variant   — exact; stores a timestamp per request.
                   Memory: O(L) per client.

2. Counter variant — approximate; keeps two fixed-window buckets and
                     interpolates. Memory: O(1) per client.
                     Error < 0.003 % in practice.

Both eliminate the "double-burst" boundary problem of Fixed Window.
"""

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock


# ---------------------------------------------------------------------------
# 1. Log (Exact) Variant
# ---------------------------------------------------------------------------

class SlidingWindowLogLimiter:
    """
    Exact sliding window using a per-client timestamp log.

    Parameters
    ----------
    limit          : max requests in any window of `window_seconds`.
    window_seconds : width of the sliding window.
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._logs: dict[str, deque] = {}
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        now = time.time()
        cutoff = now - self.window

        with self._lock:
            log = self._logs.setdefault(client_id, deque())

            # Evict timestamps outside the window (oldest first)
            while log and log[0] <= cutoff:
                log.popleft()

            count = len(log)
            remaining = max(0, self.limit - count)

            if count < self.limit:
                log.append(now)
                remaining -= 1
                allowed = True
            else:
                allowed = False

        # Reset = when the oldest request in the log falls out of the window
        with self._lock:
            log = self._logs.get(client_id, deque())
            reset_at = int(log[0] + self.window) if log else int(now + self.window)

        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            headers["Retry-After"] = str(max(1, reset_at - int(now)))

        return allowed, headers


# ---------------------------------------------------------------------------
# 2. Counter (Approximate) Variant
# ---------------------------------------------------------------------------

@dataclass
class _TwoWindowState:
    prev_count: int = 0
    curr_count: int = 0
    curr_start: float = 0.0


class SlidingWindowCounterLimiter:
    """
    Approximate sliding window using two fixed-window counters.

    effective_count = prev_count × (1 − elapsed/W) + curr_count

    Parameters
    ----------
    limit          : max requests in any window of `window_seconds`.
    window_seconds : width of each fixed sub-window (same as the
                     sliding window width).
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._clients: dict[str, _TwoWindowState] = {}
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        now = time.time()

        with self._lock:
            state = self._clients.setdefault(
                client_id, _TwoWindowState(curr_start=now)
            )

            elapsed = now - state.curr_start

            if elapsed >= 2 * self.window:
                # Both windows are stale — full reset
                state.prev_count = 0
                state.curr_count = 0
                state.curr_start = now
                elapsed = 0.0
            elif elapsed >= self.window:
                # Roll over: current → previous, start fresh current
                state.prev_count = state.curr_count
                state.curr_count = 0
                state.curr_start = now
                elapsed = 0.0

            # Interpolated count
            weight = 1.0 - (elapsed / self.window)
            effective = state.prev_count * weight + state.curr_count

            reset_at = int(state.curr_start + self.window)
            remaining = max(0, self.limit - int(effective))

            if effective < self.limit:
                state.curr_count += 1
                remaining = max(0, remaining - 1)
                allowed = True
            else:
                allowed = False

        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            headers["Retry-After"] = str(max(1, reset_at - int(now)))

        return allowed, headers


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Sliding Window Log Demo — limit=5 per 10 s\n")
    log_limiter = SlidingWindowLogLimiter(limit=5, window_seconds=10)
    client = "user_99"
    for i in range(7):
        allowed, headers = log_limiter.is_allowed(client)
        status = "✅ ALLOW" if allowed else "❌ DENY  → 429"
        print(f"  Request {i+1}: {status}  remaining={headers['X-RateLimit-Remaining']}")

    print("\nSliding Window Counter Demo — limit=5 per 10 s\n")
    counter_limiter = SlidingWindowCounterLimiter(limit=5, window_seconds=10)
    for i in range(7):
        allowed, headers = counter_limiter.is_allowed(client)
        status = "✅ ALLOW" if allowed else "❌ DENY  → 429"
        print(f"  Request {i+1}: {status}  remaining={headers['X-RateLimit-Remaining']}")
