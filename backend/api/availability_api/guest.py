"""Read-only guest access without sign-in (optional, GUEST_READ_ACCESS=true).

Requests that carry no Authorization header are served as a read-only guest:
the same availability snapshot, with collector error details removed. Requests
that do carry a token are always validated; a bad token never falls back to guest.
A small per-instance rate limit protects the public endpoints.
"""
import os
import threading
import time
from collections import deque

ENABLED = os.environ.get("GUEST_READ_ACCESS", "false").lower() == "true"
LIMIT_PER_MINUTE = int(os.environ.get("GUEST_RATE_LIMIT_PER_MINUTE", "120"))
CLAIMS = {"guest": True, "name": "Guest", "readOnly": True}

_hits = {}
_lock = threading.Lock()


def client_ip(req):
    ip = ((req.headers.get("X-Forwarded-For") or "").split(",")[0]).strip()
    if ip.count(":") == 1:                      # IPv4 with a port, e.g. 203.0.113.7:51234
        ip = ip.split(":")[0]
    return ip.strip("[]") or "unknown"


def allow(ip, now=None):
    """Sliding one-minute window per client address (best effort, per instance)."""
    now = time.monotonic() if now is None else now
    with _lock:
        hits = _hits.get(ip)
        if hits is None:
            if len(_hits) > 20000:
                _hits.clear()
            hits = _hits[ip] = deque()
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= LIMIT_PER_MINUTE:
            return False
        hits.append(now)
        return True


def scrub_summary(doc):
    """Guests see counts, not the collector's raw error text."""
    meta = dict(doc.get("meta") or {})
    if isinstance(meta.get("errors"), list):
        meta["errors"] = len(meta["errors"])
    return {**doc, "meta": meta}


def scrub_run(run):
    out = {k: v for k, v in run.items() if k not in ("slowest", "error", "calls")}
    if not run.get("ok", True):
        out["error"] = "Collection failed (details are visible to signed-in users)."
    return out
