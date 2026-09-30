# Design

**Idea:** Exa turns the public web into structured facts with citations. The app chains those facts into one sourcing workflow: detect the risk, confirm it, find alternatives, vet them, decide and keep watching.

## Who is who

```
Retailer ← direct supplier ← distributor / importer ← manufacturer ← parts and raw materials
```

- One company can play several roles. For example, Whirlpool both manufactures its products and sells them to us directly.
- The retailer's decision is always about the **direct supplier**, but a risk can start at any layer.
- A supplier is not the same as a brand. Whirlpool supplies KitchenAid and Maytag. Another company that carries the same brands still counts as an alternative supplier. The app excludes only the companies already on our watchlist.

## Without Exa vs with Exa

- **Without Exa (the current stack):**
  - Internal KPI rules: on-time delivery ≥ 95%, fill rate ≥ 96%, cost change ≤ 1%.
  - A third-party rating that refreshes monthly.
  - Both react late.
- **With Exa:** a risk level and signals for each supply-chain layer. Each signal is tagged as *direct evidence* or *inference* and cited.
- The **latency gap** line puts the two views side by side.
- **Evidence order:** sources the risk card cites come first, newest first. The Snapshot replay drops anything dated on or after the cutoff.

## Exa calls

| Step | Call | Key settings |
|---|---|---|
| Scan / Investigate | `exa.search` | `start_published_date` (last 12 months), `system_prompt` (rank by recency and severity) and `output_schema` (risk level, price change, signals by layer). One call per supplier, run in parallel. |
| Validate | `exa.search` | `contents.snapshot_as_of`: each page as it was stored on the cutoff date |
| Published since | `exa.search` | `start_published_date`: news published after the cutoff |
| Discover | `exa.search` | `category="company"`, `output_schema`, type selectable (default `deep`) |
| Vet | `exa.agent.runs.create` | `input.data` (the chosen companies), `output_schema`, `effort`. The app polls until the run finishes. |
| Evidence excerpts | `exa.get_contents` | `highlights` with a query, for each candidate |
| Copilot | `exa.openai.web_search` | Exa as an OpenAI tool. The model picks its own searches, at most 4 per question. |
| Watch | `exa.monitors.create`, then `trigger` | Runs daily and posts to a webhook. The inbox checks the `Exa-Signature` (HMAC-SHA256). |

## Guardrails

- **Never invent facts:**
  - The schemas allow null.
  - The prompts ask for sources.
  - Anything unproven is labeled as inference, or as "validate with the supplier".
- **Copilot:**
  - It answers sourcing questions only.
  - It treats search results as untrusted and cites URLs.
  - Questions are capped at 500 characters, and at 15 per session.
- **No automatic actions:** decision buttons only hand the case off to a team. They never buy or change anything.
- **Access:** a login is required, and keys live only in `.env` or the Streamlit Secrets.

## Caching

- Each request and its response are saved as JSON in `cache/<call type>/`, named by a hash of the request.
- The same request within 6 hours returns the cached result for free, with a CACHED label. After that it is fetched live again.
- If a live call fails, the app falls back to the cache, however old.
- The app counts Snapshot calls against the 100-request trial.

## Files

```
app.py          the page, top to bottom in workflow order
agent.py        prompts, schemas, supplier data, candidate shortlist
exa_client.py   every Exa call, plus the cache
copilot.py      OpenAI model with Exa as its search tool
inbox.py        Svix Play endpoint, signature check
auth.py         login
ui.py           cards, tables, citations, ↗ API-call popovers
internal.py     synthetic KPI rules and third-party feed
impact.py       spend × price change
cache.py        JSON cache on disk
data/           suppliers.json (24 suppliers, 6 categories), scenarios.json (7)
```

## Limits

- **Snapshot:**
  - It covers the last 5 months only, with 100 trial requests.
  - It fixes page *content* at the cutoff date, not search *ranking*.
  - It is a research preview.
- **Company search:** it doesn't accept date filters or domain exclusions.
- **Agent vetting:** it takes about 1–2 minutes.
- **Webhook:** Svix Play is a free test inbox that stands in for the retailer's own endpoint in a real deployment.
