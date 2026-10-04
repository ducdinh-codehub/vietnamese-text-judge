"""Keeps one client, or a burst of traffic, from overloading the model.

- rate_limited: each IP may call the API LIMIT_REQUESTS times per LIMIT_WINDOW seconds, else 429.
- run_model: at most MAX_CONCURRENT model runs at once; a request that cannot get a slot within
  QUEUE_WAIT seconds gets 503 instead of piling up. Recent results are cached, so the same text
  sent again returns without running the model.

State lives in this process's memory. With several server processes each has its own counters, so
put nginx or Cloudflare in front for a global limit (see README).
"""

import functools
import hashlib
import json
import math
import os
import threading
import time
from collections import OrderedDict, deque

from django.http import JsonResponse

LIMIT_REQUESTS = int(os.environ.get("LAYA_RATE_LIMIT", "60"))
LIMIT_WINDOW = 60.0
MAX_CONCURRENT = int(os.environ.get("LAYA_MAX_CONCURRENT", "2"))
QUEUE_WAIT = 5.0
CACHE_SIZE = 512
# Forget idle IPs once this many are tracked, so a flood of addresses cannot grow memory forever.
MAX_TRACKED_IPS = 10_000
# Only trust X-Forwarded-For when a reverse proxy you run sets it; anyone can send the header.
TRUST_PROXY = os.environ.get("LAYA_TRUST_PROXY", "0") == "1"


class Busy(Exception):
    """Every model slot stayed taken for QUEUE_WAIT seconds."""


# ---------- rate limit ----------

_hits = {}  # ip -> deque of request times inside the window
_hits_lock = threading.Lock()


def client_ip(request):
    if TRUST_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # The proxy appends the address it saw, so the last entry is the one it vouches for.
            return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _check_rate(ip, now):
    """None if the request may go ahead, else seconds until it may."""
    with _hits_lock:
        if len(_hits) > MAX_TRACKED_IPS:
            for key in [k for k, times in _hits.items() if not times or times[-1] < now - LIMIT_WINDOW]:
                del _hits[key]
        times = _hits.setdefault(ip, deque())
        while times and times[0] <= now - LIMIT_WINDOW:
            times.popleft()
        if len(times) >= LIMIT_REQUESTS:
            return max(1, math.ceil(times[0] + LIMIT_WINDOW - now))
        times.append(now)
        return None


def rate_limited(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        retry_after = _check_rate(client_ip(request), time.monotonic())
        if retry_after is not None:
            response = JsonResponse(
                {"error": f"Quá nhiều yêu cầu, vui lòng thử lại sau {retry_after} giây. (Too many requests)"},
                status=429,
            )
            response["Retry-After"] = str(retry_after)
            return response
        return view(request, *args, **kwargs)

    return wrapper


def busy_response():
    response = JsonResponse({"error": "Máy chủ đang bận, vui lòng thử lại sau giây lát. (Server busy)"}, status=503)
    response["Retry-After"] = "2"
    return response


# ---------- model slots and result cache ----------

_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
_cache = OrderedDict()
_cache_lock = threading.Lock()


def cache_key(kind, payload):
    raw = json.dumps([kind, payload], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_model(key, compute):
    """compute() via the cache and a model slot. Raises Busy when no slot frees up in time."""
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not _slots.acquire(timeout=QUEUE_WAIT):
        raise Busy()
    try:
        result = compute()
    finally:
        _slots.release()
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return result
