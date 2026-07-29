"""
load_brief_period.py

Loads every funding round TheTie flagged as part of a specific monthly
Fundraise Brief (Airtable's FundingRounds.brief_period field, a YYYY-MM
formula derived from brief_round=TRUE) and merges the companies into
data/tge_dataset_full.json.

Unlike update_from_airtable.py (which just grabs whatever's newest), this
lets you backfill or re-sync an ARBITRARY past or present brief period -
useful for catching companies/rounds that were added to Airtable after the
month already shipped, or for auditing one period's worth of coverage.

It also uses the "Post TGE Token" / "Post TGE Token added in Terminal"
checkboxes, which are curated by TheTie's own review process - the single
strongest non-CoinGecko signal available. A company flagged there is set
to POST_TGE even if it was previously UNKNOWN or TGE_ANNOUNCED (existing
CoinGecko-confirmed POST_TGE / TOKEN_LIVE_NOT_TRADING statuses are never
downgraded).

This script does NOT call Airtable itself (MCP access only exists inside a
Claude Code session). The flow is:

  1. In a Claude Code session, filter the FundingRounds table
     (tblhMpbvsCCSfWKCv in the "Fundraise Data" base, apppBDKslp00CJu9n) by
     brief_period = "<YYYY-MM>" using the Airtable MCP, fetching fields:
     company_uid, company, funding_announcement_date, funding_round_type,
     funding_amount, source_url_1, sector, "Post TGE Token",
     "Post TGE Token added in Terminal". Save the response (records +
     fieldMap of fieldId -> field name + a source block) to
     data/raw/airtable_brief_<period>.json - same shape
     data/raw/airtable_brief_2026-07.json already uses.
  2. python scripts/load_brief_period.py <period>   e.g. 2026-07
  3. node scripts/build_widget.js

Usage:
    python scripts/load_brief_period.py 2026-07
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")

TOKEN_ROUND_RE = re.compile(r"TOKEN|ICO|IEO|IDO")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def decode_record(record, field_map):
    out = {}
    for field_id, raw in record.get("cellValuesByFieldId", {}).items():
        name = field_map.get(field_id, field_id)
        if isinstance(raw, dict) and "name" in raw:
            out[name] = raw["name"]
        else:
            out[name] = raw
    return out


def first_company_uid(decoded):
    lookup = decoded.get("company_uid")
    if not isinstance(lookup, dict):
        return None
    values = lookup.get("valuesByLinkedRecordId") or {}
    for uids in values.values():
        if uids:
            return uids[0]
    return None


def company_name(decoded):
    links = decoded.get("company")
    if isinstance(links, list) and links:
        return links[0].get("name")
    return None


def _plain(value):
    """Unwraps a singleSelect-shaped {id, name, color} object to its name."""
    return value.get("name") if isinstance(value, dict) else value


def sector_list(decoded):
    sector = decoded.get("sector")
    items = []
    if isinstance(sector, dict):
        values = sector.get("valuesByLinkedRecordId") or {}
        for v in values.values():
            items.extend(v if isinstance(v, list) else [v])
    elif isinstance(sector, list):
        items = sector
    return [_plain(i) for i in items if _plain(i)]


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/load_brief_period.py <YYYY-MM>")
        sys.exit(1)

    period = sys.argv[1]
    airtable_path = os.path.join(ROOT, "data", "raw", f"airtable_brief_{period}.json")
    if not os.path.exists(airtable_path):
        print(f"Missing {airtable_path} - fetch it from Airtable first (see script docstring).")
        sys.exit(1)

    dataset = load_json(DATASET_PATH)
    airtable = load_json(airtable_path)
    field_map = airtable["fieldMap"]
    records = airtable["records"]

    by_uid = {c["u"]: c for c in dataset["companies"]}

    # Rounds within one period can repeat a company - keep only the latest.
    latest_by_uid = {}
    for record in records:
        decoded = decode_record(record, field_map)
        uid = first_company_uid(decoded)
        name = company_name(decoded)
        if not uid or not name:
            continue
        round_date = decoded.get("funding_announcement_date") or ""
        existing = latest_by_uid.get(uid)
        if existing and existing["round_date"] >= round_date:
            continue
        latest_by_uid[uid] = {
            "uid": uid,
            "name": name,
            "round_type": decoded.get("funding_round_type") or "UNSPECIFIED",
            "round_date": round_date,
            "funding_amount": decoded.get("funding_amount") or 0,
            "source_url": decoded.get("source_url_1") or "",
            "category": sector_list(decoded),
            "post_tge": bool(decoded.get("Post TGE Token")) or bool(decoded.get("Post TGE Token added in Terminal")),
        }

    added, upgraded_to_post_tge, backfilled_dates = 0, 0, 0

    for row in latest_by_uid.values():
        existing = by_uid.get(row["uid"])

        if existing:
            if row["post_tge"] and existing["s"] not in ("POST_TGE", "TOKEN_LIVE_NOT_TRADING"):
                existing["s"] = "POST_TGE"
                existing["f"] = 0.75
                existing["pv"] = "curated"
                upgraded_to_post_tge += 1
            if not existing.get("rd") or row["round_date"] > existing["rd"]:
                existing["rt"] = row["round_type"]
                existing["rd"] = row["round_date"]
                existing["ra"] = row["funding_amount"]
                existing["su"] = row["source_url"]
                backfilled_dates += 1
            if not existing.get("c") and row["category"]:
                existing["c"] = row["category"]
            continue

        if row["post_tge"]:
            status, confidence = "POST_TGE", 0.75
        elif TOKEN_ROUND_RE.search(row["round_type"].upper()):
            status, confidence = "TGE_ANNOUNCED", 0.35
        else:
            status, confidence = "UNKNOWN", 0.1

        entry = {
            "u": row["uid"],
            "n": row["name"],
            "c": row["category"],
            "s": status,
            "f": confidence,
        }
        if row["post_tge"]:
            entry["pv"] = "curated"
        entry.update({
            "rt": row["round_type"],
            "rd": row["round_date"],
            "ra": row["funding_amount"],
            "su": row["source_url"],
        })
        dataset["companies"].append(entry)
        by_uid[row["uid"]] = entry
        added += 1

    dataset["companies"].sort(key=lambda c: c["n"].lower())

    status_counts = {}
    for c in dataset["companies"]:
        status_counts[c["s"]] = status_counts.get(c["s"], 0) + 1
    dataset["stats"] = {"total": len(dataset["companies"]), **status_counts}

    save_json(DATASET_PATH, dataset)

    print(f"Brief period: {period}")
    print(f"Rounds in this period: {len(records)}  |  distinct companies: {len(latest_by_uid)}")
    print(f"New companies added: {added}")
    print(f"Existing companies upgraded to POST_TGE via curated flag: {upgraded_to_post_tge}")
    print(f"Existing companies with round data backfilled: {backfilled_dates}")
    print(f"New dataset total: {dataset['stats']['total']}")
    print(f"Wrote {DATASET_PATH}")
    print("Next: node scripts/build_widget.js")


if __name__ == "__main__":
    main()
