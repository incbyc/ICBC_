#!/usr/bin/env python3
"""Build monthly rainfall/temperature seed rows from Open-Meteo historical data."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "supabase" / "seed"
SITES_CSV = SEED_DIR / "icbc_sites.csv"
OUTPUT_CSV = SEED_DIR / "rainfall_monthly.csv"
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fetch_monthly_climate(lat: float, lng: float, start_year: int, end_year: int) -> list[dict[str, float]]:
    url = (
        "https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lng}"
        f"&start_date={start_year}-01-01&end_date={end_year}-12-31"
        "&daily=precipitation_sum,temperature_2m_mean&timezone=Africa%2FMbabane"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.loads(response.read())

    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    rains = daily.get("precipitation_sum") or []
    temps = daily.get("temperature_2m_mean") or []

    rain_by_month: dict[int, list[float]] = defaultdict(list)
    temp_by_month: dict[int, list[float]] = defaultdict(list)
    for day, rain, temp in zip(times, rains, temps):
        month = int(day[5:7])
        rain_by_month[month].append(float(rain or 0))
        if temp is not None:
            temp_by_month[month].append(float(temp))

    rows: list[dict[str, float]] = []
    years = max(end_year - start_year + 1, 1)
    for month in range(1, 13):
        month_rain = rain_by_month.get(month) or [0.0]
        month_temps = temp_by_month.get(month) or []
        total_rain = sum(month_rain)
        avg_monthly_rain = round(total_rain / years, 1)
        avg_temp = round(sum(month_temps) / len(month_temps), 1) if month_temps else ""
        rows.append(
            {
                "month": month,
                "month_label": MONTH_NAMES[month - 1],
                "rainfall_mm": avg_monthly_rain,
                "temperature_c": avg_temp,
            }
        )
    return rows


def load_sites(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites-csv", type=Path, default=SITES_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    sites = load_sites(args.sites_csv)
    fieldnames = ["site_slug", "month", "month_label", "rainfall_mm", "temperature_c"]
    output_rows: list[dict[str, str]] = []

    for site in sites:
        slug = (site.get("slug") or "").strip()
        lat_raw = (site.get("latitude") or "").strip()
        lng_raw = (site.get("longitude") or "").strip()
        if not slug or not lat_raw or not lng_raw:
            continue
        try:
            lat = float(lat_raw.replace(",", "."))
            lng = float(lng_raw.replace(",", "."))
        except ValueError:
            print(f"WARN skip {slug}: invalid coordinates", file=sys.stderr)
            continue

        try:
            monthly = fetch_monthly_climate(lat, lng, args.start_year, args.end_year)
        except urllib.error.URLError as exc:
            print(f"WARN skip {slug}: {exc}", file=sys.stderr)
            continue

        for entry in monthly:
            output_rows.append(
                {
                    "site_slug": slug,
                    "month": str(entry["month"]),
                    "month_label": entry["month_label"],
                    "rainfall_mm": str(entry["rainfall_mm"]),
                    "temperature_c": str(entry["temperature_c"]),
                }
            )
        print(f"{slug}: fetched 12 monthly rows")
        time.sleep(1.0)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Wrote {len(output_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
