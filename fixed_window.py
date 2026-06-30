"""
Fixed Window Rate Limiter
=========================
Divides time into discrete windows of length W seconds.
Each client gets a counter that resets at the start of each window.

Pros:  O(1) memory per client; dead simple.
Cons:  Vulnerable to double-burst at window boundary
       (up to 2L requests in 2 seconds).
"""

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class FixedWindowState:
    count: int = 0
    window_start: float = field(default_factory=time.time)


class FixedWindowRateLimiter:
    """
    Thread-safe fixed-window rate limiter.

    Parameters
    ----------
    limit : int
        Maximum requests allowed per window.
    window_seconds : int
        Duration of each window in seconds.
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._clients: dict[str, FixedWindowState] = {}
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        """
        Check whether a request from client_id is allowed.

        Returns
        -------
        (allowed, headers) where headers is the dict of rate-limit
        response headers to send back to the client.
        """
        now = time.time()

        with self._lock:
            state = self._clients.setdefault(client_id, FixedWindowState(window_start=now))

            # Reset counter if the window has elapsed
            if now - state.window_start >= self.window:
                state.count = 0
                state.window_start = now

            reset_at = int(state.window_start + self.window)
            remaining = max(0, self.limit - state.count)

            if state.count < self.limit:
                state.count += 1
                remaining -= 1
                allowed = True
            else:
                allowed = False

        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            retry_after = max(1, reset_at - int(now))
            headers["Retry-After"] = str(retry_after)

        return allowed, headers

    def get_stats(self, client_id: str) -> dict:
        """Return current counter state for a client (useful for debugging)."""
        with self._lock:
            state = self._clients.get(client_id)
            if not state:
                return {"count": 0, "window_start": None}
            return {"count": state.count, "window_start": state.window_start}


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    limiter = FixedWindowRateLimiter(limit=5, window_seconds=10)
    client = "user_42"

    print("Fixed Window Demo — limit=5 per 10 s\n")
    for i in range(7):
        allowed, headers = limiter.is_allowed(client)
        status = "✅ ALLOW" if allowed else "❌ DENY  → 429"
        print(f"  Request {i+1}: {status}  remaining={headers['X-RateLimit-Remaining']}")
