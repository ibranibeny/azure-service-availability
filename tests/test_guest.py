"""Offline tests for read-only guest access (no sign-in)."""
import gzip
import json
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "api"))
# Same auth settings as test_auth.py: the auth module reads them once at import, whichever test loads it first.
os.environ.update({"GUEST_READ_ACCESS": "true", "GUEST_RATE_LIMIT_PER_MINUTE": "3",
                   "AUTH_TENANT_ID": "11111111-2222-3333-4444-555555555555",
                   "AUTH_API_CLIENT_ID": "aaaaaaaa-0000-0000-0000-000000000001",
                   "AUTH_ALLOWED_CLIENT_IDS": "bbbbbbbb-0000-0000-0000-000000000002",
                   "AUTH_ALLOWED_DOMAINS": "contoso.day", "AUTH_ALLOW_GUESTS": "false"})


class _Resp:
    def __init__(self, body=None, status_code=200, mimetype=None, headers=None):
        self.body = body if isinstance(body, (bytes, type(None))) else body.encode()
        self.status_code, self.headers = status_code, headers or {}


class _App:
    def __init__(self, **kw):
        pass

    def route(self, **kw):
        return lambda f: f


# Minimal stand-ins so function_app imports without the Functions runtime or Redis.
sys.modules.setdefault("azure", types.ModuleType("azure"))
fmod = types.ModuleType("azure.functions")
fmod.FunctionApp, fmod.HttpResponse, fmod.HttpRequest = _App, _Resp, object
fmod.AuthLevel = types.SimpleNamespace(ANONYMOUS="anonymous")
sys.modules["azure.functions"] = fmod
sys.modules["azure"].functions = fmod
store = types.ModuleType("availability_api.store")
SUMMARY = {"generatedAt": "2026-11-18T06:05:35Z", "regions": [], "meta": {"errors": [{"step": "x", "error": "secret detail"}]}}
store.get_packed = lambda name: gzip.compress(json.dumps(SUMMARY).encode())
store.get_runs = lambda n: [{"at": "a", "ok": True, "errors": 0, "slowest": [{"cmd": "az rest"}]},
                            {"at": "b", "ok": False, "error": "boom /subscriptions/123"}]
sys.modules["availability_api.store"] = store
import availability_api  # noqa: E402
availability_api.store = store
from availability_api import guest  # noqa: E402
import function_app  # noqa: E402


class Req:
    def __init__(self, headers=None, route_params=None):
        self.headers, self.route_params = headers or {}, route_params or {}


class GuestTests(unittest.TestCase):
    def setUp(self):
        guest._hits.clear()

    def test_summary_without_token_is_scrubbed(self):
        r = function_app.summary(Req({"X-Forwarded-For": "203.0.113.7:5000"}))
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.body)
        self.assertEqual(body["meta"]["errors"], 1)
        self.assertNotIn("secret detail", r.body.decode())

    def test_me_and_runs_for_guest(self):
        me = json.loads(function_app.me(Req({"X-Forwarded-For": "203.0.113.8"})).body)
        self.assertTrue(me["guest"] and me["readOnly"])
        runs = json.loads(function_app.runs(Req({"X-Forwarded-For": "203.0.113.8"})).body)["runs"]
        self.assertNotIn("slowest", runs[0])
        self.assertNotIn("/subscriptions/", runs[1]["error"])

    def test_bad_token_never_falls_back_to_guest(self):
        r = function_app.summary(Req({"Authorization": "Bearer not-a-jwt"}))
        self.assertEqual(r.status_code, 401)

    def test_rate_limit(self):
        h = {"X-Forwarded-For": "198.51.100.1"}
        codes = [function_app.summary(Req(h)).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertTrue(guest.allow("198.51.100.1", now=10 ** 9))   # window moved on

    def test_guest_mode_off(self):
        guest.ENABLED = False
        try:
            self.assertEqual(function_app.summary(Req({})).status_code, 401)
        finally:
            guest.ENABLED = True


if __name__ == "__main__":
    unittest.main()
