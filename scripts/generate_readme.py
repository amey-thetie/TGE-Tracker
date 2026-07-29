"""
generate_readme.py

Builds README.md from the current data/ snapshot so every number in the
README stays in sync with the actual dataset baked into
tge_tracker_widget.html. Run this after any pipeline refresh:

    python scripts/generate_readme.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")
RAW_DIR = os.path.join(ROOT, "data", "raw")
README_PATH = os.path.join(ROOT, "README.md")

STATUS_ORDER = [
    ("POST_TGE", "Post-TGE", 0.85, "Fundraising record links a coin **and** CoinGecko confirms active trading (24h volume ≥ $1,000)."),
    ("TOKEN_LIVE_NOT_TRADING", "Live, not trading", 0.6, "Coin is confirmed to exist on CoinGecko, but 24h volume is negligible — contract exists, no active market."),
    ("TGE_ANNOUNCED", "TGE announced", "0.35 – 0.4", "A coin is referenced, or the round itself is typed as a token sale/ICO/IEO/IDO, but it isn't independently verified on CoinGecko."),
    ("PRE_TGE", "Pre-TGE", "—", "Company has publicly discussed a token, but no announcement or contract exists yet. *(not produced by the current pipeline — see Limitations)*"),
    ("NO_TOKEN", "No token", "—", "Evidence strongly indicates the project has no token. *(not produced by the current pipeline — see Limitations)*"),
    ("UNKNOWN", "Unknown", 0.1, "No coin reference or token-sale-type round was found for this company in the Fundraise Brief."),
]

INVESTIGATION_STEPS = [
    ("Identify the company", "Resolve the official entity — website, docs, GitHub, X, blog, foundation/labs split — before anything else."),
    ("Search for announcements", "Look for TGE, token launch, tokenomics, mainnet token, airdrop, listing, contract deployment, or genesis language."),
    ("Verify on-chain existence", "Contract address, mint address, deployment tx/timestamp, total supply, holder count — across 11 supported chains."),
    ("Verify market existence", "CoinGecko, CoinMarketCap, DefiLlama, DexScreener, GeckoTerminal — price, market cap, FDV, liquidity, volume."),
    ("Verify exchange listings", "Centralized (Binance, Coinbase, Kraken, ...) and decentralized (Uniswap, Jupiter, ...) — is trading actually live?"),
    ("Aggregate evidence", "Every finding carries a source, strength, and timestamp. Conflicting evidence is never discarded, only explained."),
]

SCHEMA_FIELDS = [
    ("u", "company_uid", "TIE Terminal company ID, e.g. `company_x3adb`"),
    ("n", "company", "Display name"),
    ("c", "category[]", "TIE company_category tags (e.g. `[\"DeFi\", \"Token Issuers\"]`)"),
    ("s", "status", "One of the six CryptoLaunchVerifier states"),
    ("f", "confidence", "0.0–1.0, per the weighting above"),
    ("rt", "round_type", "Most recent funding round type (e.g. `STRATEGIC`, `SEED`)"),
    ("rd", "round_date", "Most recent round's announcement date, `YYYY-MM-DD`"),
    ("ra", "round_amount", "Funding amount in USD for that round"),
    ("su", "source_url", "First source URL for that round"),
    ("tn", "token_name", "Coin name, if any is linked (present only when a coin exists)"),
    ("ts", "token_symbol", "Ticker symbol, only set once CoinGecko-verified"),
    ("mp", "market_price_usd", "Live price at snapshot time (CoinGecko)"),
    ("mc", "market_cap_usd", "Live market cap at snapshot time"),
    ("mv", "market_volume_24h_usd", "Live 24h volume at snapshot time"),
    ("pv", "provenance", "Only set to `\"curated\"` when status came from Airtable's human-reviewed \"Post TGE Token\" flag rather than a CoinGecko match"),
]


def load_json(name):
    with open(os.path.join(RAW_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def load_dataset():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_status_table(stats):
    lines = ["| Status | Count | Confidence | Meaning |", "|---|---|---|---|"]
    for key, label, conf, meaning in STATUS_ORDER:
        count = stats.get(key, 0)
        lines.append(f"| **{label}** (`{key}`) | {count:,} | {conf} | {meaning} |")
    return "\n".join(lines)


def build_steps_list():
    return "\n".join(
        f"{i}. **{title}** — {detail}" for i, (title, detail) in enumerate(INVESTIGATION_STEPS, start=1)
    )


def build_schema_table():
    lines = ["| Field | Meaning | Notes |", "|---|---|---|"]
    for short, meaning, notes in SCHEMA_FIELDS:
        lines.append(f"| `{short}` | {meaning} | {notes} |")
    return "\n".join(lines)


def main():
    dataset = load_dataset()
    stats = dataset["stats"]
    generated_at = dataset["generated_at"]
    total = stats.get("total", sum(v for k, v in stats.items() if k != "total"))

    try:
        verified = load_json("verifiedByCoinUid.json")
        unmatched = load_json("unmatchedCoins.json")
        n_verified, n_unmatched = len(verified), len(unmatched)
        n_coins_total = n_verified + n_unmatched
    except FileNotFoundError:
        n_verified = n_unmatched = n_coins_total = None

    status_table = build_status_table(stats)
    steps_list = build_steps_list()
    schema_table = build_schema_table()

    coin_verification_line = (
        f"Of the **{n_coins_total:,} coins** the Fundraise Brief links to a company, "
        f"**{n_verified:,}** were independently confirmed live on CoinGecko and "
        f"**{n_unmatched:,}** could not be matched to any CoinGecko listing."
        if n_coins_total is not None
        else "Coin verification counts are unavailable — see `data/raw/verifiedByCoinUid.json`."
    )

    content = f"""# TGE Tracker

A searchable dashboard tracking Token Generation Event (TGE) status for
every company in TheTie's **Fundraise Brief**, cross-checked live against
**CoinGecko** market data. Built on the evidence-first investigation
methodology defined in [`Instructions.py`](Instructions.py) (the
`CryptoLaunchVerifier` system prompt) — accuracy over speed, no fabricated
symbols, dates, or contracts, ever.

**[Open the widget](tge_tracker_widget.html)** — self-contained HTML, no
server or build step needed. Just open it in a browser, or run
`npm start` (or `node app.js`) to serve it at `http://localhost:3000/`
instead of a `file://` path.

## Contents

- [What it does](#what-it-does)
- [Current snapshot](#current-snapshot)
- [The investigation methodology](#the-investigation-methodology)
- [Widget features](#widget-features)
- [Running it](#running-it)
- [How this was built](#how-this-was-built)
- [Data schema](#data-schema)
- [Repo layout](#repo-layout)
- [Refreshing the data](#refreshing-the-data)
- [Known limitations](#known-limitations)

## What it does

Every company that has ever raised money in the Fundraise Brief gets
checked for two things:

1. Does the Fundraise Brief itself link this company to a coin, or does its
   most recent round carry a token-sale-type label (`TOKEN`, `ICO`, `IEO`,
   `IDO`)?
2. If so, does **CoinGecko** independently confirm that coin actually
   exists and is trading — not just announced?

Both questions are answered from real data pulled at build time. Nothing
here is inferred, guessed, or filled in from model memory — if the pipeline
couldn't verify something, the company is marked `UNKNOWN` rather than
assigned a guessed status.

## Current snapshot

- **{total:,} companies** indexed — searchable by name, token, or category
- Snapshot generated: `{generated_at}`
- Sources: TIE Terminal (Fundraise Brief) fundraising-rounds dataset + CoinGecko live market data
- {coin_verification_line}

{status_table}

## The investigation methodology

`Instructions.py` defines `CryptoLaunchVerifier`, a six-step evidence
pipeline. The automated dataset here mechanizes steps 2–4 (announcement,
coin, and market checks) at scale across thousands of companies; steps 1,
5, and 6 (company disambiguation, exchange-listing detail, full evidence
aggregation) are part of the methodology but not yet run automatically for
every company — see [Known limitations](#known-limitations).

{steps_list}

**Confidence scoring.** `Instructions.py` weights official announcements,
verified contracts, mint verification, and exchange/aggregator listings
independently (0.10–0.30 each) and reduces confidence for conflicting,
unofficial, or outdated evidence. The automated pipeline's per-status
confidence values (in the table above) are a simplified application of that
same weighting: a verified, actively-traded coin scores highest; an
unconfirmed coin reference or bare token-sale round type scores in the
middle; no signal at all scores lowest.

## Widget features

- **Search** — matches company name, token name/symbol, or category across
  every indexed company. Debounced, capped at 300 rendered results with a
  "refine your search" note if a query matches more than that.
- **Status tiles** — click any of the six status counts to filter the list
  to just that status; click again to remove the filter. Multiple statuses
  can be active at once.
- **Default view** — with no search or filter active, shows the most
  recently-announced rounds in the Fundraise Brief, newest first.
- **Sortable columns** — click any column header (Company, Round, Status,
  Confidence, Token, Market cap) to sort the current view by that column;
  click again to reverse direction. Sorting a column while browsing with no
  search/filter switches out of the "latest additions" default view into a
  full sorted browse of all companies (capped at 300 rendered rows).
- **Fundraise Brief period picker** — a native month/year calendar input
  plus a "Load →" button, mirroring the exact monthly `brief_period`
  concept Airtable uses. Clicking Load filters to companies whose round
  date falls in that month and reports "✓ N companies · from snapshot
  generated [date]". This filters what's *already in the current
  snapshot* — it does not live-fetch that month from Airtable. If a month
  has zero matches, the status message names the exact
  `python scripts/load_brief_period.py <period>` command to pull it in.
  Combinable with search, status tiles, and column sorting — pair it with
  the Post-TGE status tile for "which companies actually completed a TGE
  in this month" at a glance.
- **Refresh button** — reloads the page from disk, so it picks up a newer
  build if you've rebuilt the widget since opening it. It does **not**
  live-fetch new data from Airtable/TIE Terminal/CoinGecko — this project
  has no backend, so refreshing the underlying dataset still means running
  the pipeline scripts below and rebuilding.
- **Row detail** — click any row to expand its full evidence trail,
  reasoning, live market stats (price / market cap / 24h volume), and
  source link, generated client-side from the row's raw data fields.
- **Methodology panel** — the "How this is scored" toggle in the header
  summarizes the six-step workflow and decision rules inline.
- Light/dark theme aware; the table scrolls horizontally on narrow screens
  without the page itself scrolling sideways.

## Running it

The widget is a self-contained HTML file — opening it directly in a browser
is enough, no server required. `app.js` is a small optional convenience:

```
npm start          # or: node app.js
node app.js 8080   # pick a different port (defaults to 3000)
```

It's a plain static file server (Node built-ins only, zero dependencies)
that serves this directory at `http://localhost:3000/` and maps `/` to
`tge_tracker_widget.html`. It exists purely so you get a real `http://` URL
instead of `file://` — it does **not** add a backend, and does not change
how data gets refreshed (still the `scripts/` pipeline below).

## How this was built

The dataset comes from a multi-agent pipeline, not a single API call —
covering the full Fundraise Brief (thousands of companies, tens of
thousands of funding rounds) is too much to page through sequentially in
one context:

- **Roster** — the complete company list is paginated from TIE Terminal's
  metadata endpoint in small sequential batches (a single giant request
  hits Claude's per-call output-token ceiling once you're returning
  thousands of records at once).
- **Join** — parallel agents each take a date slice of the fundraising
  rounds and extract every row that references a coin or a token-sale-type
  round, deduplicated per company.
- **Verify** — a dedicated agent independently cross-checks every coin the
  Fundraise Brief names against CoinGecko's live market data, batching
  requests rather than checking coins one at a time.
- **Backfill** — a follow-up unfiltered pass over the most recent rounds
  fixes round-date coverage for companies that raised money but had no
  coin/token-sale signal (see [Known limitations](#known-limitations) for
  why this was needed).
- **Brief-period loads** — Airtable's `FundingRounds` table tags every round
  that shipped in a monthly Fundraise Brief with a `brief_period` (`YYYY-MM`)
  and, critically, a human-reviewed **"Post TGE Token"** checkbox — TheTie's
  own curated call on whether a company's token has already had its TGE.
  `load_brief_period.py` pulls one period at a time and uses that flag to
  upgrade companies straight to `POST_TGE` even when no coin was ever
  independently matched on CoinGecko, tagged with `pv: "curated"` so the
  widget can explain the difference (see [Data schema](#data-schema)).

See `scripts/` for the code that assembles and classifies the results of
that pipeline into `data/tge_dataset_full.json`.

## Data schema

`data/tge_dataset_full.json` uses short keys to keep the dataset small
enough to embed directly in the widget (the verbose version — full
evidence/reasoning text per company — came out to several megabytes almost
entirely from repeated boilerplate, so that text is generated client-side
from these raw fields instead):

{schema_table}

## Repo layout

```
Instructions.py              CryptoLaunchVerifier system prompt (the methodology)
widget_template.html         Editable widget source (data injected at build time)
tge_tracker_widget.html      Built widget — this is the file you actually open
app.js                       Optional local static server (npm start / node app.js)
package.json                 Just the "start" script + build:* shortcuts, no dependencies
data/
  tge_dataset_full.json      The classified dataset baked into the widget
  raw/                       Intermediate pipeline outputs
    roster.json                Full company list (company_uid + name)
    joinByCompany.json         Company -> coin/round links found by the join agents
    verifiedByCoinUid.json     Coins independently confirmed live on CoinGecko
    unmatchedCoins.json        Coins the Fundraise Brief names that CoinGecko couldn't match
    recent_rounds_unfiltered.json  Most-recent-rounds backfill pass (any round, not just token signal)
    airtable_recent_companies.json  Raw export of the newest funded_companies rows from Airtable
    airtable_brief_<period>.json  Raw export of one brief period's FundingRounds rows (e.g. airtable_brief_2026-07.json)
    stats.json                  Snapshot of dataset-wide counts
scripts/
  build_dataset.js            Classifies companies -> data/tge_dataset_full.json
  build_widget.js             Injects the dataset into widget_template.html
  merge_recent_rounds.js      Backfills round dates from a fresh unfiltered fetch
  update_from_airtable.py     Merges newly-added companies straight from the Airtable base
  load_brief_period.py        Loads one Fundraise Brief period, incl. curated Post-TGE upgrades
  extract_roster_from_journal.js  Recovers agent results if a workflow run partially fails
  process_workflow_output.js  Parses a completed workflow's raw output file
  generate_readme.py          Regenerates this file from the current dataset stats
```

## Refreshing the data

The dataset is a point-in-time snapshot, not a live feed — the TIE
Terminal / CoinGecko connections only exist inside a Claude Code session.
To refresh:

1. Re-run the data-collection pass (fundraising rounds + coin verification)
   against TIE Terminal's `get_fundraising_rounds` / `get_metadata` tools and
   the CoinGecko MCP, writing results into `data/raw/`.
2. `node scripts/build_dataset.js` — reclassifies every company from
   `data/raw/*.json` into `data/tge_dataset_full.json`.
3. `node scripts/build_widget.js` — rebuilds `tge_tracker_widget.html` from
   `widget_template.html` + the dataset.
4. `python scripts/generate_readme.py` — regenerates this file, including
   this line count and every number above.

### Fast path: pull just the newest Airtable additions

The Fundraise Brief's Airtable base ("Fundraise Data" -> `funded_companies`
table) is the earliest place a company shows up — often before it has a
`company_uid` or any round data in TIE Terminal at all. To pick up the
newest additions without re-running the full pipeline:

1. In a Claude Code session, list `funded_companies` records sorted by
   `created_timestamp` descending (field ID `fldjGsIHxCQDyYCfI`) via the
   Airtable MCP, and save the response (plus a `fieldMap` of fieldId ->
   field name) to `data/raw/airtable_recent_companies.json`.
2. `python scripts/update_from_airtable.py` — adds any company not already
   in the dataset (including ones with no `company_uid` yet, using a
   synthetic `airtable_<recordId>` ID), and backfills round dates for
   existing companies where Airtable's lookup is more recent. Never
   touches existing TGE status/token classification.
3. `node scripts/build_widget.js` — rebuild.

### Fast path: load any specific brief period

Every round in the `FundingRounds` table that shipped in a monthly Brief
carries a `brief_period` (`YYYY-MM`, derived from `brief_round = TRUE`) and
the curated `Post TGE Token` / `Post TGE Token added in Terminal`
checkboxes. To (re)load one period — useful for backfilling an older month
or re-syncing one that changed after it shipped:

1. In a Claude Code session, filter the `FundingRounds` table
   (`tblhMpbvsCCSfWKCv` in the `Fundraise Data` base, `apppBDKslp00CJu9n`) by
   `brief_period = "<YYYY-MM>"` via the Airtable MCP, fetching `company_uid`,
   `company`, `funding_announcement_date`, `funding_round_type`,
   `funding_amount`, `source_url_1`, `sector`, `Post TGE Token`, and
   `Post TGE Token added in Terminal`. Save the response (records +
   `fieldMap`) to `data/raw/airtable_brief_<period>.json`.
2. `python scripts/load_brief_period.py <period>` — e.g.
   `python scripts/load_brief_period.py 2026-07`. Adds companies missing
   from that period, backfills round data, and upgrades any company flagged
   `Post TGE Token` straight to `POST_TGE` (existing CoinGecko-confirmed
   statuses are never downgraded).
3. `node scripts/build_widget.js` — rebuild.

## Known limitations

- **Only one brief period has been loaded via `load_brief_period.py` so far
  (`2026-07`).** Older months' curated `Post TGE Token` flags haven't been
  pulled in yet, so some companies that are genuinely `POST_TGE` per
  TheTie's own review are still sitting at whatever the base pipeline
  inferred for them.
- **Curated review can disagree with this project's own earlier manual
  reasoning** — e.g. Pact Labs was reasoned through as `NO_TOKEN` in an
  early manual pass of this project (its round funds Tether's USAT
  stablecoin, not an obviously Pact-Labs-native token), but Airtable's
  `Post TGE Token` flag says otherwise for it, and the automated loader
  correctly defers to the curated flag over that earlier manual guess.
- **`TGE_ANNOUNCED` companies with no token name shown** raised money via a
  round explicitly typed as a token sale/ICO/IEO/IDO, but the Fundraise
  Brief doesn't link a specific coin to them, and no company-name-based
  CoinGecko search was run for that bucket (~650 companies) — a few of
  these are almost certainly live tokens that just aren't reflected here
  yet (e.g. Credible Finance's CRED token was confirmed live in manual
  spot-checks during development, but the bulk pipeline still shows it as
  `TGE_ANNOUNCED` since it wasn't part of the 880-coin verification pass).
- **`PRE_TGE` and `NO_TOKEN` are currently always 0.** The bulk classifier
  only distinguishes "coin/token-round signal found" from "nothing found"
  (`UNKNOWN`) — it doesn't yet attempt the finer judgment calls (e.g. "this
  company has publicly discussed a token" vs. "this business model doesn't
  fit a token at all") that would populate those two states. `Instructions.py`
  defines both; the automated pipeline just hasn't been extended to produce
  them at scale.
- **Round-date coverage.** Every company's *most recent* round date is
  backfilled from an unfiltered fetch of the ~700 most recent Fundraise
  Brief rounds (back to 2025-12-03) — companies whose only round predates
  that window may still be missing a round date even though they're in the
  Fundraise Brief.
- **Exchange listing detail (step 5 of the methodology) isn't captured.**
  The pipeline confirms *whether* a coin trades on CoinGecko, but not which
  specific centralized or decentralized exchanges list it.
- **Airtable-only additions (`airtable_<recordId>` IDs) carry minimal data.**
  Companies pulled in via `update_from_airtable.py` before they have a real
  `company_uid` have no category, round type, or amount — just a name, an
  optional round date, and (when Airtable's own `token_issuer` flag is set)
  a `TGE_ANNOUNCED` status. They get a proper profile once TIE Terminal
  assigns them a `company_uid` and the main pipeline picks them up.
"""

    with open(README_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"wrote {README_PATH} ({len(content)} chars)")


if __name__ == "__main__":
    main()
