"""
Leaky Bucket Rate Limiter
==========================
Requests enter a FIFO queue (the "bucket"). They are processed (leak
out) at a fixed rate R. If the queue is full, new requests are dropped.

Pros:  Output rate is perfectly smooth — ideal for protecting downstream
       services that can't handle bursts (payment processors, SMS gateways).
Cons:  Adds queuing latency; bursty clients feel sluggish even when
       overall load is low.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _LeakyBucketState:
    queue: deque = field(default_factory=deque)
    last_leak: float = field(default_factory=time.time)


class LeakyBucketRateLimiter:
    """
    Thread-safe leaky bucket rate limiter.

    Parameters
    ----------
    capacity    : Maximum queue depth (B). Requests beyond this are dropped.
    leak_rate   : Requests processed (leaked) per second (R).
    """

    def __init__(self, capacity: int, leak_rate: float):
        self.capacity = capacity
        self.leak_rate = leak_rate
        self._clients: dict[str, _LeakyBucketState] = {}
        self._lock = Lock()

    def _leak(self, state: _LeakyBucketState, now: float) -> None:
        """Drain items from the queue proportional to elapsed time."""
        elapsed = now - state.last_leak
        to_drain = int(elapsed * self.leak_rate)
        for _ in range(min(to_drain, len(state.queue))):
            state.queue.popleft()
        if to_drain > 0:
            state.last_leak = now

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        """
        Attempt to enqueue a request for client_id.

        Returns
        -------
        (allowed, headers)
            allowed=True means the request was queued and will be
            processed. allowed=False means the bucket is full → 429.
        """
        now = time.time()

        with self._lock:
            state = self._clients.setdefault(client_id, _LeakyBucketState(last_leak=now))
            self._leak(state, now)

            queue_depth = len(state.queue)
            remaining_slots = max(0, self.capacity - queue_depth)

            if queue_depth < self.capacity:
                state.queue.append(now)
                remaining_slots -= 1
                allowed = True
            else:
                allowed = False

            # Retry after the next slot opens up
            retry_after = max(1, int(1.0 / self.leak_rate))
            reset_at = int(now + len(state.queue) / self.leak_rate)

        headers = {
            "X-RateLimit-Limit": str(self.capacity),
            "X-RateLimit-Remaining": str(remaining_slots),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            headers["Retry-After"] = str(retry_after)

        return allowed, headers

    def queue_depth(self, client_id: str) -> int:
        """Return current queue depth for a client."""
        now = time.time()
        with self._lock:
            state = self._clients.get(client_id)
            if not state:
                return 0
            self._leak(state, now)
            return len(state.queue)


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Queue of 5, processes 1 req/s
    limiter = LeakyBucketRateLimiter(capacity=5, leak_rate=1.0)
    client = "user_13"

    print("Leaky Bucket Demo — capacity=5 queue, leak=1 req/s\n")
    print("Burst of 8 requests (expect 5 queued, 3 dropped):\n")
    for i in range(8):
        allowed, headers = limiter.is_allowed(client)
        status = "✅ QUEUED" if allowed else "❌ DROPPED → 429"
        print(
            f"  Request {i+1}: {status}  "
            f"queue_slots_left={headers['X-RateLimit-Remaining']}"
        )
