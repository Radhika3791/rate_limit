
# Rate Limiting — Task 06

Complete code package accompanying `06_rate_limiting.md`.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the algorithm demos
python algorithms/fixed_window.py
python algorithms/sliding_window.py
python algorithms/token_bucket.py
python algorithms/leaky_bucket.py

# See the 429 response contract and retry simulation
python examples/response_contract.py

# See the cascading failure simulation (A vs B)
python examples/cascading_failure_demo.py

# Run all unit tests
python -m pytest tests/ -v
# or
python tests/test_algorithms.py
```

## Deployment Notes

### Layer A — Kong (gateway/kong_rate_limiting.yaml)
```bash
deck sync -s gateway/kong_rate_limiting.yaml
```

### Layer B — Nginx (gateway/nginx_rate_limit.conf)
```bash
sudo cp gateway/nginx_rate_limit.conf /etc/nginx/conf.d/orchestrator.conf
sudo nginx -t && sudo nginx -s reload
```

### Layer C — FastAPI middleware (middleware/rate_limit_middleware.py)
```python
from middleware.rate_limit_middleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware, redis_url="redis://localhost:6379")
```

Set plan limits via environment variables:
```bash
RATE_LIMIT_FREE_RPM=60
RATE_LIMIT_PRO_RPM=600
RATE_LIMIT_ENT_RPM=6000
```

## Algorithm Cheat Sheet

| Algorithm       | Burst   | Memory    | Smoothness | Best For                        |
|-----------------|---------|-----------|------------|---------------------------------|
| Fixed Window    | 2× at boundary | O(1) | Low   | Internal tooling                |
| Sliding Window  | None    | O(L)/O(1) | Medium     | Public APIs, per-user quotas    |
| Token Bucket    | Up to B | O(1)      | Medium     | APIs tolerating short bursts    |
| Leaky Bucket    | None    | O(B)      | High       | Protecting downstream services  |

---
*Document owner: Intern 6 | 2026-06-30*
