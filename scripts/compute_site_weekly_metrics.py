#!/usr/bin/env python3
"""Compute per-site weekly averages from weekly_stats.csv for map sidebar display."""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"

CHURCH_ALIASES = {
    "mshaweni": "msahweni",
    "hawane clc church": "hawane",
    "lonhlane": "lonhlalane",
    "lushikisheni": "lushikishini",
    "mlangatane": "mhlangatane",
    "msaweni": "msahweni",
    "nsubani": "nsubane",
}


def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "site"


def load_site_name_map(sites_csv: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with sites_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            slug = (row.get("slug") or "").strip()
            name = (row.get("name") or "").strip()
            if not slug:
                continue
            mapping[slug] = slug
            if name:
                mapping[slugify(name)] = slug
                mapping[name.strip().lower()] = slug
    for alias, slug in CHURCH_ALIASES.items():
        mapping[alias] = slug
        mapping[slugify(alias)] = slug
    return mapping


def church_to_slug(church: str, name_map: dict[str, str]) -> str:
    raw = (church or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in name_map:
        return name_map[lowered]
    slug = slugify(raw)
    if slug in name_map:
        return name_map[slug]
    for key, site_slug in name_map.items():
        if key and (key in lowered or lowered in key):
            return site_slug
    return slug


def compute_avg_home_visits(
    weekly_stats_csv: Path,
    sites_csv: Path,
    min_avg: float = 5.0,
) -> dict[str, float]:
    name_map = load_site_name_map(sites_csv)
    totals: dict[str, list[float]] = defaultdict(list)

    with weekly_stats_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            slug = church_to_slug(row.get("church", ""), name_map)
            if not slug:
                continue
            try:
                visits = float(row.get("home_visits") or 0)
            except ValueError:
                continue
            totals[slug].append(visits)

    averages: dict[str, float] = {}
    for slug, values in totals.items():
        if not values:
            continue
        avg = sum(values) / len(values)
        if avg >= min_avg:
            averages[slug] = round(avg, 1)
    return averages


def write_metrics_csv(averages: dict[str, float], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["site_slug", "avg_home_visits_per_week"])
        writer.writeheader()
        for slug in sorted(averages):
            writer.writerow(
                {
                    "site_slug": slug,
                    "avg_home_visits_per_week": averages[slug],
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weekly-stats",
        type=Path,
        default=SEED_DIR / "weekly_stats.csv",
    )
    parser.add_argument(
        "--sites-csv",
        type=Path,
        default=SEED_DIR / "icbc_sites.csv",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SEED_DIR / "site_weekly_metrics.csv",
    )
    parser.add_argument("--min-avg", type=float, default=5.0)
    args = parser.parse_args()

    averages = compute_avg_home_visits(args.weekly_stats, args.sites_csv, args.min_avg)
    write_metrics_csv(averages, args.out)
    print(f"Wrote {len(averages)} site(s) with avg home visits >= {args.min_avg} to {args.out}")


if __name__ == "__main__":
    main()
