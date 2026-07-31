import os
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict = defaultdict(deque)

# Redis backend (اختیاری)
_redis_client = None
_redis_available = False


def _get_redis():
    global _redis_client, _redis_available
    if _redis_available:
        return _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis as redis_mod
                _redis_client = redis_mod.from_url(redis_url, socket_timeout=2, decode_responses=True)
                _redis_client.ping()
                _redis_available = True
                import logging
                logging.getLogger(__name__).info("✅ Redis rate limiter connected: %s", redis_url)
            except Exception:
                _redis_client = None
                _redis_available = False
        else:
            _redis_client = False  # علامت عدم وجود Redis
    return _redis_client if _redis_available else None


def _in_memory_rate_limit(key: str, max_requests: int, window_seconds: int, raise_on_limit: bool = True) -> Optional[bool]:
    """محدودکننده مبتنی بر حافظه."""
    now = time.time()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= max_requests:
            if raise_on_limit:
                raise HTTPException(status_code=429, detail="تعداد درخواست‌های شما بیش از حد مجاز است. کمی صبر کنید.")
            return False
        hits.append(now)
        return True


def _redis_check(key: str, max_requests: int, window_seconds: int, raise_on_limit: bool = True) -> Optional[bool]:
    """محدودکننده مبتنی بر Redis (اشتراکی بین workerها)."""
    client = _get_redis()
    if not client:
        return None  # Redis در دسترس نیست
    try:
        now = int(time.time())
        window_start = now - window_seconds
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window_seconds)
        results = pipe.execute()
        count = results[1]
        if count >= max_requests:
            if raise_on_limit:
                raise HTTPException(status_code=429, detail="تعداد درخواست‌های شما بیش از حد مجاز است. کمی صبر کنید.")
            return False
        return True
    except Exception:
        return None  # در صورت خطا در Redis، fallback به in-memory نمی‌شود


def rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """محدودکننده نرخ درخواست. ابتدا Redis را امتحان می‌کند، در صورت عدم دسترسی از حافظه استفاده می‌کند."""
    result = _redis_check(key, max_requests, window_seconds)
    if result is None:
        _in_memory_rate_limit(key, max_requests, window_seconds)


def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """نسخه non-blocking بررسی محدودیت نرخ - Exception پرتاب نمی‌کند، فقط bool برمی‌گرداند."""
    result = _redis_check(key, max_requests, window_seconds, raise_on_limit=False)
    if result is None:
        result = _in_memory_rate_limit(key, max_requests, window_seconds, raise_on_limit=False)
    return result if result is not None else True


def get_remaining(key: str, max_requests: int, window_seconds: int) -> dict:
    """دریافت وضعیت محدودیت نرخ: تعداد باقیمانده و زمان تا ریست."""
    client = _get_redis()
    if client:
        try:
            now = int(time.time())
            window_start = now - window_seconds
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.ttl(key)
            results = pipe.execute()
            count = results[1]
            ttl = max(0, results[2] if results[2] else window_seconds)
            return {"remaining": max(0, max_requests - count), "reset_in_seconds": ttl, "limit": max_requests}
        except Exception:
            pass
    # Fallback به in-memory
    now = time.time()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        remaining = max(0, max_requests - len(hits))
        reset_in = window_seconds
        if hits:
            reset_in = max(0, int(window_seconds - (now - hits[0])))
        return {"remaining": remaining, "reset_in_seconds": reset_in, "limit": max_requests}
