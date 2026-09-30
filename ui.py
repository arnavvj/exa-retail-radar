import json
from html import escape
from pprint import pformat
from textwrap import indent

import pandas as pd
import streamlit as st

import internal

RISK_COLORS = {"High": "red", "Medium": "orange", "Low": "green"}
CSS = """<style>
[class*="st-key-decide"] button {background:#FF9900; border-color:#FF9900; color:#111;}
[class*="st-key-decide"] button:hover {background:#E68A00; border-color:#E68A00; color:#111;}
[data-testid="stPopoverBody"] {min-width:min(760px, 90vw); max-height:75vh; overflow:auto;}
sup a {text-decoration:none; font-weight:600; margin-left:1px;}
</style>"""


def clean(text, limit=None):
    text = " ".join(line.lstrip("#>*- ").strip() for line in str(text or "").splitlines())
    text = escape(text, quote=False).replace("$", "\\$").replace("~", "\\~").replace("_", "\\_")
    return text[:limit] + "…" if limit and len(text) > limit else text


def style():
    st.markdown(CSS, unsafe_allow_html=True)


def badge(res):
    if res["source"] == "live":
        st.markdown(f":green-badge[LIVE] fetched {res['fetched_at']} · {res['latency_s']}s")
    elif res["source"] == "cached":
        st.markdown(f":blue-badge[CACHED] originally fetched live {res['fetched_at']}")
    if res.get("error"):
        st.error(f"Exa request failed: {res['error']}")


def python_snippet(req):
    p = dict(req["python"])
    first, value = next(iter(p.items()))
    p.pop(first)
    positional = req["call"] in ("exa.search", "exa.get_contents", "exa.monitors.create")
    lead = repr(value) if positional else f"{first}={value!r}"
    args = [lead] + [f"{k}={pformat(v, width=76, sort_dicts=False)}" for k, v in p.items()]
    return f"{req['call']}(\n" + "".join(indent(a, "    ") + ",\n" for a in args) + ")"


def call_body(res):
    req = res["request"]
    py, rest = st.tabs(["Python (exa-py)", "REST"])
    py.code(python_snippet(req), language="python")
    rest.caption(req["rest"]["endpoint"])
    rest.code(json.dumps(req["rest"]["body"], indent=2), language="json")
    data = res.get("data") or {}
    meta = [f"run {data['id']}" if data.get("id") else "",
            f"reported cost \\${data['cost']:.3f}" if data.get("cost") is not None else ""]
    st.caption(" · ".join(m for m in meta if m))


def row():
    return st.container(horizontal=True, vertical_alignment="bottom", gap="medium")


def section(title, *calls, controls=None, note=None, level="header"):
    r = row()
    getattr(r, level)(title, width="content")
    if controls:
        with r:
            controls()
    calls = [c for c in calls if c and c.get("request")]
    if calls:
        with r.popover("↗", help="View the Exa API call"):
            if note:
                st.caption(note)
            for i, c in enumerate(calls):
                if i:
                    st.divider()
                st.markdown(f"**{c['request']['call']}**")
                call_body(c)


def ref_numbers(results):
    return {r["url"]: i + 1 for i, r in enumerate(results)}


def sup(grounding, prefix, refs):
    links = {}
    for g in grounding or []:
        if g["field"].startswith(prefix):
            for c in g["citations"]:
                refs.setdefault(c["url"], len(refs) + 1)
                links[c["url"]] = f"{c['title'] or c['url']} · {g['confidence']} confidence"
    return "".join(f'<sup><a href="{u}" target="_blank" title="{escape(t).replace('$', 'USD ')}">[{refs[u]}]</a></sup>'
                   for u, t in links.items())


def risk_card(output, refs):
    if not output:
        st.warning("No structured output returned.")
        return
    c, g = output["content"], output["grounding"]
    level = c.get("risk_level", "?")
    st.markdown(f":{RISK_COLORS.get(level, 'gray')}-badge[{level} risk]")
    st.markdown(f"**{clean(c.get('primary_signal'))}**{sup(g, 'primary_signal', refs)}", unsafe_allow_html=True)
    lo, hi = c.get("price_change_low_pct"), c.get("price_change_high_pct")
    change = "n/a" if lo is None and hi is None else f"{lo}%" if hi in (None, lo) else f"{lo}% to {hi}%"
    st.markdown(f"**Announced price change:** {change}{sup(g, 'price_change', refs)} · "
                f"**Effective:** {clean(c.get('effective_date')) or 'n/a'}{sup(g, 'effective_date', refs)}",
                unsafe_allow_html=True)
    st.markdown(f"**Business implication:** {clean(c.get('business_implication'))}"
                f"{sup(g, 'business_implication', refs)}", unsafe_allow_html=True)
    if c.get("signals"):
        st.markdown("**Signals across the supply chain**\n" + "\n".join(
            f"- :gray-badge[{s['layer']}] {clean(s['signal'])} *({s['basis'].lower()})*{sup(g, f'signals[{i}]', refs)}"
            for i, s in enumerate(c["signals"])), unsafe_allow_html=True)


def origins(content):
    return ", ".join(dict.fromkeys(s["layer"] for s in content.get("signals") or [])) or "—"


def current_stack(profile, today):
    status, flags = internal.kpi_status(profile)
    feed = internal.third_party_feed(profile, today)
    st.markdown("**Without Exa · current stack** :gray-badge[SYNTHETIC]")
    st.caption(f"{profile['relationship']} · upstream: {', '.join(profile['upstream'])}")
    st.caption(f"**What we buy:** {profile['sku_count']} SKUs, including " +
               "; ".join(i.split(" · ")[1] for i in profile["top_items"]))
    a, b = st.columns(2)
    a.metric("Internal KPI status", status, help="Rule: on-time ≥ 95%, fill rate ≥ 96%, cost Δ ≤ 1%")
    b.metric("3P risk rating", feed["rating"], help="Simulated monthly third-party supplier risk feed")
    st.caption(f"On-time {profile['on_time_delivery']}% · fill rate {profile['fill_rate']}% · "
               f"cost Δ {profile['internal_cost_delta']}% · " + ("; ".join(flags) or "all KPIs within thresholds"))
    st.caption(f"3P feed last refreshed {feed['last']:%b %d, %Y} · next refresh {feed['next']:%b %d, %Y} · "
               f"{feed['age_days']} days old today")


def evidence(results, refs=None, limit=8, new=False):
    for r in results[:limit]:
        n = f"[{refs[r['url']]}] " if refs and r["url"] in refs else ":green-badge[NEW] " if new else ""
        st.markdown(f"{n}**[{clean(r['title'])}]({r['url']})**  \n`{r['domain']}` · {r['date'] or 'undated'}")
        if r["highlights"]:
            st.caption(f"“{clean(r['highlights'][0], 320)}”")


def candidates_table(cands, key, default):
    rows = [{"Vet": c["company_name"] in default, "Company": c["company_name"],
             "Supply-chain role": c["supply_chain_role"], "Brands carried": c.get("brands_carried", ""),
             "Product fit": c["product_capability"], "Geography": c["geography"],
             "Retailer-serving capability": c["retailer_serving_capability"], "Why it fits": c["fit_reason"],
             "Founded": (c["facts"] or {}).get("founded"), "Employees": (c["facts"] or {}).get("employees"),
             "HQ": (c["facts"] or {}).get("hq"), "Evidence": c["evidence"][0]} for c in cands]
    wide = st.column_config.TextColumn(width="large")
    edited = st.data_editor(pd.DataFrame(rows), key=key, hide_index=True, disabled=list(rows[0])[1:],
                            column_config={"Vet": st.column_config.CheckboxColumn(width="small"),
                                           "Product fit": wide, "Retailer-serving capability": wide,
                                           "Why it fits": wide, "Employees": st.column_config.NumberColumn(format="%d"),
                                           "Evidence": st.column_config.LinkColumn()})
    return [c for c, keep in zip(cands, edited["Vet"]) if keep]


VET_LINES = [("Product fit", "product_fit"), ("Manufacturing", "manufacturing_capability"),
             ("Distribution", "distribution_capability"), ("Coverage", "geographic_coverage"),
             ("Scale", "scale_indicators"), ("Retail relationships", "retail_relationships"),
             ("Recent developments", "recent_developments")]
VET_LISTS = [("⚠️ Material risks", "material_risks"), ("✅ Publicly demonstrated", "publicly_demonstrated"),
             ("💭 Reasonable inferences", "reasonable_inferences"),
             ("☎️ Validate with the supplier", "needs_supplier_validation")]


def vet_card(col, c, grounding, p, highlights):
    refs = {}
    with col.container(border=True, height=760):
        st.markdown(f"#### {clean(c['company_name'])}\n:blue-badge[{c['supply_chain_role']}]")
        for label, field in VET_LINES:
            if c.get(field):
                st.markdown(f"**{label}:** {clean(c[field])}{sup(grounding, f'{p}.{field}', refs)}",
                            unsafe_allow_html=True)
        for label, field in VET_LISTS:
            if c.get(field):
                st.markdown(f"**{label}**{sup(grounding, f'{p}.{field}', refs)}\n" +
                            "\n".join(f"- {clean(x)}" for x in c[field]), unsafe_allow_html=True)
        hits = [(r, h) for r in ((highlights or {}).get("data") or {}).get("results", []) for h in r["highlights"]]
        if hits:
            st.markdown("**Evidence excerpts** · :blue-badge[Exa highlights]")
            for r, h in hits:
                st.markdown(f"> {clean(h, 400)}  \n> — [{r['domain']}]({r['url']})")


def decision_table(cands):
    wide = st.column_config.TextColumn(width="large")
    st.dataframe(pd.DataFrame([{"Candidate": c["company_name"], "Role": c["supply_chain_role"],
                                "Evidence it can serve us": "; ".join(c["publicly_demonstrated"]),
                                "Validate with the supplier": "; ".join(c["needs_supplier_validation"])}
                               for c in cands]), hide_index=True,
                 column_config={"Evidence it can serve us": wide, "Validate with the supplier": wide})
