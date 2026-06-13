#!/usr/bin/env python3
"""Align pastor spouse surnames, apply manual fixes, push staff + rainfall to Supabase."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from staff_spouse_utils import align_spouse_surname, is_invalid_spouse  # noqa: E402
from supabase_sync import build_sync_client  # noqa: E402

MANUAL_SPOUSE: dict[tuple[str, str], str] = {
    ("moneni", "Samuel Dlamini"): "Happiness Dlamini",
}


def load_secrets() -> tuple[str, str]:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.is_file():
        raise SystemExit("Missing .streamlit/secrets.toml with Supabase credentials.")
    text = secrets_path.read_text(encoding="utf-8")
    url_match = re.search(r'SUPABASE_URL\s*=\s*"([^"]+)"', text)
    key_match = re.search(r'SUPABASE_SERVICE_ROLE_KEY\s*=\s*"([^"]+)"', text)
    if not url_match or not key_match:
        raise SystemExit("Could not read SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY from secrets.toml")
    return url_match.group(1), key_match.group(1)


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


def fix_staff_csv(staff_path: Path) -> int:
    fieldnames, rows = read_csv(staff_path)
    for column in ("spouse_name", "children_count"):
        if column not in fieldnames:
            fieldnames.append(column)

    changed = 0
    for row in rows:
        if (row.get("role") or "").strip() != "Pastor":
            continue

        site_slug = (row.get("site_slug") or "").strip().lower()
        pastor_name = (row.get("full_name") or "").strip()
        key = (site_slug, pastor_name)

        if key in MANUAL_SPOUSE:
            new_spouse = MANUAL_SPOUSE[key]
        else:
            current = row.get("spouse_name", "")
            if is_invalid_spouse(current):
                current = ""
            new_spouse = align_spouse_surname(pastor_name, current)

        old_spouse = (row.get("spouse_name") or "").strip()
        if new_spouse != old_spouse:
            row["spouse_name"] = new_spouse
            changed += 1
            print(f"  {site_slug}: {pastor_name!r} spouse -> {new_spouse!r}")

    write_csv(staff_path, fieldnames, rows)
    return changed


def push_table(client, table_key: str, csv_name: str) -> None:
    path = SEED_DIR / csv_name
    _, rows = read_csv(path)
    message = client.sync_all(table_key, rows)
    print(message)


def main() -> None:
    staff_path = SEED_DIR / "staff.csv"
    print("Fixing pastor spouse surnames in staff.csv …")
    updated = fix_staff_csv(staff_path)
    print(f"Updated {updated} pastor spouse row(s).\n")

    url, key = load_secrets()
    client = build_sync_client(url, key)
    if not client:
        raise SystemExit("Could not connect Supabase sync client.")

    print("Pushing staff to Supabase …")
    push_table(client, "staff", "staff.csv")
    print("Pushing rainfall_monthly to Supabase …")
    push_table(client, "rainfall_monthly", "rainfall_monthly.csv")
    print("\nDone.")


if __name__ == "__main__":
    main()
