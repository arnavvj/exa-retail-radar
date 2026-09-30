"""Spike: run the real Exa calls once and dump raw output to cache/spike/ for inspection.

Usage: .venv/bin/python scripts/spike.py [search|snapshot|company|agent|all]
Agent is excluded from "all" because it's the only paid-per-run call ($0.10 at medium).
"""

import json
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from dotenv import load_dotenv
from exa_py import Exa

load_dotenv()
exa = Exa(api_key=os.environ["EXA_API_KEY"])
OUT = Path("cache/spike")
OUT.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "Prefer primary company sources, SEC filings and reputable industry/news sources. "
    "Avoid duplicate reporting of the same event. Do not state unverified allegations as facts. "
    "If a field cannot be verified from the sources, return null rather than guessing."
)

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "primary_signal": {"type": "string"},
        "increase_low_pct": {"type": ["number", "null"]},
        "increase_high_pct": {"type": ["number", "null"]},
        "effective_date": {"type": ["string", "null"]},
        "business_implication": {"type": "string"},
    },
    "required": ["risk_level", "primary_signal", "business_implication"],
}

COMPANY_SCHEMA = {
    "type": "object",
    "properties": {
        "companies": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "website": {"type": "string"},
                    "fit_reason": {"type": "string"},
                    "geography": {"type": "string"},
                    "capability": {"type": "string"},
                },
                "required": ["company_name", "website", "fit_reason", "geography", "capability"],
            },
        }
    },
    "required": ["companies"],
}

QUERY = "Whirlpool appliance price increase, tariff exposure or supply changes affecting dishwashers"


def dump(name, obj, seconds):
    def default(o):
        if is_dataclass(o):
            return asdict(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)

    path = OUT / f"{name}.json"
    path.write_text(json.dumps(obj, default=default, indent=2))
    print(f"[{name}] {seconds:.1f}s -> {path}")


def summarize(resp):
    for r in resp.results:
        print(f"  - {r.published_date or '????'} | {r.title[:80]} | {r.url}")
    if resp.output:
        print("  output:", json.dumps(resp.output.content, indent=2)[:1500])
    print("  cost:", resp.cost_dollars)


def run_search():
    t = time.time()
    resp = exa.search(
        QUERY, type="auto", num_results=8, system_prompt=SYSTEM_PROMPT,
        output_schema=RISK_SCHEMA, contents={"highlights": True},
    )
    dump("search", resp, time.time() - t)
    summarize(resp)


def run_snapshot():
    t = time.time()
    resp = exa.search(
        QUERY, type="auto", num_results=8, system_prompt=SYSTEM_PROMPT,
        output_schema=RISK_SCHEMA,
        contents={"highlights": True, "snapshot_as_of": "2026-06-10T00:00:00Z"},
    )
    dump("snapshot", resp, time.time() - t)
    summarize(resp)
    for r in resp.results:
        print("  snapshot_at:", r.snapshot_at, r.url)


def run_company():
    t = time.time()
    resp = exa.search(
        "manufacturers of premium built-in dishwashers selling through North American retailers",
        type="deep", category="company", num_results=8,
        system_prompt=(
            "Exclude Whirlpool (incl. KitchenAid, Maytag), GE Appliances (Haier), LG and "
            "Bosch/BSH: they are current vendors. Prefer official company pages."
        ),
        output_schema=COMPANY_SCHEMA, contents={"highlights": True},
    )
    dump("company", resp, time.time() - t)
    summarize(resp)
    for r in resp.results:
        print("  entities:", (r.entities or [None])[0])


def run_agent():
    companies = json.loads((OUT / "company.json").read_text())["output"]["content"]["companies"][:3]
    t = time.time()
    run = exa.agent.runs.create(
        query=(
            "Evaluate each supplied company as a potential supplier of premium dishwashers for a "
            "large US retailer: product fit, manufacturing footprint serving North America, capacity "
            "indicators, and material sourcing risks including recent developments."
        ),
        input={"data": [{"company_name": c["company_name"], "website": c["website"]} for c in companies]},
        output_schema={
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array", "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string"},
                            "product_fit": {"type": "string"},
                            "geography": {"type": "string"},
                            "capacity_indication": {"type": "string"},
                            "key_risks": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
                        },
                        "required": ["company_name", "product_fit", "geography", "capacity_indication", "key_risks"],
                    },
                }
            },
            "required": ["candidates"],
        },
        effort=os.environ.get("EXA_AGENT_EFFORT", "medium"),
    )
    print("  run id:", run.id)
    finished = exa.agent.runs.poll_until_finished(run.id, poll_interval=3000, timeout_ms=600000)
    dump("agent", finished, time.time() - t)
    print("  status:", finished.status, "cost:", finished.cost_dollars)
    if finished.output:
        print(json.dumps(finished.output.structured, indent=2)[:2000])


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"search": run_search, "snapshot": run_snapshot, "company": run_company, "agent": run_agent}
    for name in (["search", "snapshot", "company"] if which == "all" else [which]):
        try:
            steps[name]()
        except Exception as e:  # spike: report and keep going
            print(f"[{name}] FAILED: {type(e).__name__}: {e}")
