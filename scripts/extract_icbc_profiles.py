#!/usr/bin/env python3
"""Extract pastor family and compassionate-care data from ICBC profile Word documents."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from staff_spouse_utils import align_spouse_surname, is_invalid_spouse, pastor_surname

DEFAULT_PROFILES_DIR = (
    ROOT.parent
    / "ICBC, Missions & JSH - Documents"
    / "ICBC CSPs"
    / "ICBC PROFILES"
)

SITE_PROFILES_CSV = SEED_DIR / "icbc_site_profiles.csv"
SITE_PROFILES_JS = ROOT / "js" / "icbc-site-profiles-data.js"


def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "site"


def profile_slug_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"\bprofile\b", "", stem, flags=re.I)
    stem = stem.replace("-", " ").strip()
    return slugify(stem)


def docx_plain_text(path: Path) -> str:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(path)
    parts: list[str] = []
    for node in doc.element.body.iter(qn("w:t")):
        if node.text:
            parts.append(node.text)
    return "".join(parts)


def normalize_profile_text(text: str) -> str:
    """Insert spaces where Word runs glued keywords to names (e.g. SPOUSEThobile)."""
    text = re.sub(r"\s+", " ", text.strip())
    for pattern in (
        r"(?i)(pastors?)([A-Z][a-z])",
        r"(?i)(spouse|wife)([A-Z][a-z])",
        r"(?i)(children)([A-Z][a-z])",
        r"(?i)(members?)([0-9])",
        r"(?i)(members?\s*:)([0-9])",
    ):
        text = re.sub(pattern, r"\1 \2", text)
    return re.sub(r"\s+", " ", text)


def count_children(raw: str, pastor_name: str = "") -> int:
    """Count pastor children from profile text (names are not stored)."""
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if not value or re.fullmatch(r"(none|single|n/a)\.?", value, flags=re.I):
        return 0
    if re.fullmatch(r"\d+", value):
        count = int(value)
        return count if count <= 20 else 0

    surname = pastor_surname(pastor_name)

    if "," in value:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        parts = [part for part in parts if not re.fullmatch(r"none\.?", part, flags=re.I)]
        return len(parts)

    if re.search(r"\band\b", value, flags=re.I):
        parts = [part.strip() for part in re.split(r"\band\b", value, flags=re.I) if part.strip()]
        parts = [part for part in parts if not re.fullmatch(r"none\.?", part, flags=re.I)]
        return len(parts)

    if surname and len(surname) >= 2:
        surname_count = len(re.findall(rf"\b{re.escape(surname)}\b", value, flags=re.I))
        if surname_count > 0:
            return surname_count

    return 1


def sanitize_spouse(value: str) -> str:
    spouse = re.sub(r"\s{2,}", " ", value.strip())
    spouse = re.sub(r"^[.\s]+", "", spouse)
    if not spouse or re.fullmatch(r"(none|single|n/a)\.?", spouse, flags=re.I):
        return ""
    if len(spouse) > 55:
        return ""
    if re.search(
        r"qualification|pre\s*school|church\s+attendance|children|pastors?|certificate|diploma|degree",
        spouse,
        flags=re.I,
    ):
        return ""
    return spouse


def parse_compassionate_care_members(text: str) -> int | None:
    normalized = normalize_profile_text(text)
    patterns = (
        r"compassionate\s+care\s+team[^0-9]{0,40}members?\s*:?\s*(\d+)",
        r"compassionate\s+care[^0-9]{0,40}members?\s*:?\s*(\d+)",
        r"care\s+team[^0-9]{0,20}members?\s*:?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.I)
        if match:
            return int(match.group(1))
    return None


def parse_profile_text(text: str) -> dict[str, str | int | None]:
    normalized = normalize_profile_text(text)
    pastor_match = re.search(
        r"pastor\s*:?\s*(.+?)(?:spouse|wife|children)\s*:?",
        normalized,
        flags=re.I,
    )

    spouse = ""
    spouse_match = re.search(
        r"(?:spouse|wife)\s*:?\s*(.+?)(?:children|pastors?|pre\s*school|church\s+attendance|qualification|climate|water\s+source|region:|compassionate)",
        normalized,
        flags=re.I,
    )
    if spouse_match:
        spouse = sanitize_spouse(spouse_match.group(1))

    children_match = re.search(
        r"children\s*:?\s*(.+?)(?:pastors?['\u2019]?|pre\s*school|church\s+attendance|qualification|diploma|degree|climate|water\s+source|region:|spouse|wife|compassionate|men\s+\d|women\s+\d|youth\s+\d)",
        normalized,
        flags=re.I,
    )
    children_raw = children_match.group(1).strip() if children_match else ""
    if re.match(r"^(none|single|n/a)\.?$", children_raw, flags=re.I):
        children_raw = ""
    if children_raw.lower().startswith("pastors"):
        children_raw = ""

    if not spouse:
        alt_spouse = re.search(
            r"children\s+(?:none|n/a)\s+(?:spouse|wife)\s+(.+?)(?:pastors?|pre\s*school|qualification|climate|compassionate)",
            normalized,
            flags=re.I,
        )
        if alt_spouse:
            spouse = sanitize_spouse(alt_spouse.group(1))

    cc_members = parse_compassionate_care_members(text)
    pastor_name = pastor_match.group(1).strip() if pastor_match else ""

    return {
        "pastor_name": pastor_name,
        "spouse_name": spouse,
        "children_count": count_children(children_raw, pastor_name),
        "compassionate_care_members": cc_members,
    }


def extract_profiles(profiles_dir: Path) -> dict[str, dict[str, str | int | None]]:
    results: dict[str, dict[str, str | int | None]] = {}
    for path in sorted(profiles_dir.glob("*.docx")):
        slug = profile_slug_from_filename(path.name)
        try:
            parsed = parse_profile_text(docx_plain_text(path))
        except Exception as exc:
            print(f"WARN {path.name}: {exc}", file=sys.stderr)
            continue
        if (
            parsed["spouse_name"]
            or parsed["children_count"]
            or parsed.get("compassionate_care_members") is not None
        ):
            results[slug] = parsed
            print(
                f"{slug}: spouse={parsed['spouse_name']!r} "
                f"children={parsed['children_count']} "
                f"care={parsed.get('compassionate_care_members')}"
            )
    return results


def is_bad_spouse(value: str) -> bool:
    return bool(is_invalid_spouse(value))


def write_site_profiles_csv(profiles: dict[str, dict[str, str | int | None]], out_path: Path) -> None:
    fieldnames = ["site_slug", "compassionate_care_members"]
    rows = []
    for slug in sorted(profiles):
        cc = profiles[slug].get("compassionate_care_members")
        if cc is None:
            continue
        rows.append({"site_slug": slug, "compassionate_care_members": cc})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_site_profiles_js(profiles: dict[str, dict[str, str | int | None]], out_path: Path) -> None:
    payload: dict[str, dict[str, int]] = {}
    for slug in sorted(profiles):
        cc = profiles[slug].get("compassionate_care_members")
        if cc is None:
            continue
        payload[slug] = {"compassionate_care_members": int(cc)}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "// Auto-generated from ICBC profile Word docs.",
        "// Refresh: python scripts/extract_icbc_profiles.py",
        "window.ICBC_SITE_PROFILES_SEED = " + json.dumps(payload, indent=4) + ";",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def apply_to_staff_csv(profiles: dict[str, dict[str, str | int | None]], staff_path: Path) -> int:
    with staff_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        for column in ("spouse_name", "children_count"):
            if column not in fieldnames:
                fieldnames.append(column)
        rows = list(reader)

    updated = 0
    for row in rows:
        if (row.get("role") or "").strip() != "Pastor":
            continue
        slug = slugify(row.get("site_slug", ""))
        profile = profiles.get(slug)
        if not profile:
            continue
        row.setdefault("spouse_name", "")
        row.setdefault("children_count", "")
        changed = False
        current_spouse = (row.get("spouse_name") or "").strip()
        profile_spouse = str(profile.get("spouse_name") or "").strip()
        if profile_spouse and (not current_spouse or is_bad_spouse(current_spouse)):
            row["spouse_name"] = align_spouse_surname(
                row.get("full_name", ""),
                profile_spouse,
            )
            changed = True
        elif current_spouse:
            aligned = align_spouse_surname(row.get("full_name", ""), current_spouse)
            if aligned != current_spouse:
                row["spouse_name"] = aligned
                changed = True
        if profile.get("children_count") is not None:
            profile_children = str(profile["children_count"])
            if str(row.get("children_count") or "").strip() != profile_children:
                row["children_count"] = profile_children
                changed = True
        if changed:
            updated += 1

    with staff_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=DEFAULT_PROFILES_DIR,
        help="Folder containing ICBC profile .docx files",
    )
    parser.add_argument(
        "--staff-csv",
        type=Path,
        default=SEED_DIR / "staff.csv",
    )
    parser.add_argument(
        "--site-profiles-csv",
        type=Path,
        default=SITE_PROFILES_CSV,
    )
    parser.add_argument(
        "--site-profiles-js",
        type=Path,
        default=SITE_PROFILES_JS,
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.profiles_dir.is_dir():
        raise SystemExit(f"Profiles folder not found: {args.profiles_dir}")

    profiles = extract_profiles(args.profiles_dir)
    print(f"Parsed {len(profiles)} profile(s) with family or care-team data.")
    if args.dry_run:
        return

    write_site_profiles_csv(profiles, args.site_profiles_csv)
    print(f"Wrote {args.site_profiles_csv}")

    write_site_profiles_js(profiles, args.site_profiles_js)
    print(f"Wrote {args.site_profiles_js}")

    updated = apply_to_staff_csv(profiles, args.staff_csv)
    print(f"Updated {updated} pastor row(s) in {args.staff_csv}")


if __name__ == "__main__":
    main()
