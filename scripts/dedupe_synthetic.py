"""
dedupe_synthetic.py

Repairs duplicate company entries created before the ingest dedup fix landed.

A company first seen in Airtable before TIE Terminal assigned it a
company_uid is stored under a synthetic "airtable_<recordId>" key. Once the
real uid appears, ingest used to key only on that uid and add a SECOND entry
for the same Airtable record - a silent duplicate (this happened to
Attestable and TradeZero). scripts/sweep.js now drops the synthetic twin on
ingest, but rows duplicated before that fix still need clearing once.

Safety: a pair is only merged when BOTH of these hold, so two genuinely
different companies that happen to share a name are never collapsed:
  - one entry's uid starts with "airtable_" and the other's with "company_"
  - the names are identical

Any field present on the synthetic row but missing on the canonical one is
carried over before the synthetic row is dropped, so nothing is lost.

Usage:
    python scripts/dedupe_synthetic.py          # report only
    python scripts/dedupe_synthetic.py --apply  # write changes
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(ROOT, "data", "tge_dataset_full.json")


def main():
    apply_changes = "--apply" in sys.argv

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    by_name = {}
    for c in dataset["companies"]:
        by_name.setdefault(c["n"], []).append(c)

    merges = []
    for name, entries in by_name.items():
        if len(entries) < 2:
            continue
        synthetic = [c for c in entries if c["u"].startswith("airtable_")]
        canonical = [c for c in entries if c["u"].startswith("company_")]
        # Only an unambiguous 1:1 synthetic/canonical pair is safe to merge.
        if len(synthetic) == 1 and len(canonical) == 1:
            merges.append((synthetic[0], canonical[0]))

    for synth, canon in merges:
        # Carry over anything the canonical row is missing, then drop the twin.
        for key, value in synth.items():
            if key not in ("u",) and key not in canon:
                canon[key] = value
        dataset["companies"].remove(synth)

    status_counts = {}
    for c in dataset["companies"]:
        status_counts[c["s"]] = status_counts.get(c["s"], 0) + 1
    dataset["stats"] = {"total": len(dataset["companies"]), **status_counts}

    print(f"Merge pairs found: {len(merges)}")
    for synth, canon in merges:
        print(f"  {canon['n']}: dropped {synth['u']} -> kept {canon['u']}")

    remaining_dupe_names = [n for n, e in by_name.items() if len(e) > 1 and not any(
        s is synth for synth, _ in merges for s in e)]
    print(f"Names still duplicated (left alone - not a synthetic/canonical pair): {len(remaining_dupe_names)}")

    if apply_changes:
        with open(DATASET_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f)
        print(f"\nWrote {DATASET_PATH} - new total {dataset['stats']['total']}")
        print("Next: node scripts/build_widget.js")
    else:
        print("\n(dry run - pass --apply to write)")


if __name__ == "__main__":
    main()
