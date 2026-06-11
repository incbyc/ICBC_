#!/usr/bin/env python3
"""Regenerate supabase/seed/maize_buyback_records.csv from the maize workbook."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_supabase_seed import (  # noqa: E402
    ICBC_JS,
    SEED_DIR,
    csv_escape_row,
    load_js_feature_collection,
    parse_maize_workbook_rows,
    slugify,
    workbook_site_slug,
)

FIELDS = ["site_slug", "year", "farmers_impacted", "kilograms_bought", "meals_made", "notes"]


def valid_site_slugs() -> set[str]:
    data = load_js_feature_collection(ICBC_JS)
    slugs: set[str] = set()
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("Site Name") or ""
        slug = slugify(name)
        if slug:
            slugs.add(slug)
    return slugs


def write_maize_csv(rows: list[dict]) -> Path:
    path = SEED_DIR / "maize_buyback_records.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_escape_row(row, FIELDS))
    return path


def main() -> None:
    slugs = valid_site_slugs()
    rows = parse_maize_workbook_rows(slugs)
    if not rows:
        print("No maize rows parsed. Place the workbook at data/MAIZE BUYBACK PROJECT.xlsx")
        sys.exit(1)

    out = write_maize_csv(rows)
    total_kg = sum(float(row["kilograms_bought"]) for row in rows)
    total_farmers = sum(int(row["farmers_impacted"]) for row in rows)
    print(f"Wrote {len(rows)} rows -> {out}")
    print(f"Network totals: {total_farmers} farmers, {total_kg:,.1f} kg")
    for row in rows:
        print(
            f"  {row['site_slug']:12}  {row['farmers_impacted']:3} farmers  "
            f"{float(row['kilograms_bought']):>10,.1f} kg"
        )


if __name__ == "__main__":
    main()
