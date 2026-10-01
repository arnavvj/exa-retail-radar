import os
import time
from datetime import datetime
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa
from exa_py.api import to_camel_case

import cache

load_dotenv()
TTL = 6 * 3600


@lru_cache
def client():
    return Exa(api_key=os.environ["EXA_API_KEY"])


def has_key():
    return bool(os.getenv("EXA_API_KEY"))


def now():
    return datetime.now().isoformat(timespec="seconds")


def cached_call(op, request, fn, live):
    hit = None if live else cache.get(op, request, TTL)
    if hit:
        return {**hit, "source": "cached"}
    start = time.time()
    try:
        data = fn()
    except Exception as e:
        old = cache.get(op, request)
        if old:
            return {**old, "source": "cached", "error": str(e)}
        return {"source": "error", "error": str(e), "request": request}
    out = {"data": data, "request": request, "fetched_at": now(), "latency_s": round(time.time() - start, 1)}
    cache.put(op, request, out)
    if op == "snapshot":
        cache.put("usage", "snapshot", snapshot_calls() + 1)
    return {**out, "source": "live"}


def snapshot_calls():
    return cache.get("usage", "snapshot") or 0


def request(call, path, python):
    return {"call": call, "python": python, "rest": {"endpoint": f"POST https://api.exa.ai/{path}",
                                                     "body": to_camel_case(python, skip_keys=["output_schema"])}}


def cost(r):
    return r.cost_dollars.total if r.cost_dollars else None


def search(query, live=False, **kwargs):
    kwargs = {"type": "auto", "num_results": 8, "contents": {"highlights": True}, **kwargs}
    op = "snapshot" if "snapshot_as_of" in kwargs["contents"] else kwargs.get("category") or "search"

    def run():
        r = client().search(query, **kwargs)
        return {"results": [_result(x) for x in r.results], "output": _output(r.output), "cost": cost(r)}

    return cached_call(op, request("exa.search", "search", {"query": query, **kwargs}), run, live)


def contents(urls, query, live=False):
    kwargs = {"highlights": {"query": query, "max_characters": 600}, "text": False}

    def run():
        r = client().get_contents(urls, **kwargs)
        return {"results": [_result(x) for x in r.results], "cost": cost(r)}

    return cached_call("contents", request("exa.get_contents", "contents", {"urls": urls, **kwargs}), run, live)


def _result(r):
    ents = {e.type: e.properties for e in r.entities or []}
    return {"title": r.title, "url": r.url, "domain": urlparse(r.url).netloc.removeprefix("www."),
            "date": (r.published_date or "")[:10], "highlights": r.highlights or [],
            "company": _company(ents["company"]) if "company" in ents else None,
            "person": _person(ents["person"]) if "person" in ents else None}


def _person(p):
    now = next((w for w in p.work_history or [] if not (w.dates and w.dates.to_date)), None)
    return {"name": p.name, "location": p.location, "title": now.title if now else None,
            "employer": now.company.name if now and now.company else None}


def _company(p):
    hq = p.headquarters
    return {"name": p.name, "founded": p.founded_year,
            "employees": p.workforce.total if p.workforce else None,
            "hq": ", ".join(x for x in [hq.city, hq.country] if x) if hq else None,
            "revenue": p.financials.revenue_annual if p.financials else None}


def _grounding(rows):
    return [{"field": g.field, "confidence": g.confidence,
             "citations": [{"url": c.url, "title": c.title} for c in g.citations]} for g in rows or []]


def _output(o):
    return {"content": o.content, "grounding": _grounding(o.grounding)} if o else None


def agent_cached(request):
    hit = cache.get("agent", request, TTL)
    return {**hit, "source": "cached"} if hit else None


def agent_start(request):
    p = request["python"]
    run = client().agent.runs.create(query=p["query"], input=p["input"],
                                     output_schema=p["output_schema"], effort=p["effort"])
    return {"id": run.id, "request": request, "started": time.time()}


def agent_poll(job):
    run = client().agent.runs.get(job["id"])
    if run.status in ("queued", "running"):
        return {"status": run.status}
    if run.status != "completed":
        msg = run.error.message if run.error else run.status
        return {"status": run.status, "source": "error", "error": f"Agent run {run.status}: {msg}"}
    out = {"data": {"id": run.id, "structured": run.output.structured,
                    "grounding": _grounding(run.output.grounding), "cost": cost(run)},
           "request": job["request"], "fetched_at": now(), "latency_s": round(time.time() - job["started"], 1)}
    cache.put("agent", job["request"], out)
    return {**out, "status": "completed", "source": "live"}


def monitor_request(supplier, query, webhook):
    body = {"name": f"Supplier watch: {supplier}",
            "search": {"query": query, "numResults": 5, "contents": {"highlights": True}},
            "trigger": {"type": "interval", "period": "1d"},
            "webhook": {"url": webhook or "<EXA_MONITOR_WEBHOOK_URL>", "events": ["monitor.run.completed"]}}
    return {"call": "exa.monitors.create", "python": {"params": body},
            "rest": {"endpoint": "POST https://api.exa.ai/monitors", "body": body}}


def create_monitor(supplier, query, webhook):
    request = monitor_request(supplier, query, webhook)
    m = client().monitors.create(request["python"]["params"])
    client().monitors.trigger(m.id)
    saved = {"id": m.id, "request": request, "created": now(), "secret": m.webhook_secret}
    cache.put("monitor", supplier, saved)
    return saved


def saved_monitor(supplier):
    return cache.get("monitor", supplier)
