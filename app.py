import time
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import agent
import auth
import copilot
import exa_client as ex
import impact
import inbox
import internal
import ui

st.set_page_config(page_title="Supplier Risk Radar", page_icon="📡", layout="wide")
ui.style()
auth.require_login()
ss = st.session_state
CATEGORIES = list(dict.fromkeys(s["category"] for s in agent.SUPPLIERS))
today = date.today()


def log(msg):
    if msg not in ss.setdefault("trace", []):
        ss.trace.append(msg)


def content(res):
    out = ((res or {}).get("data") or {}).get("output")
    return out["content"] if out else {}


def reset():
    for k in ["snaps", "disc", "vetted", "vet_job", "vet_error", "decision", "copilot_answer", "trace"]:
        ss.pop(k, None)


def on_category():
    ss.supplier = agent.suppliers_in(ss.get("category", CATEGORIES[0]))[0]["name"]
    reset()


def on_scenario():
    s = ss.get("scenario") or agent.SCENARIOS[0]
    ss.category = s["category"] if s["as_of"] else ss.get("category", CATEGORIES[0])
    ss.as_of = date.fromisoformat(s["as_of"]) if s["as_of"] else today - timedelta(days=30)
    on_category()


if "scenario" not in ss:
    ss.scenario = agent.SCENARIOS[0]
    on_scenario()
for k in ("category", "supplier", "as_of"):
    ss[k] = ss[k]

st.title("Supplier Risk & Discovery Radar")
st.caption("External supply-chain intelligence for retail sourcing agents · *Which of our suppliers is becoming a "
           "risk, what is happening upstream, and who could we source from instead?*")
st.markdown("**Detect** · Exa Search → **Trace upstream** · Exa Search → **Validate** · Exa Snapshot → "
            "**Discover** · Exa Company Search → **Vet** · Exa Agent → **Contact** · Exa People Search → "
            "**Watch** · Exa Monitors")
st.caption("Exa is not just the search box inside the agent. It is the external intelligence layer that lets the "
           "agent move from a supplier-risk signal to an actionable sourcing workflow.")

with ui.row():
    st.selectbox("Scenario", agent.SCENARIOS, key="scenario", on_change=on_scenario,
                 format_func=lambda s: s["name"] if s["category"] == "Any"
                 else f"{s['category']} · {s['name']} (real event: {s['event']})", width=720)
    live = st.toggle("Run live (bypass cache)")

scenario, focus = ss.scenario, ss.scenario["focus"]
suppliers = agent.suppliers_in(ss.category)
sweep = ss.setdefault("sweeps", {}).get((scenario["name"], ss.category), {})

st.divider()
supplier = ss.supplier
profile = agent.supplier_profile(supplier)
product = profile["product"]
inv = sweep.get(supplier)


def watchlist_controls():
    st.selectbox("Category", CATEGORIES, key="category", on_change=on_category, disabled=bool(scenario["as_of"]),
                 width=240)
    st.button("📡 Scan the web with Exa", type="primary", on_click=lambda: ss.update(scan=True))


ui.section("Supplier watchlist", controls=watchlist_controls)
if ss.pop("scan", False):
    with st.spinner("Searching the public web across each supplier's supply chain…"):
        ss.sweeps[(scenario["name"], ss.category)] = agent.sweep(suppliers, focus, live)
    st.rerun()


def watch_row(s):
    c = content(sweep.get(s["name"]))
    return {"Supplier": s["name"], "Relationship": s["relationship"], "Brands": ", ".join(s["brands"]),
            "SKUs": s["sku_count"], "Internal KPI status": internal.kpi_status(s)[0],
            "3P rating": f"{s['third_party_rating']} (as of {internal.third_party_feed(s, today)['last']:%b %d})",
            "External risk (Exa)": c.get("risk_level", "—"), "Risk origin (Exa)": ui.origins(c),
            "External signal (Exa)": c.get("primary_signal", "Not scanned"),
            "Annual spend": impact.money(s["annual_spend"])}


st.dataframe(pd.DataFrame([watch_row(s) for s in suppliers]), hide_index=True, height=180,
    column_config={"External signal (Exa)": st.column_config.TextColumn(width=900),
                   "Risk origin (Exa)": st.column_config.TextColumn(width=320)})
st.caption(":gray-badge[SYNTHETIC] internal KPIs and 3P ratings are demo data · Exa columns come from Exa Search")

if inv:
    log("Swept the public web for every supplier (Exa Search)")
    log(f"Investigated {supplier} and its upstream supply chain")
    ui.section(f"Investigate {supplier} across its supply chain", inv, level="subheader",
               note=f"One Exa Search per supplier, run in parallel ({len(suppliers)} calls). Showing {supplier}'s call.",
               controls=lambda: st.selectbox("Direct supplier", [s["name"] for s in suppliers], key="supplier",
                                             width=200))
    results = agent.rank_evidence(inv["data"]["results"], inv["data"]["output"]) if inv.get("data") else []
    refs = ui.ref_numbers(results)
    left, right = st.columns([1, 2], border=True)
    with left:
        ui.current_stack(profile, today)
    with right:
        st.markdown("**With Exa · external supply-chain view**")
        ui.badge(inv)
        if inv.get("data"):
            ui.risk_card(inv["data"]["output"], refs)
    if inv.get("data"):
        feed = internal.third_party_feed(profile, today)
        newest = max((r["date"] for r in results if r["date"]), default="n/a")
        st.info(f"**The latency gap:** the 3P feed still rates {supplier} **{feed['rating']}** (monthly refresh, last "
                f"{feed['last']:%b %d}). Exa rates it **{content(inv).get('risk_level', 'n/a')}** today from "
                f"{len(results)} public sources, the newest published {newest}.")
        with st.expander(f"Evidence · {len(results)} sources"):
            ui.evidence(results, refs)

snap_key = (supplier, str(ss.as_of))
snap = ss.setdefault("snaps", {}).get(snap_key)
if inv and inv.get("data"):
    st.divider()
    ui.section("Validate with Exa Snapshot", snap, (snap or {}).get("since"),
               note="Left pane: Snapshot replay (contents.snapshot_as_of). Right pane: live search limited to pages "
                    "published after the cutoff (start_published_date).", controls=lambda: st.date_input(
        "Point-in-time date", key="as_of", min_value=today - timedelta(days=150),
        max_value=today, width=180))
    as_of = ss.as_of
    st.caption("Exa Snapshot serves each page as stored at or before the cutoff. It bounds content, not ranking: "
               "historical web-content validation, not a reconstruction of past search results. Research preview.")
    st.markdown(f"**What could we have known on {as_of:%b %d, %Y}?** {scenario['why_date']} "
                "The date comes from the scenario and can be changed here, within Snapshot's 5-month window.")
    if not snap and st.button("⏪ Replay the web with Exa Snapshot", type="primary"):
        with st.spinner("Replaying the web as of the cutoff, and searching what's been published since…"):
            ss.snaps[snap_key] = {**agent.validate(supplier, product, focus, as_of, live),
                                  "since": agent.since(supplier, product, focus, as_of, live)}
        st.rerun()
    if snap:
        ui.badge(snap)
    if snap and snap.get("data"):
        log(f"Validated the signal as of {as_of} (Exa Snapshot)")
        sresults = agent.rank_evidence(snap["data"]["results"], snap["data"]["output"], as_of)
        srefs = ui.ref_numbers(sresults)
        st.markdown(f":violet-badge[POINT-IN-TIME WEB REPLAY · {as_of:%b %d, %Y}]")
        ui.risk_card(snap["data"]["output"], srefs)
        a, b = st.columns(2, border=True)
        with a:
            st.markdown(f"**Evidence available on {as_of:%b %d}**")
            ui.evidence(sresults, srefs)
        with b:
            newer = agent.newer_results(snap.get("since"), inv, as_of)
            st.markdown(f"**Published since {as_of:%b %d} · live Exa Search** :green-badge[NOT IN THE REPLAY]")
            st.caption("What the sourcing team could not have seen on the cutoff date.")
            if newer:
                ui.evidence(newer, new=True)
            else:
                st.caption(f"No new public evidence published since {as_of:%b %d, %Y}.")
        c = content(snap)
        label = impact.exposure_label(profile["annual_spend"], c.get("price_change_low_pct"),
                                      c.get("price_change_high_pct"))
        if label:
            kind = "savings opportunity" if label.startswith("-") else "exposure"
            st.markdown(f"**Illustrative {kind}: {label}**".replace("$", "\\$"))
            st.caption(f":orange-badge[DERIVED] \\{impact.money(profile['annual_spend'])} synthetic annual spend × "
                       "announced price change (point-in-time evidence). Illustrative, not a forecast.")

disc, picks = ss.get("disc"), []
if inv and inv.get("data"):
    st.divider()
    def discovery_controls():
        st.selectbox("Search type", agent.SEARCH_TYPES, index=agent.SEARCH_TYPES.index("deep"), key="search_type",
                     width=170, help="Exa Search type: instant and fast favor speed; deep and deep-reasoning run "
                                     "multi-step research for more thorough results.")
        st.button("🔎 Find alternative suppliers with Exa company search", type="primary",
                  on_click=lambda: ss.update(discover=True))

    ui.section("Alternative suppliers", disc, controls=discovery_controls)
    st.markdown(f":blue-badge[LIVE COMPANY DISCOVERY] Who could realistically become an alternative direct "
                f"supplier of {product}? Manufacturers, distributors, wholesalers or importers, with the role "
                "grounded in public evidence.")
    if ss.pop("discover", False):
        with st.spinner(f"Exa company search (type={ss.search_type})…"):
            ss.disc = agent.discover(product, ss.category, ss.search_type, live)
        st.rerun()
    if disc:
        ui.badge(disc)
    if disc and disc.get("candidates"):
        log("Discovered alternative direct-supplier candidates (Exa Company Search)")
        picks = ui.candidates_table(disc["candidates"], f"cands-{disc['fetched_at']}",
                                    agent.diverse_pick(disc["candidates"]))
        if len(picks) > 3:
            st.warning("Select up to 3 companies to vet.")

vetted, shown = ss.setdefault("vetted", {}), []
if picks:
    st.divider()
    picks = picks[:3]
    todo = [p for p in picks if p["company_name"] not in vetted]
    shown = [vetted[p["company_name"]] for p in picks if p["company_name"] in vetted]
    runs = list({v["run"]["data"]["id"]: v["run"] for v in shown}.values())
    ui.section("Vet the shortlist", *runs, *[v["hl"] for v in shown if v["hl"]],
               *[v["people"] for v in shown if v.get("people")],
               note="Exa Agent vets each company; Contents highlights pull evidence excerpts; people search finds "
                    "current sales leaders to contact. Already-vetted companies are reused.")
    if todo and "vet_job" not in ss and st.button(
            f"🧪 Vet {len(todo)} {'new ' if shown else ''}candidate{'s' if len(todo) > 1 else ''} with Exa Agent",
            type="primary"):
        req = agent.vet_request(product, todo)
        res = None if live else ex.agent_cached(req)
        if not res:
            try:
                ss.vet_job = {**ex.agent_start(req), "names": [p["company_name"] for p in todo]}
            except Exception as e:
                res = {"source": "error", "error": str(e), "request": req}
        if res:
            ss.vet_result = (res, [p["company_name"] for p in todo])
    if "vet_job" in ss:
        job = ss.vet_job
        with st.status("Exa Agent is assessing each candidate as a direct supplier…") as box:
            while (res := ex.agent_poll(job))["status"] in ("queued", "running"):
                box.update(label=f"Exa Agent · {res['status']} · {time.time() - job['started']:.0f}s")
                time.sleep(3)
            box.update(label=f"Exa Agent · {res['status']}", state="complete" if res.get("data") else "error")
        ss.vet_result = (res, job["names"])
        del ss.vet_job
    if "vet_result" in ss:
        res, names = ss.pop("vet_result")
        if res.get("data"):
            vetted.update(agent.split_vetting(res, names, product, live))
            st.rerun()
        ss.vet_error = res
    if ss.get("vet_error"):
        ui.badge(ss.vet_error)
    if shown:
        log("Vetted candidates and found who to contact (Exa Agent + highlights + people search)")
        ui.badge(shown[0]["run"])
        for col, v in zip(st.columns(3), shown):
            ui.vet_card(col, v["cand"], v["run"]["data"]["grounding"], v["prefix"], v["hl"], v.get("people"))

if shown:
    st.divider()
    answer = ss.get("copilot_answer")
    calls = ((answer or {}).get("data") or {}).get("exa_calls", [])
    ui.section("Ask your sourcing copilot",
               *([copilot.openai_request(answer["request"]["question"], answer["request"]["context"])] + calls
                 if answer and answer.get("request") else []),
               note=f"1) Your OpenAI model ({copilot.MODEL}) gets Exa as a tool via exa.openai.web_search(). "
                    "2) The exa.search calls it chose to make. 3) A second OpenAI call with the Exa results "
                    "writes the answer.")
    st.caption("Bring your own agent: an OpenAI model does the reasoning, Exa is its web search tool. "
               "One question at a time.")
    with st.form("copilot_form", border=False, clear_on_submit=True):
        question = st.text_input("Question", label_visibility="collapsed", max_chars=copilot.MAX_QUESTION,
                                 placeholder="Which candidate could ship before Black Friday, and what should we verify first?")
        asked = st.form_submit_button("Ask", type="primary", disabled=not copilot.has_key())
    if not copilot.has_key():
        st.caption("Set OPENAI_API_KEY to enable the copilot.")
    used = ss.get("copilot_count", 0)
    if asked:
        question, problem = copilot.check(question, used)
        if problem:
            st.warning(problem)
    if asked and not problem:
        context = copilot.context(profile, suppliers, content(inv).get("primary_signal", "n/a"),
                                  [v["cand"] for v in shown])
        with st.spinner("Your model is thinking and searching with Exa…"):
            ss.copilot_answer = copilot.ask(question, context, live)
        ss.copilot_count = used + 1
        st.rerun()
    if answer:
        ui.badge(answer)
    if answer and answer.get("data"):
        log("Answered a sourcing question (OpenAI + Exa search tool)")
        st.markdown(f"**Q:** {ui.clean(answer['request']['question'])}")
        st.markdown(answer["data"]["answer"].replace("$", "\\$"))
        links = [r for c in answer["data"]["exa_calls"] for r in c["results"]]
        if links:
            st.caption(f"{len(answer['data']['exa_calls'])} Exa search(es) · sources: " + " · ".join(
                f"[{ui.clean(r['title'], 50)}]({r['url']})" for r in links[:6]))

if shown:
    st.divider()
    st.subheader("Sourcing decision")
    st.markdown(f"*If {supplier} becomes materially constrained, which companies could we investigate as "
                "alternative sources, what role would each play in the supply chain, and what evidence supports "
                "their ability to serve us?*  \n:orange-badge[INTERNAL WORKFLOW]")
    ui.decision_table([v["cand"] for v in shown])
    actions = ["Open Supplier Review", "Route to Pricing", "Route to Compliance", "Keep Watching"]
    for i, (col, action) in enumerate(zip(st.columns(4), actions)):
        if col.button(action, key=f"decide_{i}", width="stretch"):
            ss.decision = action
    if ss.get("decision"):
        log("Prepared sourcing handoff")
        st.success(f"**{ss.decision}** handed to the sourcing team. "
                   "No procurement or pricing change was executed automatically.")

if shown and ss.get("decision") == "Keep Watching":
    st.divider()
    webhook, query = inbox.endpoint(), agent.risk_query(supplier, product, focus)
    mon = ex.saved_monitor(supplier)
    ui.section("Keep watching", mon or {"request": ex.monitor_request(supplier, query, webhook)})
    if not webhook and st.button("Create demo webhook endpoint (Svix Play)", type="primary"):
        inbox.create_endpoint()
        st.rerun()
    if not mon and webhook and st.button(f"Start daily Exa Monitor for {supplier}", type="primary"):
        ex.create_monitor(supplier, query, webhook)
        st.rerun()
    if mon:
        log(f"Monitoring {supplier} daily (Exa Monitors)")
        url = mon["request"]["python"]["params"]["webhook"]["url"]
        st.markdown(f"Monitoring: :green-badge[Active] `{mon['id']}` since {mon['created']} · delivers to `{url}`")
        st.markdown("**Webhook inbox** · what Exa POSTed to our endpoint, with the `Exa-Signature` checked "
                    "against the monitor's signing secret")
        if st.button("↻ Refresh inbox", type="primary"):
            ss.inbox = inbox.deliveries(url, mon["id"])
        for d in ss.get("inbox", []):
            ok = inbox.verify(d["raw"], d["signature"], mon.get("secret") or "")
            data = d["body"].get("data", {})
            output = data.get("output") or {}
            with st.container(border=True):
                st.markdown(f"`{d['body'].get('type', 'unknown event')}` · received {d['received']} UTC · "
                            + (":green-badge[Signature verified]" if ok else ":red-badge[Signature not verified]")
                            + f" · status {data.get('status', 'n/a')}")
                for r in output.get("results", [])[:5]:
                    st.markdown(f"- [{ui.clean(r.get('title'))}]({r.get('url')})")
                if isinstance(output.get("content"), str):
                    st.caption(ui.clean(output["content"], 400))
        if "inbox" in ss and not ss.inbox:
            st.caption("No deliveries yet. The first run usually lands within a minute or two of starting the monitor.")
    else:
        st.markdown("Monitoring: :gray-badge[Ready to configure]" if webhook else
                    "Monitoring: :gray-badge[Not connected] create a demo endpoint to receive Exa's webhook")

with st.sidebar:
    auth.logout_button()
    st.subheader("Agent activity")
    for t in ss.get("trace", []):
        st.markdown(f"✓ {t}")
    st.caption(f"Exa key {'✅' if ex.has_key() else '❌'} · Snapshot calls used: {ex.snapshot_calls()} / 100")
