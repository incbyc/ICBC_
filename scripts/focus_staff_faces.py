#!/usr/bin/env python3
"""Re-crop existing staff photos in the seed folder to centre on faces.

Usage (from project root):
    python scripts/focus_staff_faces.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAFF_CSV = ROOT / "supabase" / "seed" / "staff.csv"

sys.path.insert(0, str(ROOT))

from scripts.face_focus import crop_portrait_to_face  # noqa: E402


def main() -> None:
    if not STAFF_CSV.is_file():
        raise SystemExit(f"Missing {STAFF_CSV}")

    updated = 0
    skipped = 0
    with STAFF_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            photo_path = (row.get("photo_url") or "").strip()
            if not photo_path:
                skipped += 1
                continue
            file_path = ROOT / photo_path
            if not file_path.is_file():
                print(f"Missing file: {photo_path}")
                skipped += 1
                continue
            is_pastor = (row.get("role") or "").strip() == "Pastor"
            original = file_path.read_bytes()
            processed, focus = crop_portrait_to_face(original, is_pastor=is_pastor)
            if processed == original:
                print(f"No face detected: {photo_path}")
                skipped += 1
                continue
            out_path = file_path if file_path.suffix.lower() in {".jpg", ".jpeg"} else file_path.with_suffix(".jpg")
            out_path.write_bytes(processed)
            updated += 1
            print(f"Cropped: {out_path.relative_to(ROOT)} (pastor={is_pastor})")

    print(f"Done. Cropped {updated} photo(s), skipped {skipped}.")


if __name__ == "__main__":
    main()
