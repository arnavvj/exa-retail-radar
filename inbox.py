import base64
import hashlib
import hmac
import json
import os
import secrets
import string

import requests

import cache

PLAY = "https://play.svix.com"


def endpoint():
    return os.getenv("EXA_MONITOR_WEBHOOK_URL") or (cache.get("webhook", "endpoint") or {}).get("url")


def create_endpoint():
    token = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(27))
    cache.put("webhook", "endpoint", {"url": f"{PLAY}/in/{token}/"})
    return f"{PLAY}/in/{token}/"


def deliveries(url, monitor_id):
    token = url.rstrip("/").split("/")[-1]
    r = requests.get(f"https://api.play.svix.com/history/{token}/", timeout=10)
    found = [d for d in map(_delivery, r.json()["data"]) if d["body"].get("data", {}).get("monitorId") == monitor_id]
    return sorted(found, key=lambda d: d["received"], reverse=True)


def _delivery(d):
    raw = base64.b64decode(d["body"] or "").decode()
    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        body = {"raw": raw}
    return {"received": d["created_at"][:19].replace("T", " "), "raw": raw,
            "signature": d["headers"].get("exa-signature", ""), "body": body}


def verify(raw, signature, secret):
    try:
        parts = dict(p.split("=", 1) for p in signature.split(","))
        expected = hmac.new(secret.encode(), f"{parts['t']}.{raw}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except (KeyError, ValueError, AttributeError):
        return False
