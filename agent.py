import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import exa_client as ex

DATA = Path(__file__).parent / "data"
SUPPLIERS = json.loads((DATA / "suppliers.json").read_text())
SCENARIOS = json.loads((DATA / "scenarios.json").read_text())

SOURCE_RULES = (
    "Prefer primary company sources, SEC filings and reputable industry/news sources. "
    "Avoid duplicate reporting of the same event. Do not state unverified allegations as facts. "
    "If a field cannot be verified from the sources, return null rather than guessing."
)

LAYERS = ["Direct supplier", "Manufacturer", "Distributor / logistics", "Upstream component / material",
          "Industry-wide"]
ROLES = ["Manufacturer", "Distributor", "Wholesaler", "Importer", "Vertically Integrated Supplier", "Other"]


def string(nullable=False):
    return {"type": ["string", "null"]} if nullable else {"type": "string"}


def strings(n):
    return {"type": "array", "maxItems": n, "items": {"type": "string"}}


def obj_list(n, props, required=None):
    return {"type": "array", "maxItems": n, "items": {"type": "object", "properties": props,
                                                      "required": required or list(props)}}


RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "primary_signal": string(),
        "price_change_low_pct": {"type": ["number", "null"], "description":
                                 "The direct supplier's own announced price change on this product, in percent "
                                 "(negative for decreases). Null if none. Not commodity, tariff or share figures."},
        "price_change_high_pct": {"type": ["number", "null"]},
        "effective_date": string(nullable=True),
        "business_implication": string(),
        "signals": obj_list(5, {"layer": {"type": "string", "enum": LAYERS}, "signal": string(),
                                "basis": {"type": "string", "enum": ["Direct evidence", "Inference"]}}),
    },
    "required": ["risk_level", "primary_signal", "business_implication", "signals"],
}

COMPANY_SCHEMA = {"type": "object", "required": ["companies"], "properties": {"companies": obj_list(8, {
    "company_name": string(), "website": string(), "supply_chain_role": {"type": "string", "enum": ROLES},
    "fit_reason": string(), "product_capability": string(), "geography": string(),
    "retailer_serving_capability": string(), "brands_carried": string()})}}

VET_SCHEMA = {"type": "object", "required": ["candidates"], "properties": {"candidates": obj_list(3, {
    "company_name": string(), "supply_chain_role": {"type": "string", "enum": ROLES}, "product_fit": string(),
    "manufacturing_capability": string(True), "distribution_capability": string(True),
    "geographic_coverage": string(), "scale_indicators": string(), "retail_relationships": string(True),
    "recent_developments": string(True), "material_risks": strings(3), "publicly_demonstrated": strings(3),
    "reasonable_inferences": strings(3), "needs_supplier_validation": strings(3),
}, required=["company_name", "supply_chain_role", "product_fit", "geographic_coverage", "scale_indicators",
             "material_risks", "publicly_demonstrated", "reasonable_inferences", "needs_supplier_validation"])}}


def suppliers_in(category):
    return [s for s in SUPPLIERS if s["category"] == category]


def supplier_profile(name):
    return next((s for s in SUPPLIERS if s["name"] == name), None)


def risk_query(supplier, product, focus):
    return f"{supplier} and its supply chain: {focus} affecting {product}"


def risk_rules(supplier, product):
    p = supplier_profile(supplier) or {"relationship": "direct supplier, role unknown", "upstream": ["unknown"]}
    return (f"We are a large North American retailer. {supplier} is our {p['relationship']} of {product}; "
            f"known upstream dependencies: {', '.join(p['upstream'])}. Look for signals at every supply-chain "
            "layer: the direct supplier, manufacturers, distributors and logistics, upstream components and "
            "materials, and industry-wide shifts. Prioritize what could affect product cost, availability, "
            "lead time, capacity or continuity of supply. Label each signal as direct evidence or inference. "
            + SOURCE_RULES)


def investigate(supplier, product, focus, live=False):
    return ex.search(risk_query(supplier, product, focus), system_prompt=risk_rules(supplier, product),
                     output_schema=RISK_SCHEMA, live=live)


def sweep(suppliers, focus, live=False):
    with ThreadPoolExecutor(len(suppliers)) as pool:
        results = pool.map(lambda s: investigate(s["name"], s["product"], focus, live), suppliers)
    return dict(zip([s["name"] for s in suppliers], results))


def validate(supplier, product, focus, as_of, live=False):
    return ex.search(risk_query(supplier, product, focus), system_prompt=risk_rules(supplier, product),
                     output_schema=RISK_SCHEMA, live=live,
                     contents={"highlights": True, "snapshot_as_of": f"{as_of}T00:00:00Z"})


def since(supplier, product, focus, as_of, live=False):
    return ex.search(risk_query(supplier, product, focus), system_prompt=risk_rules(supplier, product),
                     start_published_date=f"{as_of}T00:00:00Z", live=live)


def newer_results(since_res, inv, as_of):
    fresh = ((since_res or {}).get("data") or {}).get("results", [])
    older = [r for r in ((inv or {}).get("data") or {}).get("results", []) if r["date"] > str(as_of)]
    merged = {r["url"]: r for r in fresh + older}
    return sorted(merged.values(), key=lambda r: r["date"], reverse=True)


def current_suppliers(supplier, category):
    return list(dict.fromkeys([s["name"] for s in suppliers_in(category)] + [supplier]))


SEARCH_TYPES = ["instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"]


def discover(supplier, product, category, search_type="deep", live=False):
    names = current_suppliers(supplier, category)
    res = ex.search(f"companies that could become alternative direct suppliers of {product} "
                    "to large North American retailers",
                    type=search_type, category="company", output_schema=COMPANY_SCHEMA, live=live,
                    system_prompt="Candidates may be manufacturers selling directly to retailers, distributors or "
                                  "wholesalers, importers, or vertically integrated suppliers. Set each company's "
                                  "supply_chain_role only from retrieved evidence; use Other when unclear. Weigh "
                                  "product capability, manufacturing and distribution capability, geography, "
                                  "ability to serve large retailers, scale and current market presence. "
                                  f"Do not return these companies, which are already our suppliers: {', '.join(names)}. "
                                  "Other companies that sell their brands or products are allowed. List the brands each "
                                  "candidate carries. Prefer official company pages.")
    if res.get("data"):
        res["candidates"] = shortlist(res["data"], names)
    return res


def shortlist(data, names):
    blocked = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I)
    facts = {}
    for r in data["results"]:
        if r["company"]:
            facts.setdefault(first_word(r["company"]["name"]), r)
    output = data["output"] or {"content": {}, "grounding": []}
    out, seen = [], set()
    for i, c in enumerate(output["content"].get("companies", [])):
        key = first_word(c["company_name"])
        if blocked.search(c["company_name"]) or key in seen:
            continue
        seen.add(key)
        cited = [ct["url"] for g in output["grounding"] if g["field"].startswith(f"companies[{i}]")
                 for ct in g["citations"]]
        hit = facts.get(key)
        out.append({**c, "facts": hit["company"] if hit else None,
                    "evidence": list(dict.fromkeys(cited)) or [hit["url"] if hit else c["website"]]})
    return out


def diverse_pick(cands, n=3):
    picks = list({c["supply_chain_role"]: c["company_name"] for c in reversed(cands)}.values())[::-1][:n]
    return picks + [c["company_name"] for c in cands if c["company_name"] not in picks][:n - len(picks)]


def first_word(name):
    return name.split()[0].lower()


def vet_request(product, candidates):
    query = (f"Evaluate whether each supplied company could realistically serve as an alternative direct supplier "
             f"of {product} for a large North American retailer. Determine its supply-chain role, product fit, "
             "manufacturing and distribution capability where applicable, geographic coverage, scale and capacity "
             "indicators, relevant retail relationships, recent developments and material risks. Separate what the "
             "company publicly demonstrates, what can reasonably be inferred, and what needs direct supplier "
             "validation.")
    data = [{k: c[k] for k in ("company_name", "website", "supply_chain_role")} for c in candidates]
    python = {"query": query, "input": {"data": data}, "output_schema": VET_SCHEMA,
              "effort": os.getenv("EXA_AGENT_EFFORT", "medium")}
    return {"call": "exa.agent.runs.create", "python": python,
            "rest": {"endpoint": "POST https://api.exa.ai/agent/runs",
                     "body": {**{k: v for k, v in python.items() if k != "output_schema"},
                              "outputSchema": VET_SCHEMA}}}


def split_vetting(run, names, product, live=False):
    out = {}
    cands = run["data"]["structured"]["candidates"]
    for i, cand in enumerate(cands):
        name = next((n for n in names if first_word(n) == first_word(cand["company_name"])),
                    names[i] if i < len(names) else cand["company_name"])
        prefix = f"structured.candidates[{i}]"
        urls = list(dict.fromkeys(c["url"] for g in run["data"]["grounding"] if g["field"].startswith(prefix)
                                  for c in g["citations"]))
        query = (f"{cand['company_name']} {product} supply capability: manufacturing, distribution, capacity, "
                 "retail customers and risks")
        out[name] = {"cand": cand, "run": run, "prefix": prefix,
                     "hl": ex.contents(urls[:4], query, live) if urls else None}
    return out


