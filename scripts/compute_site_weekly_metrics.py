#!/usr/bin/env python3
"""Compute per-site weekly averages from weekly_stats.csv for map sidebar display."""

from __future__ import annotations

import argparse
import csv
import json
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

METRIC_FIELDS = (
    "avg_home_visits_per_week",
    "avg_men",
    "avg_women",
    "avg_youth",
    "avg_children",
    "weeks_recorded",
)


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


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_site_weekly_metrics(
    weekly_stats_csv: Path,
    sites_csv: Path,
    min_avg_home_visits: float = 5.0,
) -> dict[str, dict[str, float | int]]:
    name_map = load_site_name_map(sites_csv)
    home_visits: dict[str, list[float]] = defaultdict(list)
    men: dict[str, list[float]] = defaultdict(list)
    women: dict[str, list[float]] = defaultdict(list)
    youth: dict[str, list[float]] = defaultdict(list)
    children: dict[str, list[float]] = defaultdict(list)

    with weekly_stats_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            slug = church_to_slug(row.get("church", ""), name_map)
            if not slug:
                continue
            attendance = _float(row.get("total_attendance"))
            if attendance <= 0:
                continue
            home_visits[slug].append(_float(row.get("home_visits")))
            men[slug].append(_float(row.get("men")))
            women[slug].append(_float(row.get("women")))
            youth[slug].append(_float(row.get("youth")))
            children[slug].append(_float(row.get("children")))

    metrics: dict[str, dict[str, float | int]] = {}
    all_slugs = set(home_visits) | set(men) | set(women) | set(youth) | set(children)
    for slug in all_slugs:
        weeks = len(men.get(slug) or women.get(slug) or youth.get(slug) or children.get(slug) or [])
        if not weeks:
            continue
        entry: dict[str, float | int] = {
            "weeks_recorded": weeks,
            "avg_men": round(sum(men[slug]) / weeks, 1),
            "avg_women": round(sum(women[slug]) / weeks, 1),
            "avg_youth": round(sum(youth[slug]) / weeks, 1),
            "avg_children": round(sum(children[slug]) / weeks, 1),
            "avg_home_visits_per_week": 0.0,
        }
        visits = home_visits.get(slug) or []
        if visits:
            entry["avg_home_visits_per_week"] = round(sum(visits) / len(visits), 1)
        metrics[slug] = entry

    return {
        slug: values
        for slug, values in metrics.items()
        if values["weeks_recorded"] > 0
        and (
            values["avg_home_visits_per_week"] >= min_avg_home_visits
            or values["avg_men"] > 0
            or values["avg_women"] > 0
            or values["avg_youth"] > 0
            or values["avg_children"] > 0
        )
    }


def write_metrics_csv(metrics: dict[str, dict[str, float | int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["site_slug", *METRIC_FIELDS]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for slug in sorted(metrics):
            row = {"site_slug": slug}
            row.update(metrics[slug])
            writer.writerow(row)


def write_metrics_js(metrics: dict[str, dict[str, float | int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {slug: metrics[slug] for slug in sorted(metrics)}
    lines = [
        "// Auto-generated from supabase/seed/site_weekly_metrics.csv",
        "// — run scripts/compute_site_weekly_metrics.py to refresh.",
        "window.ICBC_WEEKLY_METRICS_SEED = " + json.dumps(payload, indent=4) + ";",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


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
    parser.add_argument(
        "--out-js",
        type=Path,
        default=ROOT / "js" / "icbc-weekly-metrics-data.js",
    )
    parser.add_argument("--min-avg-home-visits", type=float, default=5.0)
    args = parser.parse_args()

    metrics = compute_site_weekly_metrics(
        args.weekly_stats,
        args.sites_csv,
        args.min_avg_home_visits,
    )
    write_metrics_csv(metrics, args.out)
    write_metrics_js(metrics, args.out_js)
    print(f"Wrote {len(metrics)} site weekly metric row(s) to {args.out}")
    print(f"Wrote embedded weekly metrics seed to {args.out_js}")


if __name__ == "__main__":
    main()
