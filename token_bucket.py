"""
Token Bucket Rate Limiter
==========================
A bucket holds up to B tokens. Tokens are added at a steady rate R/s.
Each request consumes one token. Empty bucket → 429.

Pros:  Allows short bursts up to B; average throughput capped at R req/s.
Cons:  An idle client can accumulate a full burst — may or may not be
       desirable depending on your use case.
"""

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _TokenBucketState:
    tokens: float
    last_refill: float = field(default_factory=time.time)


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Parameters
    ----------
    capacity      : Maximum tokens the bucket can hold (burst size B).
    refill_rate   : Tokens added per second (R).
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._clients: dict[str, _TokenBucketState] = {}
        self._lock = Lock()

    def _refill(self, state: _TokenBucketState, now: float) -> None:
        """Add tokens proportional to elapsed time since last refill."""
        elapsed = now - state.last_refill
        state.tokens = min(self.capacity, state.tokens + elapsed * self.refill_rate)
        state.last_refill = now

    def is_allowed(self, client_id: str, tokens_required: float = 1.0) -> tuple[bool, dict]:
        """
        Check whether a request from client_id is allowed.

        Parameters
        ----------
        client_id       : Unique identifier for the client/user.
        tokens_required : Cost of this request in tokens (default 1).
                          Useful for weighted endpoints (e.g. heavy
                          compute calls cost more tokens).

        Returns
        -------
        (allowed, headers)
        """
        now = time.time()

        with self._lock:
            state = self._clients.setdefault(
                client_id, _TokenBucketState(tokens=self.capacity)
            )
            self._refill(state, now)

            if state.tokens >= tokens_required:
                state.tokens -= tokens_required
                allowed = True
            else:
                allowed = False

            # Time until the bucket has enough tokens for the next request
            deficit = tokens_required - state.tokens
            retry_after = max(1, int(deficit / self.refill_rate)) if not allowed else 0
            remaining_tokens = int(state.tokens)

        headers = {
            "X-RateLimit-Limit": str(int(self.capacity)),
            "X-RateLimit-Remaining": str(remaining_tokens),
            # Reset ≈ time when bucket would be full again (worst case)
            "X-RateLimit-Reset": str(int(now + (self.capacity - remaining_tokens) / self.refill_rate)),
        }
        if not allowed:
            headers["Retry-After"] = str(retry_after)

        return allowed, headers

    def get_tokens(self, client_id: str) -> float:
        """Return current token count for a client (useful for monitoring)."""
        now = time.time()
        with self._lock:
            state = self._clients.get(client_id)
            if not state:
                return self.capacity
            self._refill(state, now)
            return state.tokens


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # capacity=5 tokens, refill at 1 token/s
    limiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)
    client = "user_7"

    print("Token Bucket Demo — capacity=5, refill=1 tok/s\n")
    print("Burst of 7 requests (expect first 5 allowed, last 2 denied):\n")
    for i in range(7):
        allowed, headers = limiter.is_allowed(client)
        status = "✅ ALLOW" if allowed else "❌ DENY  → 429"
        print(f"  Request {i+1}: {status}  tokens_left={headers['X-RateLimit-Remaining']}")

    print("\nWaiting 3 seconds for refill...\n")
    time.sleep(3)
    for i in range(4):
        allowed, headers = limiter.is_allowed(client)
        status = "✅ ALLOW" if allowed else "❌ DENY  → 429"
        print(f"  Request {i+8}: {status}  tokens_left={headers['X-RateLimit-Remaining']}")
