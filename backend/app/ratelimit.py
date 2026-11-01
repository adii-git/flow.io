import time
from fastapi import HTTPException, Request
from .config import get_settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class RateLimiter:
    def __init__(self):
        self._mem: dict[str, tuple[int, float]] = {}
        self._r = None

    def _client(self):
        url = get_settings().redis_url
        if url and redis and self._r is None:
            self._r = redis.from_url(url, socket_timeout=1)
        return self._r

    def hit(self, key: str, limit: int, window: int) -> bool:
        r = self._client()
        if r:
            try:
                k = f"rl:{key}:{int(time.time() // window)}"
                n = r.incr(k)
                if n == 1:
                    r.expire(k, window)
                return n <= limit
            except Exception:
                pass  # Redis down: fall back to per-process counting rather than locking everyone out
        n, reset = self._mem.get(key, (0, 0.0))
        t = time.time()
        if t > reset:
            n, reset = 0, t + window
        self._mem[key] = (n + 1, reset)
        return n + 1 <= limit

    def reset(self):
        self._mem.clear()


limiter = RateLimiter()


def rate_limit(name: str, limit: int, window: int = 60):
    def dep(request: Request):
        ip = request.client.host if request.client else "unknown"
        if not limiter.hit(f"{name}:{ip}", limit, window):
            raise HTTPException(429, f"Too many attempts. Wait {window} seconds and try again.")
    return dep
