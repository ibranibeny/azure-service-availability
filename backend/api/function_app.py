"""Availability API Function app (HTTP).

Reads the snapshot that the scheduled collector writes to Azure Managed Redis and
serves it to the dashboard. Every data route requires a Microsoft Entra ID access
token for this API (see availability_api/auth.py); CORS is set on the Function app.
"""
import gzip
import json
import logging
import os
import re

import azure.functions as func

from availability_api import auth, store

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

REGION_RE = re.compile(r"^[a-z0-9]{2,40}$")


def _json(obj, status=200, extra=None):
    headers = {"Cache-Control": "no-store"}
    headers.update(extra or {})
    return func.HttpResponse(json.dumps(obj, separators=(",", ":")), status_code=status,
                             mimetype="application/json", headers=headers)


def _error(status, code, message):
    extra = {}
    if status == 401:
        extra["WWW-Authenticate"] = 'Bearer error="%s"' % code
    return _json({"error": {"code": code, "message": message}}, status, extra)


def _guard(req):
    try:
        return auth.validate(req.headers.get("Authorization")), None
    except auth.AuthError as e:
        if e.status >= 500:
            logging.error("Auth configuration error: %s", e.message)
        return None, _error(e.status, e.code, e.message)


def _document(req, name):
    claims, denied = _guard(req)
    if denied:
        return denied
    try:
        raw = store.get_packed(name)
    except Exception:
        logging.exception("Redis read failed for %s", name)
        return _error(503, "cache_unavailable", "The availability cache can't be reached right now.")
    if raw is None:
        return _error(404, "not_collected", "No data yet. The scheduled collector hasn't published this item.")
    headers = {"Cache-Control": "private, max-age=120", "Vary": "Authorization, Accept-Encoding"}
    if "gzip" in (req.headers.get("Accept-Encoding") or "").lower():
        headers["Content-Encoding"] = "gzip"
        body = raw
    else:
        body = gzip.decompress(raw)
    return func.HttpResponse(body=body, status_code=200, mimetype="application/json", headers=headers)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json({"status": "ok"})


@app.route(route="me", methods=["GET"])
def me(req: func.HttpRequest) -> func.HttpResponse:
    claims, denied = _guard(req)
    if denied:
        return denied
    return _json({"name": claims.get("name"),
                  "user": claims.get("preferred_username") or claims.get("upn"),
                  "tenant": claims.get("tid"), "scopes": (claims.get("scp") or "").split()})


@app.route(route="summary", methods=["GET"])
def summary(req: func.HttpRequest) -> func.HttpResponse:
    return _document(req, "summary")


@app.route(route="regions/{name}", methods=["GET"])
def region(req: func.HttpRequest) -> func.HttpResponse:
    name = (req.route_params.get("name") or "").lower()
    if not REGION_RE.match(name):
        return _error(400, "bad_region", "Region names are lowercase letters and digits, e.g. indonesiacentral.")
    return _document(req, "region:" + name)


@app.route(route="vm-skus", methods=["GET"])
def vm_skus(req: func.HttpRequest) -> func.HttpResponse:
    return _document(req, "vmindex")


@app.route(route="managed-redis", methods=["GET"])
def managed_redis(req: func.HttpRequest) -> func.HttpResponse:
    return _document(req, "amr")


@app.route(route="changes", methods=["GET"])
def changes(req: func.HttpRequest) -> func.HttpResponse:
    return _document(req, "changes")


@app.route(route="runs", methods=["GET"])
def runs(req: func.HttpRequest) -> func.HttpResponse:
    claims, denied = _guard(req)
    if denied:
        return denied
    try:
        items = store.get_runs(20)
    except Exception:
        logging.exception("Redis read failed for runs")
        return _error(503, "cache_unavailable", "The availability cache can't be reached right now.")
    return _json({"schedule": os.environ.get("COLLECT_SCHEDULE", ""), "runs": items})
