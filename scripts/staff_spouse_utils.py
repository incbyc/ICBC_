"""Helpers for pastor spouse names in staff seed data."""

from __future__ import annotations

import re


def pastor_surname(full_name: str) -> str:
    parts = (full_name or "").strip().split()
    return parts[-1] if parts else ""


def is_invalid_spouse(value: str) -> bool:
    spouse = (value or "").strip()
    if not spouse:
        return False
    if re.fullmatch(r"(none|single|n/a)\.?", spouse, flags=re.I):
        return True
    if len(spouse) > 55:
        return True
    return bool(
        re.search(
            r"qualification|pre\s*school|church\s+attendance|children|pastors?|certificate|diploma|degree",
            spouse,
            flags=re.I,
        )
    )


def align_spouse_surname(pastor_name: str, spouse_name: str) -> str:
    """Use pastor's surname as the spouse's last name."""
    spouse = (spouse_name or "").strip()
    if is_invalid_spouse(spouse):
        return ""
    if not spouse:
        return ""

    surname = pastor_surname(pastor_name)
    if not surname:
        return spouse

    parts = spouse.split()
    if len(parts) == 1:
        return f"{parts[0]} {surname}"
    return " ".join(parts[:-1] + [surname])
