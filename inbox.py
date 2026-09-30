import hashlib
import hmac
import json
import os

import requests

import cache

API = "https://webhook.site"


def endpoint():
    return os.getenv("EXA_MONITOR_WEBHOOK_URL") or (cache.get("webhook", "endpoint") or {}).get("url")


def create_endpoint():
    token = requests.post(f"{API}/token", headers={"Accept": "application/json"}, timeout=10).json()["uuid"]
    cache.put("webhook", "endpoint", {"url": f"{API}/{token}"})
    return f"{API}/{token}"


def deliveries(url, monitor_id):
    token = url.rstrip("/").split("/")[-1]
    r = requests.get(f"{API}/token/{token}/requests", params={"sorting": "newest"},
                     headers={"Accept": "application/json"}, timeout=10)
    return [d for d in map(_delivery, r.json()["data"]) if d["body"].get("data", {}).get("monitorId") == monitor_id]


def _delivery(d):
    sig = (d["headers"].get("exa-signature") or [""])[0]
    try:
        body = json.loads(d["content"] or "{}")
    except json.JSONDecodeError:
        body = {"raw": d["content"]}
    return {"received": d["created_at"], "raw": d["content"] or "", "signature": sig, "body": body}


def verify(raw, signature, secret):
    try:
        parts = dict(p.split("=", 1) for p in signature.split(","))
        expected = hmac.new(secret.encode(), f"{parts['t']}.{raw}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except (KeyError, ValueError, AttributeError):
        return False
