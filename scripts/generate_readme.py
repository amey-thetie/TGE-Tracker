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
    ("ts", "token_symbol", "Ticker symbol, only set once market-verified"),
    ("mp", "market_price_usd", "Live price at snapshot time (CoinGecko, or CoinMarketCap where `pv` says so)"),
    ("mc", "market_cap_usd", "Live market cap at snapshot time"),
    ("mv", "market_volume_24h_usd", "Live 24h volume at snapshot time"),
    ("pv", "provenance", "How the status was reached when it wasn't the standard coin_uid + CoinGecko path. `\"curated\"` = Airtable's human-reviewed \"Post TGE Token\" flag. `\"name-match\"` = company name uniquely matched a live CoinGecko coin (inferred link, scored lower). `\"cmc-name-match\"` = same inferred name match, but confirmed on CoinMarketCap after CoinGecko found nothing, so the price on that row comes from CMC. Absent = standard path."),
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
**CoinGecko** and **CoinMarketCap** market data. Built on the evidence-first investigation
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
- [How it works](#how-it-works)
- [Setup and run](#setup-and-run)
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
2. If so, does **CoinGecko** — or **CoinMarketCap**, for anything CoinGecko
   can't match — independently confirm that coin actually exists and is
   trading, not just announced?

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

```text
┌──────────────────────────────────────────────────────────────────────┐
│ TGE Tracker      [ How this is scored ]      snapshot 2026-08-14 UTC │
├──────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ Search any company in the Fundraise Brief…                   (1) │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ [ 2026-08 ] [ Load → ] (3)  ✓ 128 companies       (4) [ ↻ Refresh ]  │
│                                                                      │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│ │  647   │ │  229   │ │  473   │ │   0    │ │   0    │ │ 4,034  │    │
│ │Post-TGE│ │Live not│ │TGE ann.│ │Pre-TGE │ │No token│ │Unknown │(2) │
│ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
│                                                                      │
│ Showing the latest 50 of 5,383                     [ Clear filters ] │
├──────────────────────────────────────────────────────────────────────┤
│ Company ▾    Round ▾      Status ▾     Conf ▾  Token ▾  Mkt cap ▾(5) │
│ ──────────────────────────────────────────────────────────────────── │
│ Worldcoin    Aug 11 2026  POST_TGE     0.85    WLD      $1.9B        │
│ Ondo Finance Aug 04 2026  POST_TGE     0.85    ONDO     $2.9B        │
│ Blockspace   Aug 03 2026  UNKNOWN      0.10    —        —            │
│ ┌── expanded row (6) ──────────────────────────────────────────────┐ │
│ │ evidence · source · strength    price · market cap · 24h volume  │ │
│ └──────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│ 5,383 companies indexed · snapshot 2026-08-14                        │
└──────────────────────────────────────────────────────────────────────┘
```

1. **Search** · 2. **Status tiles** · 3. **Brief month + Load** ·
4. **Refresh** · 5. **Sortable headers** · 6. **Expandable row**

Only **(4) Refresh** reaches the network. Everything else operates on data
already embedded in the file, which is why it works from a `file://` path.

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
- **Refresh button (live, when run via `npm start`)** — calls a local
  `/api/refresh` endpoint that fetches companies added to the Fundraise
  Brief since the current snapshot, checks any flagged as a token issuer
  against CoinGecko and then CoinMarketCap (exact match only, no fuzzy
  guessing), classifies them with the same rules as the batch pipeline, and
  re-renders in place — no page reload. Requires an Airtable token in `.env`
  (see [Setup and run](#setup-and-run)); without a server or a token it falls
  back to a clear inline message rather than failing silently. Refresh only
  ever *adds* companies — for status changes on companies already tracked,
  see [Automatic sweeps](#automatic-sweeps-optional).
- **Auto-updating while open** — when served locally, the page polls
  `/api/snapshot` once a minute and pulls a new dataset only when the
  timestamp actually moves, so a tab left open picks up background sweeps on
  its own. Your search, status tiles, month, and sort are preserved across the
  swap; the header timestamp is what tells you the data underneath changed.
- **Row detail** — click any row to expand its full evidence trail,
  reasoning, live market stats (price / market cap / 24h volume), and
  source link, generated client-side from the row's raw data fields.
- **Methodology panel** — the "How this is scored" toggle in the header
  summarizes the six-step workflow and decision rules inline.
- Light/dark theme aware; the table scrolls horizontally on narrow screens
  without the page itself scrolling sideways.

## How it works

Three things move data through this repo: a batch build, a live Refresh, and
a background sweep. They write the same two files.

### Where the data comes from

```mermaid
flowchart TD
  RAW["data/raw/*.json<br/>MCP pulls + python loaders"] -->|"npm run build:dataset"| BD["build_dataset.js"]
  BD --> DS["data/tge_dataset_full.json<br/>the snapshot everything reads"]
  DS -->|"npm run build:widget"| BW["build_widget.js"]
  BW --> WID["tge_tracker_widget.html<br/>self-contained, opens anywhere"]
  SW["Refresh button / auto-sweep"] -.->|"rewrites both"| DS
  SW -.-> WID
```

The live path deliberately skips the build scripts and writes the same two
artifacts the batch pipeline produces, so a swept widget is comparable to a
rebuilt one.

### What a refresh or sweep does

```mermaid
flowchart TD
  BTN["Refresh button"] -->|"POST /api/refresh"| APP["app.js"]
  TIMER["Scheduler<br/>every SWEEP_INTERVAL_MINUTES"] --> APP
  APP -->|"rows added since the sync cursor"| AT["Airtable funded_companies"]
  AT -->|"companies never seen before"| VM["verifyMarkets"]
  APP -->|"sweep only: tracked rows whose<br/>round is inside the age window"| RV["reverifyRecent"]
  RV --> VM
  VM -->|"symbol, price, 24h volume"| CL["classify / promote"]
  CL --> OUT["dataset + widget rewritten"]
  OUT -.->|"GET /api/snapshot, once a minute"| BTN
```

A manual Refresh runs only the ingest half. A sweep runs both, which is what
lets a company already in the dataset move off `TGE_ANNOUNCED` once its token
goes live. Both share a write lock, so they can never interleave.

### How a token gets verified

```mermaid
flowchart LR
  N["candidate names"] --> CG["CoinGecko<br/>exact name or symbol"]
  CG -->|"exact match"| OK1["verified<br/>source: coingecko"]
  CG -->|"no match, and a CMC key is set"| CMC["CoinMarketCap<br/>cached map, ~8,000 listings"]
  CMC -->|"one confident id + live quote"| OK2["verified<br/>source: coinmarketcap"]
  CMC -->|"no match, ambiguous, or no quote"| UN["unmatched<br/>stays TGE_ANNOUNCED"]
```

CoinGecko runs first and its result is never overwritten, so the existing
snapshot stays internally comparable. With no CoinMarketCap key the middle
stage is skipped entirely and the path is simply CoinGecko → unmatched.

CoinMarketCap has no name-search endpoint, so the id map is pulled once per
process and matched locally through four tiers, strictest first:

1. name, literal (case-folded, punctuation intact)
2. name, normalized (punctuation stripped)
3. symbol, literal
4. symbol, normalized

The first tier returning *exactly one* listing wins; a tier returning several
is a genuine ambiguity and the name is abandoned rather than guessed. The
literal tier exists because CoinMarketCap lists both `Bitcoin` and
`Bitcoin.ℏ` — stripping punctuation collapses them into one ambiguous pair,
and 136 of ~7,900 listed names collide that way.

## Setup and run

### Prerequisites

- **Node.js 18+** — only used for `app.js` (the local server) and the
  `scripts/*.js` pipeline. Zero npm dependencies; there is nothing to
  `npm install`.
- **Python 3.8+** — only used for `scripts/*.py` (README generation, the
  Airtable/brief-period loaders). Standard library only; nothing to `pip
  install`.

Neither is required just to *view* the widget — it's a single static HTML
file with the entire dataset embedded inline.

### Get the code

```
git clone https://github.com/amey-thetie/TGE-Tracker.git
cd TGE-Tracker
```

### Option A — just open it (no setup)

Double-click [tge_tracker_widget.html](tge_tracker_widget.html), or from a
terminal:

```
start tge_tracker_widget.html    # Windows
open tge_tracker_widget.html     # macOS
xdg-open tge_tracker_widget.html # Linux
```

### Option B — run the local server (needed for the live Refresh button)

```
npm start          # or: node app.js
node app.js 8080   # pick a different port if 3000 is taken (defaults to 3000)
```

Then open `http://localhost:3000/` in a browser. Ctrl+C to stop. `app.js`
serves the widget (mapping `/` to `tge_tracker_widget.html`) and, if
configured, exposes `POST /api/refresh` for the Refresh button's live
incremental fetch. Without the server (opening the file directly) the
Refresh button just tells you to run `npm start` instead.

### Enable the live Refresh button (optional)

The Refresh button can pull companies added to the Fundraise Brief since
the current snapshot and classify them on the spot. This needs your own
Airtable token — nothing is bundled with the repo:

1. Create a token at <https://airtable.com/create/tokens> with scope
   `data.records:read` and access to the "Fundraise Data" base
   (`apppBDKslp00CJu9n`).
2. `cp .env.example .env` (Windows: `copy .env.example .env`), then open
   `.env` yourself and paste the token in as `AIRTABLE_TOKEN=...`. Don't
   paste it into a chat with anyone, including an AI assistant — it's a
   credential. `.env` is already gitignored.
3. Restart the server (`npm start`). The startup log will say
   `Live refresh: enabled` once it finds the token.

Without a token, everything else in the widget works exactly the same —
Refresh just shows a message telling you it's not configured.

### Market-data API keys (both optional)

Refresh verifies each new token issuer against live market data. Neither
key below is required — leave them blank and it behaves as it always has.

| Variable | What it changes | Without it |
| --- | --- | --- |
| `COINGECKO_API_KEY` | Raises the CoinGecko rate limit, so a refresh with many new issuers finishes faster. Set `COINGECKO_API_PLAN=pro` **only** for a paid Pro/Analyst key — that switches requests to `pro-api.coingecko.com`. A free Demo key needs no plan change. | Public CoinGecko API, paced at one lookup every 1.2s. |
| `COINMARKETCAP_API_KEY` | Adds CoinMarketCap as a **fallback**: any company CoinGecko couldn't match gets a second lookup. Rows verified this way are tagged `pv: "cmc-name-match"`. | CoinGecko only; unmatched companies stay `TGE_ANNOUNCED`. |

The startup log prints the state of all three credentials, so `npm start`
tells you exactly which sources are live.

**Pulling these from 1Password.** `.env.tpl` holds vault references rather
than values, so it is safe to commit. Regenerate a real `.env` any time —
after a clone, or after a key rotates — with:

```bash
op inject -i .env.tpl -o .env
```

All three resolve from a single item — **`the_tie_listings_ops`** in the
`dotenv_files` vault — so one `op inject` sets up the whole app. Two of its
fields need a deliberate choice, both verified by probing the live APIs
rather than inferred from their names:

- **CoinGecko** — the stored key is a **Demo** key, so `COINGECKO_API_PLAN`
  stays `demo`. Setting it to `pro` would send requests to
  `pro-api.coingecko.com`, where this key is rejected.
- **CoinMarketCap** — the item holds *two* working keys. The template uses
  `COINMARKETCAP_PRO_API_KEY` (750 req/min). Its sibling
  `COINMARKETCAP_API_KEY` also authenticates but is a 50 req/min plan.
  Worth knowing: the 750/min key is shared with production traffic
  (~11.5k credits already drawn on the day this was set up), so if you'd
  rather keep a local tracker off that budget, point the template at the
  50/min key instead — a one-line change.

Note that the `Airtable` item in the Employee vault is a *different* thing:
an SSO browser login for airtable.com, not an API token. The working PAT is
the `AIRTABLE_API_KEY` field on `the_tie_listings_ops`.

One gotcha when editing the template: `op inject` scans the whole file for
references, comments included, so never write a literal reference URI in a
comment or the run fails to parse.

CoinGecko always runs first and its result is never overwritten, so
turning CMC on can only add verifications — it can't silently reprice a
company the existing snapshot already agreed on. Both sources use the
same exact-normalized-name rule; CoinMarketCap additionally refuses any
name that matches two or more listings (ticker collisions are common),
since a wrong match would promote a company to `POST_TGE` with a real
price attached. If a source errors mid-refresh, the response carries a
`warnings` array and the widget reports "Refreshed with problems" rather
than a clean success — an API failure and "no coin exists" look identical
in the table otherwise.

### Automatic sweeps (optional)

The Refresh button only ever *adds* companies — it skips uids it already has.
That left a real gap: a company ingested as `TGE_ANNOUNCED` stayed that way
forever, even after its token went live. The background sweep closes it.

While `npm start` is running, the server can periodically do both halves:
ingest new Airtable rows **and** re-check existing companies whose status can
still move. Configure it in `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SWEEP_INTERVAL_MINUTES` | `60` | Minutes between sweeps. `0` disables the scheduler. |
| `SWEEP_MAX_AGE_MONTHS` | `12` | Only re-check companies whose most recent round is this recent. |
| `SWEEP_ON_START` | `false` | Run one sweep at startup instead of waiting a full interval. |

The scheduler is **in-process**: it exists only while the server runs, and
stops with it. There is no cron job and nothing to uninstall.

Rules the sweep follows, which are what keep it safe to run unattended:

- **Only two statuses can move** — `TGE_ANNOUNCED` and
  `TOKEN_LIVE_NOT_TRADING`. A curated or already-confirmed row is never
  touched.
- **It never demotes.** Volume dipping below the trading bar is routine noise,
  not a retraction, and the sweep's evidence can be weaker than whatever
  produced the original row.
- **Known tokens are queried by token name**, which is the link the pipeline
  originally asserted. Only when no token is known does it fall back to the
  company name — an *inferred* link, promoted at 0.70 rather than 0.85 and
  tagged `pv: "name-match"` (or `"cmc-name-match"`), exactly as the batch
  script `verify_announced_by_name.py` does.
- **The window bounds the cost.** At 12 months that's ~109 companies, roughly
  4 minutes of API calls per sweep on the CoinGecko demo tier. Widening it to
  24 months roughly doubles both.

Sweeps and manual refreshes share a write lock, so the two can never interleave
and lose each other's changes.

An open browser tab polls `/api/snapshot` once a minute — a ~60-byte response —
and pulls the full dataset only when the timestamp actually moves. Your search,
status tiles, month, and sort survive the swap; the header timestamp is what
tells you the data underneath changed.

### Verify it's working

- The header should immediately show a company count (e.g. "Showing the
  latest 50 companies…") and a populated table — everything is embedded,
  so there's no network call to wait on.
- Try the search box, click a status tile (e.g. Post-TGE), and try the
  Fundraise Brief month picker's Load → button to confirm interactivity.
- Open browser devtools and confirm no console errors.

See [Widget features](#widget-features) for the full feature list, or
[Refreshing the data](#refreshing-the-data) to update the dataset itself.

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
app.js                       Local server (npm start / node app.js), background sweep scheduler,
                             POST /api/refresh · GET /api/snapshot · GET /api/dataset
.env.example                 Reference copy of the env vars (documentation)
.env.tpl                     1Password reference template — op inject -i .env.tpl -o .env
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
  build_widget.js             Injects the dataset into widget_template.html (also used live by app.js)
  classify.js                 Shared classification rules used by app.js's live /api/refresh
  airtable_client.js          Airtable REST API wrapper used by app.js (needs AIRTABLE_TOKEN)
  sweep.js                    Ingest + re-verification, shared by /api/refresh and the scheduler
  market_verifier.js          Runs CoinGecko then CoinMarketCap for the leftovers; what app.js calls
  market_http.js              Shared fetch helper for both market clients (429/5xx retry)
  coingecko_client.js         CoinGecko API wrapper — keyless, or Demo/Pro with COINGECKO_API_KEY
  coinmarketcap_client.js     CoinMarketCap fallback wrapper (needs COINMARKETCAP_API_KEY)
  merge_recent_rounds.js      Backfills round dates from a fresh unfiltered fetch
  update_from_airtable.py     Merges newly-added companies straight from the Airtable base
  load_brief_period.py        Loads one Fundraise Brief period, incl. curated Post-TGE upgrades
  apply_curated_post_tge.py   Applies curated "Post TGE Token" flags across ALL periods at once
  verify_announced_by_name.py Name-matches unverified TGE_ANNOUNCED companies against CoinGecko
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

- **The live Refresh button mechanizes steps 2 and 4 of the methodology
  only (announcement + market check), not the full investigation.** It
  does not do company disambiguation, on-chain verification, exchange
  listing checks, or the "Post TGE Token" curated flag (that flag lives on
  `FundingRounds`, not the `funded_companies` table the live endpoint
  reads) — running the real multi-step AI investigation for every new
  company on every click isn't practical (it would take real LLM time and
  cost per company, not something a button click can do instantly). Its
  CoinGecko match is also an exact company-name match only, which is a
  weaker signal than a real `coin_uid` — a company whose token has a
  different name than the company itself won't be found this way.
- **`name-match` results are inferred links, not asserted ones.** 180
  companies that had a token-sale-type round but no coin in TIE Terminal's
  data were resolved by matching the company name against CoinGecko
  (exact, unique-name-only; ambiguous names skipped). They're scored 0.70
  / 0.50 rather than 0.85 / 0.60 and tagged `pv: "name-match"`, and the
  widget's evidence card says plainly that the link is inferred. Spot-checks
  look right (Chiliz→CHZ, Agoric→BLD, Boundless→ZKC), but a company whose
  token simply shares its name with an unrelated coin could still slip
  through — confirm before relying on any single one.
- **Background sweeps promote companies unattended.** With
  `SWEEP_INTERVAL_MINUTES` set, status changes are written straight into the
  dataset with no human in the loop. The guardrails are real — only
  `TGE_ANNOUNCED` and `TOKEN_LIVE_NOT_TRADING` rows can move, nothing is ever
  demoted, and ambiguous matches are refused — but the *inferred* half of the
  sweep inherits every weakness of name-matching above, without the
  spot-check. A first live sweep over 109 companies produced 14 status
  changes, 6 through an asserted token link (0.85) and 8 through a company
  name (0.70): among them generic single-word names like `Aria`, `Space`,
  `LOL`, and `Axis`, plus one clear false positive — `OKX` matched a dormant
  token literally named "OKX", not OKB, and landed as
  `TOKEN_LIVE_NOT_TRADING`. Rows carry `pv: "name-match"` and a reduced
  confidence so the weak link stays visible, but treat auto-promoted
  single-word matches as unreviewed until someone looks.
- **The sweep only re-checks a window.** At the default
  `SWEEP_MAX_AGE_MONTHS=12` that is ~109 of the 702 companies whose status
  could still move; the other ~593 have older rounds and are never
  re-examined until the window is widened or a batch script is run.
- **Curated review can disagree with this project's own earlier manual
  reasoning** — e.g. Pact Labs was reasoned through as `NO_TOKEN` in an
  early manual pass of this project (its round funds Tether's USAT
  stablecoin, not an obviously Pact-Labs-native token), but Airtable's
  `Post TGE Token` flag says otherwise for it, and the automated loader
  correctly defers to the curated flag over that earlier manual guess.
- **~470 `TGE_ANNOUNCED` companies remain unresolved.** These had a
  token-sale-type round but no coin in TIE Terminal's data *and* no unique
  CoinGecko name match — so their token either isn't listed, isn't live, or
  trades under a name unrelated to the company's. Resolving these needs
  per-company research rather than a bulk pass.
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
