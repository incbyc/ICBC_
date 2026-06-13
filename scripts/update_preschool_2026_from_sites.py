#!/usr/bin/env python3
"""Set 2026 preschool enrollment from data/ICBCSites_6.js (current children + teachers)."""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"
SITES_JS = ROOT / "data" / "ICBCSites_6.js"
PRESCHOOL_CSV = SEED_DIR / "preschool_enrollment.csv"
YEAR = 2026
NOTE = "Source: ICBCSites_6.js · current pre-school enrollment 2026"
# Sites confirmed closed / no pre-school this year (overrides stale map data).
NO_PRESCHOOL_2026 = frozenset({"mangcongco", "sigengeni", "makhungutja"})


def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "site"


def parse_preschool_summary(summary: str | None) -> dict[str, int] | None:
    raw = (summary or "").strip()
    if not raw or raw.lower() in {"none", "n/a"}:
        return None
    children = re.search(r"Children:\s*(\d+)", raw, flags=re.I)
    if not children:
        return None
    teachers = re.search(r"Teachers:\s*(\d+)", raw, flags=re.I)
    payload: dict[str, int] = {"children_count": int(children.group(1))}
    if teachers:
        payload["teachers_count"] = int(teachers.group(1))
    return payload


def load_sites_enrollment() -> dict[str, dict[str, int]]:
    text = SITES_JS.read_text(encoding="utf-8")
    match = re.search(r"var\s+json_ICBCSites_6\s*=\s*(\{.*\})\s*;?\s*$", text, flags=re.S)
    if not match:
        raise SystemExit(f"Could not parse JSON from {SITES_JS}")
    data = json.loads(match.group(1))
    by_slug: dict[str, dict[str, int]] = {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        site_name = props.get("Site Name") or ""
        slug = slugify(site_name)
        if not slug:
            continue
        parsed = parse_preschool_summary(props.get("PreSchool"))
        if parsed:
            by_slug[slug] = parsed
        elif (props.get("PreSchool") or "").strip().lower() == "none":
            by_slug[slug] = {"children_count": 0}
    for slug in NO_PRESCHOOL_2026:
        by_slug[slug] = {"children_count": 0}
    return by_slug


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def apply_enrollment(rows: list[dict[str, str]], by_slug: dict[str, dict[str, int]]) -> tuple[int, int]:
    updated = 0
    existing_2026 = {
        (row.get("site_slug") or "").strip().lower()
        for row in rows
        if str(row.get("year") or "").strip() == str(YEAR)
    }
    for row in rows:
        if str(row.get("year") or "").strip() != str(YEAR):
            continue
        slug = (row.get("site_slug") or "").strip().lower()
        if slug not in by_slug:
            continue
        payload = by_slug[slug]
        new_children = str(payload["children_count"])
        new_teachers = str(payload.get("teachers_count", "") or "")
        old_children = str(row.get("children_count") or "").strip()
        old_teachers = str(row.get("teachers_count") or "").strip()
        if new_children != old_children or new_teachers != old_teachers:
            row["children_count"] = new_children
            row["teachers_count"] = new_teachers
            row["notes"] = NOTE
            updated += 1
            print(f"  {slug}: children {old_children} -> {new_children}, teachers {old_teachers or '—'} -> {new_teachers or '—'}")

    added = 0
    fieldnames = list(rows[0].keys()) if rows else ["site_slug", "year", "children_count", "teachers_count", "notes"]
    for slug, payload in sorted(by_slug.items()):
        if slug in existing_2026:
            continue
        rows.append(
            {
                "site_slug": slug,
                "year": str(YEAR),
                "children_count": str(payload["children_count"]),
                "teachers_count": str(payload.get("teachers_count", "") or ""),
                "notes": NOTE,
            }
        )
        added += 1
        print(f"  + {slug}: children={payload['children_count']} teachers={payload.get('teachers_count', '')}")

    rows.sort(key=lambda row: ((row.get("site_slug") or "").lower(), int(row.get("year") or 0)))
    return updated, added


def push_to_supabase() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from fix_pastor_spouses_and_sync import load_secrets, read_csv as read_csv_sync, push_table
    from supabase_sync import build_sync_client

    url, key = load_secrets()
    client = build_sync_client(url, key)
    if not client:
        raise SystemExit("Could not connect Supabase sync client.")
    push_table(client, "preschool_enrollment", "preschool_enrollment.csv")


def main() -> None:
    if not SITES_JS.is_file():
        raise SystemExit(f"Missing {SITES_JS}")
    if not PRESCHOOL_CSV.is_file():
        raise SystemExit(f"Missing {PRESCHOOL_CSV}")

    by_slug = load_sites_enrollment()
    print(f"Loaded {len(by_slug)} site(s) with 2026 pre-school data from ICBCSites_6.js")

    fieldnames, rows = read_csv(PRESCHOOL_CSV)
    print(f"Updating {PRESCHOOL_CSV} …")
    updated, added = apply_enrollment(rows, by_slug)
    write_csv(PRESCHOOL_CSV, fieldnames, rows)
    print(f"Updated {updated} row(s), added {added} row(s).\n")

    print("Pushing preschool_enrollment to Supabase …")
    push_to_supabase()
    print("Done.")


if __name__ == "__main__":
    main()
