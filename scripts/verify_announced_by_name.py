"""
verify_announced_by_name.py

Closes the gap where companies with a token-sale-type round (ICO/IEO/IDO/
token sale) but NO coin linked in TIE Terminal's data were never checked
against CoinGecko at all - they sat at TGE_ANNOUNCED regardless of whether
their token was actually live and trading.

Matching rule (deliberately strict, to avoid false POST_TGE calls):
  - normalize company name and CoinGecko coin name (lowercase, alphanumeric)
  - require an EXACT match on coin NAME (not symbol - a 3-4 letter symbol
    colliding with a company name is far too weak a signal)
  - require the matched name to be UNIQUE across CoinGecko's whole coin list;
    any name shared by 2+ coins is skipped as ambiguous rather than guessed
  - require length >= 3 characters

Because the company->token link here is INFERRED from a name match rather
than asserted by TIE Terminal's own coin_uid, results are tagged
pv="name-match" and scored below the coin_uid-verified path (0.70 vs 0.85).
The widget renders a distinct evidence card for this provenance so the
weaker linkage is visible to the reader, not hidden behind an identical
"POST_TGE" pill.

Inputs (produced by the fetch/match steps - see repo README):
  data/raw/res716_matches.json   company -> coingecko id, exact unique matches
  data/raw/res716_markets.json   live market rows for those ids

Usage:
    python scripts/verify_announced_by_name.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")
MATCHES_PATH = os.path.join(ROOT, "data", "raw", "res716_matches.json")
MARKETS_PATH = os.path.join(ROOT, "data", "raw", "res716_markets.json")

ACTIVE_VOLUME_THRESHOLD = 1000  # same bar the rest of the pipeline uses


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    dataset = load_json(DATASET_PATH)
    matches = load_json(MATCHES_PATH)
    markets = load_json(MARKETS_PATH)

    market_by_id = {m["id"]: m for m in markets}
    by_uid = {c["u"]: c for c in dataset["companies"]}

    promoted_trading, promoted_dormant, no_market, skipped_not_announced = 0, 0, 0, 0
    promoted_names = []

    for m in matches:
        company = by_uid.get(m["u"])
        if company is None:
            continue

        # Only touch the exact bucket this script is meant to fix. Never
        # overwrite a curated call or an existing market-verified status.
        if company["s"] != "TGE_ANNOUNCED" or company.get("tn") or company.get("pv"):
            skipped_not_announced += 1
            continue

        market = market_by_id.get(m["cgId"])
        if market is None:
            no_market += 1
            continue

        volume = market.get("total_volume") or 0
        price = market.get("current_price")
        actively_trading = volume >= ACTIVE_VOLUME_THRESHOLD

        company["s"] = "POST_TGE" if actively_trading else "TOKEN_LIVE_NOT_TRADING"
        company["f"] = 0.70 if actively_trading else 0.50
        company["pv"] = "name-match"
        company["tn"] = market.get("name") or m["n"]
        company["ts"] = (market.get("symbol") or "").upper()
        company["mp"] = round(price, 2) if isinstance(price, (int, float)) else 0
        company["mc"] = round(market.get("market_cap") or 0)
        company["mv"] = round(volume)

        if actively_trading:
            promoted_trading += 1
            promoted_names.append(f"{company['n']} -> {company['ts']}")
        else:
            promoted_dormant += 1

    dataset["companies"].sort(key=lambda c: c["n"].lower())
    status_counts = {}
    for c in dataset["companies"]:
        status_counts[c["s"]] = status_counts.get(c["s"], 0) + 1
    dataset["stats"] = {"total": len(dataset["companies"]), **status_counts}

    with open(DATASET_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f)

    print(f"Name-matched candidates: {len(matches)}  |  with live market data: {len(markets)}")
    print(f"-> POST_TGE (actively trading): {promoted_trading}")
    print(f"-> TOKEN_LIVE_NOT_TRADING (listed, negligible volume): {promoted_dormant}")
    print(f"Matched but no market data returned: {no_market}")
    print(f"Skipped (already classified/curated, left alone): {skipped_not_announced}")
    print(f"\nSample promotions:")
    for n in promoted_names[:20]:
        print(f"  + {n}")
    print(f"\nNew stats: {json.dumps(dataset['stats'])}")
    print(f"Wrote {DATASET_PATH}")
    print("Next: node scripts/build_widget.js")


if __name__ == "__main__":
    main()
