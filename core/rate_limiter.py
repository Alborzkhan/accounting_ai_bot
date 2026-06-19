import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict = defaultdict(deque)


def rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """محدودکننده نرخ درخواست در حافظه (per-process). برای استقرار با چند worker/instance
    باید با یک backend مشترک مثل Redis جایگزین شود."""
    now = time.time()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= max_requests:
            raise HTTPException(status_code=429, detail="تعداد درخواست‌های شما بیش از حد مجاز است. کمی صبر کنید.")
        hits.append(now)
