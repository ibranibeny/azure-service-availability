"""Azure Managed Redis writer (Microsoft Entra ID auth, TLS on port 10000)."""
import gzip
import json
import os

import redis

PREFIX = "{asa}:v1:"   # one hash slot, so the snapshot is written in a single transaction
RUNS_KEPT = 50


def pack(doc):
    return gzip.compress(json.dumps(doc, separators=(",", ":")).encode("utf-8"), compresslevel=6)


class Store:
    def __init__(self, token):
        self.r = redis.Redis(
            host=os.environ["REDIS_HOST"], port=int(os.environ.get("REDIS_PORT", "10000")),
            ssl=True, username=os.environ["REDIS_USER_OBJECT_ID"], password=token,
            socket_timeout=30, socket_connect_timeout=15)

    def get_json(self, name):
        raw = self.r.get(PREFIX + name)
        return json.loads(gzip.decompress(raw)) if raw else None

    def add_run(self, record):
        try:
            pipe = self.r.pipeline(transaction=True)
            pipe.lpush(PREFIX + "runs", json.dumps(record))
            pipe.ltrim(PREFIX + "runs", 0, RUNS_KEPT - 1)
            pipe.execute()
        except redis.RedisError:
            pass

    def write(self, docs, record):
        pipe = self.r.pipeline(transaction=True)
        for name in ("summary", "vmindex", "amr", "changes"):
            pipe.set(PREFIX + name, pack(docs[name]))
        for region, doc in docs["regions"].items():
            pipe.set(PREFIX + "region:" + region, pack(doc))
        pipe.lpush(PREFIX + "runs", json.dumps(record))
        pipe.ltrim(PREFIX + "runs", 0, RUNS_KEPT - 1)
        pipe.execute()
