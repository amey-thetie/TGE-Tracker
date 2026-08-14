"""
apply_curated_post_tge.py

Applies TheTie's curated "Post TGE Token" / "Post TGE Token added in Terminal"
flags to the dataset, across ALL Fundraise Brief periods at once.

This supersedes the per-period approach in load_brief_period.py for the
specific job of syncing curated flags: rather than loading one YYYY-MM period
at a time (and only ever getting that month's curation), this reads a single
export of every FundingRounds row where either curated checkbox is set,
regardless of period.

The curated flag is TheTie's own human review and is the strongest non-market
signal available - stronger than this project's inferred classification. So a
curated company is set to POST_TGE even with no CoinGecko match, tagged
pv="curated" so the widget explains the difference. Existing
CoinGecko-confirmed statuses (POST_TGE / TOKEN_LIVE_NOT_TRADING) are never
downgraded.

Refresh the input in a Claude Code session by filtering the FundingRounds
table (tblhMpbvsCCSfWKCv in base apppBDKslp00CJu9n) on
"Post TGE Token" = true OR "Post TGE Token added in Terminal" = true, then
saving the flattened result to data/raw/airtable_curated_post_tge.json.

Usage:
    python scripts/apply_curated_post_tge.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")
CURATED_PATH = os.path.join(ROOT, "data", "raw", "airtable_curated_post_tge.json")

# Statuses that already carry independent market verification - never downgrade.
MARKET_VERIFIED = ("POST_TGE", "TOKEN_LIVE_NOT_TRADING")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    dataset = load_json(DATASET_PATH)
    curated = load_json(CURATED_PATH)["records"]

    by_uid = {c["u"]: c for c in dataset["companies"]}

    upgraded, already_post_tge, added, backfilled = 0, 0, 0, 0
    upgraded_names, added_names = [], []

    for row in curated:
        uid = row.get("company_uid")
        name = row.get("company")
        if not uid or not name:
            continue

        existing = by_uid.get(uid)

        if existing is None:
            entry = {
                "u": uid,
                "n": name,
                "c": [],
                "s": "POST_TGE",
                "f": 0.75,
                "pv": "curated",
                "rt": row.get("round_type") or "UNSPECIFIED",
                "rd": row.get("round_date") or "",
                "ra": row.get("funding_amount") or 0,
                "su": row.get("source_url") or "",
            }
            dataset["companies"].append(entry)
            by_uid[uid] = entry
            added += 1
            added_names.append(name)
            continue

        if existing["s"] in MARKET_VERIFIED:
            already_post_tge += 1
        else:
            existing["s"] = "POST_TGE"
            existing["f"] = 0.75
            existing["pv"] = "curated"
            upgraded += 1
            upgraded_names.append(f"{name} ({row.get('brief_period', '?')})")

        # Backfill round detail if this curated round is newer than what we have.
        round_date = row.get("round_date") or ""
        if round_date and (not existing.get("rd") or round_date > existing["rd"]):
            existing["rt"] = row.get("round_type") or "UNSPECIFIED"
            existing["rd"] = round_date
            existing["ra"] = row.get("funding_amount") or 0
            existing["su"] = row.get("source_url") or ""
            backfilled += 1

    dataset["companies"].sort(key=lambda c: c["n"].lower())

    status_counts = {}
    for c in dataset["companies"]:
        status_counts[c["s"]] = status_counts.get(c["s"], 0) + 1
    dataset["stats"] = {"total": len(dataset["companies"]), **status_counts}

    with open(DATASET_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f)

    periods = sorted({r.get("brief_period") for r in curated if r.get("brief_period")})
    print(f"Curated records read: {len(curated)}  |  periods covered: {', '.join(periods)}")
    print(f"Upgraded to POST_TGE (curated): {upgraded}")
    for n in upgraded_names:
        print(f"  + {n}")
    print(f"Already market-verified (left alone): {already_post_tge}")
    print(f"New companies added: {added}")
    for n in added_names:
        print(f"  + {n}")
    print(f"Round detail backfilled: {backfilled}")
    print(f"New dataset total: {dataset['stats']['total']}")
    print(f"Wrote {DATASET_PATH}")
    print("Next: node scripts/build_widget.js")


if __name__ == "__main__":
    main()
