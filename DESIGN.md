# Supplier Risk & Discovery Radar — Design

**Positioning:** external supply-chain intelligence for retail sourcing agents.
**Persona:** strategic sourcing lead at a large North American retailer.
**Question:** which of our suppliers is becoming a risk, what is happening upstream, and who could we source from instead?

## Entity model

Retailer → direct (tier-1) supplier → distributor / wholesaler / importer → manufacturer → upstream components and materials.
One company can hold several roles. The retailer's decision is always about the **direct supplier relationship**; risks can originate at any layer.
`data/suppliers.json` records each direct supplier's relationship (e.g. "Manufacturer · direct supplier", "Distributor · direct supplier") and known upstream dependencies.

## Workflow → Exa

| Step | Exa capability | Notes |
|---|---|---|
| Watchlist sweep + investigate | Search, `system_prompt`, `output_schema` (risk + signals by layer, direct evidence vs inference), grounding | One search per supplier; the same result powers the drill-in |
| Validate | Snapshot (`contents.snapshot_as_of`) | Auto only, no category, 5-month window, 100 trial requests; shows the latency gap vs the 3P feed |
| Impact | derived | Synthetic spend × grounded price change (ignores values beyond ±50%) |
| Alternative suppliers | Search `type="deep"`, `category="company"` | Roles: Manufacturer / Distributor / Wholesaler / Importer / Vertically Integrated / Other, grounded in evidence; default shortlist is role-diverse |
| Vet | Agent (`input.data`, `output_schema`, `effort`) + Contents highlights | Direct-supplier assessment: demonstrated vs inferred vs needs supplier validation |
| Decide | internal workflow | Final question + candidate table; orange buttons never execute procurement actions |
| Watch | Monitors | Webhook required at create; runs read back by polling |

"Without Exa" = the current stack: rule-based internal KPI status (on-time ≥ 95%, fill ≥ 96%, cost Δ ≤ 1%) plus a simulated quarterly 3P risk rating with refresh dates. All synthetic and labeled.

## Files

```
app.py          Streamlit page, progressive reveal; sidebar = scenario, supplier, date, live toggle, agent trace
agent.py        orchestrator: queries, system prompts, schemas, shortlist logic
exa_client.py   every Exa call: search, contents, agent runs, monitors; caching + request capture
internal.py     synthetic current stack: KPI rules, quarterly 3P feed
ui.py           rendering: ↗ call popovers, inline citations, tables, cards
impact.py       exposure math
cache.py        JSON cache
data/           suppliers.json (24 suppliers, 6 categories), scenarios.json (7 scenarios)
```
