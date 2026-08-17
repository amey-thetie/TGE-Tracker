"""
update_from_airtable.py

Adds any companies newly added to the Fundraise Brief's Airtable base
("Fundraise Data" -> funded_companies table) that aren't yet in
data/tge_dataset_full.json.

The Airtable "funded_companies" table is the source of truth for which
companies exist in the Fundraise Brief at all - a company can show up there
(with a created_timestamp) before it's ever fully processed into TIE
Terminal's own fundraising-rounds API (no company_uid, no round data yet).
This script surfaces those newest additions immediately rather than waiting
for them to propagate through TIE Terminal.

This script does NOT call Airtable itself - Airtable MCP access only exists
inside a Claude Code session. The actual flow is:

  1. In a Claude Code session, fetch recent funded_companies records sorted
     by created_timestamp desc (see README.md "Refreshing the data") and
     save the raw response + a "fieldMap" (fieldId -> field name) to
     data/raw/airtable_recent_companies.json (same shape this script reads).
  2. Run this script to merge any company_uids not already in the dataset.
  3. node scripts/build_dataset.js is NOT needed for this step - this script
     writes directly to data/tge_dataset_full.json - just rebuild the widget:
     node scripts/build_widget.js

Usage:
    python scripts/update_from_airtable.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")
AIRTABLE_PATH = os.path.join(ROOT, "data", "raw", "airtable_recent_companies.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def decode_record(record, field_map):
    """Turns {fieldId: rawValue} into {fieldName: simplifiedValue}."""
    out = {}
    for field_id, raw in record.get("cellValuesByFieldId", {}).items():
        name = field_map.get(field_id, field_id)
        if isinstance(raw, dict) and "name" in raw:
            out[name] = raw["name"]  # singleSelect -> plain string
        else:
            out[name] = raw
    return out


def extract_last_round_date(decoded):
    """METRIC_last_round_date is a lookup: {linkedRecordIds, valuesByLinkedRecordId}."""
    lookup = decoded.get("METRIC_last_round_date")
    if not isinstance(lookup, dict):
        return None
    values = lookup.get("valuesByLinkedRecordId") or {}
    for dates in values.values():
        if dates:
            return dates[0]
    return None


def main():
    dataset = load_json(DATASET_PATH)
    airtable = load_json(AIRTABLE_PATH)
    field_map = airtable["fieldMap"]
    records = airtable["records"]

    by_uid = {c["u"]: c for c in dataset["companies"]}

    added, backfilled_dates, skipped_no_uid_already_seen = 0, 0, 0
    promoted_from_synthetic = 0
    new_entries = []

    for record in records:
        decoded = decode_record(record, field_map)
        name = decoded.get("funded_company")
        if not name:
            continue

        company_uid = decoded.get("company_uid")
        last_round_date = extract_last_round_date(decoded)
        is_token_issuer = decoded.get("token_issuer") == "TRUE"

        # A company first seen before TIE Terminal assigned it a company_uid was
        # stored under a synthetic airtable_<recordId> key. Once the real uid
        # exists, keying only on that uid would add a SECOND entry for the same
        # Airtable record - a silent duplicate. Drop the synthetic twin first:
        # same record ID means same company, not a name collision.
        if company_uid:
            synthetic_key = f"airtable_{record['id']}"
            twin = by_uid.pop(synthetic_key, None)
            if twin is not None:
                dataset["companies"].remove(twin)
                promoted_from_synthetic += 1

        if company_uid and company_uid in by_uid:
            # Already tracked - only backfill the round date display if this
            # Airtable lookup is more recent than what we have, never touch
            # existing TGE status/token classification.
            existing = by_uid[company_uid]
            if last_round_date and (not existing.get("rd") or last_round_date > existing["rd"]):
                existing["rt"] = existing.get("rt") or "UNSPECIFIED"
                existing["rd"] = last_round_date
                backfilled_dates += 1
            continue

        # Genuinely new to our dataset - either just processed into TIE
        # Terminal (has a company_uid) or brand new to the Brief itself
        # (no company_uid yet, e.g. added to Airtable within the last day).
        uid = company_uid or f"airtable_{record['id']}"
        if uid in by_uid:
            skipped_no_uid_already_seen += 1
            continue

        status = "TGE_ANNOUNCED" if is_token_issuer else "UNKNOWN"
        confidence = 0.3 if is_token_issuer else 0.1

        entry = {
            "u": uid,
            "n": name,
            "c": [],
            "s": status,
            "f": confidence,
        }
        if last_round_date:
            entry["rt"] = "UNSPECIFIED"
            entry["rd"] = last_round_date
            entry["ra"] = 0
            entry["su"] = ""

        dataset["companies"].append(entry)
        by_uid[uid] = entry
        new_entries.append(name)
        added += 1

    dataset["companies"].sort(key=lambda c: c["n"].lower())

    status_counts = {}
    for c in dataset["companies"]:
        status_counts[c["s"]] = status_counts.get(c["s"], 0) + 1
    dataset["stats"] = {"total": len(dataset["companies"]), **status_counts}

    save_json(DATASET_PATH, dataset)

    print(f"Airtable source: {airtable['source']['baseName']} / {airtable['source']['tableName']}")
    print(f"Records checked: {len(records)}")
    print(f"New companies added: {added}")
    if new_entries:
        print("  " + "\n  ".join(new_entries))
    print(f"Existing companies with round date backfilled: {backfilled_dates}")
    print(f"Synthetic airtable_* entries merged into a real company_uid: {promoted_from_synthetic}")
    print(f"New dataset total: {dataset['stats']['total']}")
    print(f"Wrote {DATASET_PATH}")
    print("Next: node scripts/build_widget.js")


if __name__ == "__main__":
    main()
