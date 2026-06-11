"""Parse legacy text fields from map GeoJSON / site records."""
from __future__ import annotations

import re
from typing import Optional


def parse_number(text) -> Optional[float]:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw.upper() in {"N/A", "NA", "-", "NONE", "NOT PLOUGHED YET"}:
        return None
    match = re.search(r"[\d.]+", raw.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def parse_preschool_summary(summary: str) -> dict:
    if not summary:
        return {"children_count": None, "teachers_count": None}
    children = re.search(r"Children:\s*(\d+)", summary, re.I)
    teachers = re.search(r"Teachers:\s*(\d+)", summary, re.I)
    return {
        "children_count": int(children.group(1)) if children else None,
        "teachers_count": int(teachers.group(1)) if teachers else None,
    }
