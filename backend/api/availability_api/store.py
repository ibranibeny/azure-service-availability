"""Azure Managed Redis reader with Microsoft Entra ID (managed identity) auth."""
import gzip
import json
import os
import threading
import time

import redis
from azure.identity import ManagedIdentityCredential

PREFIX = "{asa}:v1:"
SCOPE = "https://redis.azure.com/.default"

_lock = threading.Lock()
_client = None
_expires = 0
_credential = None
_cache = {}
CACHE_SECONDS = int(os.environ.get("API_CACHE_SECONDS", "60"))


def _redis():
    global _client, _expires, _credential
    with _lock:
        if _client is None or time.time() > _expires - 300:
            if _credential is None:
                _credential = ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"])
            tok = _credential.get_token(SCOPE)
            if _client is not None:
                try:
                    _client.close()
                except Exception:
                    pass
            _client = redis.Redis(
                host=os.environ["REDIS_HOST"], port=int(os.environ.get("REDIS_PORT", "10000")),
                ssl=True, username=os.environ["REDIS_USER_OBJECT_ID"], password=tok.token,
                socket_timeout=10, socket_connect_timeout=10)
            _expires = tok.expires_on
        return _client


def get_packed(name):
    """Return the gzip-compressed JSON document stored under `name`, or None."""
    now = time.time()
    hit = _cache.get(name)
    if hit and hit[0] > now:
        return hit[1]
    raw = _redis().get(PREFIX + name)
    if raw is not None:
        _cache[name] = (now + CACHE_SECONDS, raw)
    return raw


def get_runs(count=20):
    rows = _redis().lrange(PREFIX + "runs", 0, max(0, count - 1))
    return [json.loads(r) for r in rows]


def unpack(raw):
    return json.loads(gzip.decompress(raw))
