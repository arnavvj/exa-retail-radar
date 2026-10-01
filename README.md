# Supplier Risk & Discovery Radar

A small web app that shows how a retailer's sourcing team can use [Exa](https://exa.ai) to spot supplier trouble early and find backup suppliers.

## The problem

A large retailer buys from hundreds of suppliers. The signs of trouble are usually public weeks before they show up in the retailer's own numbers: price increases, tariffs, plant closures, parts shortages. The team's usual tools lag behind:

- **Internal dashboards** (on-time delivery, fill rate) react only after the damage is done.
- **Third-party risk ratings** refresh once a month.

Nobody has time to read the whole web.

**The question the app answers:** *Which of our suppliers is becoming a risk, what is happening upstream, and who could we source from instead?*

**User:** a strategic sourcing lead at a large North American retailer.

## How it works

| Step | What the user sees | Exa feature |
|---|---|---|
| 1. Scan | Every supplier on the watchlist checked against the last 12 months of public web news, most recent and most severe first | Search, with structured output and citations |
| 2. Investigate | One supplier's risks, split by supply-chain layer (the supplier, factories, logistics, raw materials) | the same Search result |
| 3. Validate | The web replayed as of a past date ("could we have known?"), plus what has been published since | Snapshot, then Search filtered by date |
| 4. Discover | Companies that could supply us instead | Search with `category="company"` |
| 5. Vet | Deep research on up to 3 candidates: what is proven, what is likely, what still needs checking, and 2 sales leaders to contact at each | Agent, Contents highlights and people search |
| 6. Ask | A follow-up question, answered by an OpenAI model that uses Exa as its search tool | Exa tool for OpenAI |
| 7. Decide | A choice of next step. Nothing is bought or changed automatically. | none |
| 8. Watch | A daily re-check of the supplier, with results pushed to a webhook | Monitors |

Each Exa section has a **↗** button that shows the exact API call, in both Python and REST form.

## What is real

| Label | Meaning |
|---|---|
| LIVE / CACHED | Real Exa results. Cached results were fetched live earlier and saved, to avoid paying for the same call twice. |
| SYNTHETIC | The retailer's internal data (spend, SKUs, KPIs, third-party ratings) is made up. |
| DERIVED | Our own math, such as spend × announced price change. |

The suppliers, brands and events are real. There are 7 scenarios: 6 based on real 2026 events, plus "Live today".

## Run it

```bash
uv venv --python 3.12 && uv pip install -r requirements.txt
cp .env.example .env        # then fill it in
.venv/bin/streamlit run app.py
```

| Variable | Needed? | Purpose |
|---|---|---|
| `EXA_API_KEY` | yes | Exa |
| `APP_USER1` / `APP_PASS1` | yes | Login. Add more accounts as `APP_USER2`, `APP_PASS2`, and so on, up to 9. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | for step 6 | Copilot (default model `gpt-5.6`) |
| `EXA_AGENT_EFFORT` | no | Vetting depth. The default, `medium`, costs $0.10 per run. |
| `EXA_MONITOR_WEBHOOK_URL` | no | Where the Monitor sends results. If this is empty, the app creates a free Svix Play URL. |

On Streamlit Community Cloud, put the same values in the app's **Secrets**.

**Cost notes:**

- Results are saved in `cache/`, which is gitignored, and reused for 6 hours. A fresh clone starts with an empty cache, so the first run of each step calls Exa and costs money.
- The **Run live** toggle skips the cache.
- Snapshot allows 100 trial requests and covers the last 5 months only.
- Step 8 creates a real daily Monitor. It keeps running, and billing, until you delete it with `exa.monitors.delete(id)`.

For how the app is built, see [DESIGN.md](DESIGN.md).

#### PRESENTATION [↗](https://docs.google.com/presentation/d/1sTm5gTODzAOsxuOJeb-zXX5PHs3_QrF5/edit?usp=sharing&ouid=100040357837908168144&rtpof=true&sd=true)
