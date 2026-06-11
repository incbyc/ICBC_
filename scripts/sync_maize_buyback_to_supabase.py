#!/usr/bin/env python3
"""Push maize_buyback_records.csv to Supabase (service_role key required)."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from supabase_sync import SupabaseSeedSync  # noqa: E402

CSV_PATH = ROOT / "supabase" / "seed" / "maize_buyback_records.csv"
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"
STALE_SLUGS = ("mantabeni",)


def load_service_role_key() -> tuple[str, str]:
    text = SECRETS_PATH.read_text(encoding="utf-8")
    url_match = re.search(r'SUPABASE_URL\s*=\s*"([^"]+)"', text)
    key_match = re.search(r'SUPABASE_SERVICE_ROLE_KEY\s*=\s*"([^"]+)"', text)
    if not url_match or not key_match:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .streamlit/secrets.toml")
    return url_match.group(1), key_match.group(1)


def main() -> None:
    url, key = load_service_role_key()
    sync = SupabaseSeedSync(url, key)

    for slug in STALE_SLUGS:
        try:
            print(sync.delete_row("maize_buyback_records", {"site_slug": slug, "year": "2025"}))
        except Exception as err:
            print(f"Skip delete {slug}: {err}")

    with CSV_PATH.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        print(sync.sync_row("maize_buyback_records", row))


if __name__ == "__main__":
    main()
