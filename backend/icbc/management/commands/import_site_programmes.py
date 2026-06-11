"""
Import preschool, ploughing, and coordinates from data/ICBCSites_6.js.

Usage:
    python manage.py import_site_programmes
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from icbc.models import ICBCSite, MaizeBuybackRecord, PloughingRecord, PreschoolSnapshot
from icbc.programme_utils import parse_number, parse_preschool_summary

ROOT = Path(__file__).resolve().parents[4]
ICBC_JS = ROOT / "data" / "ICBCSites_6.js"

MIN_PLOUGH_HOURS = 20


class Command(BaseCommand):
    help = "Import programme data from the static ICBC GeoJSON file."

    def handle(self, *args, **options):
        if not ICBC_JS.exists():
            self.stderr.write(f"Missing {ICBC_JS}")
            return

        text = ICBC_JS.read_text(encoding="utf-8")
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1])

        preschool_n = plough_n = coord_n = 0

        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or []

            name = (props.get("Site Name") or "").strip()
            if not name:
                continue

            site, _ = ICBCSite.objects.get_or_create(
                slug=slugify(name),
                defaults={"name": name},
            )
            if site.name != name:
                site.name = name

            if len(coords) >= 2:
                site.longitude = coords[0]
                site.latitude = coords[1]
                coord_n += 1

            parsed = parse_preschool_summary(props.get("PreSchool") or "")
            children = parsed.get("children_count")
            if children:
                year_raw = (props.get("Ploughing Season") or "").strip()
                year = int(year_raw) if year_raw.isdigit() else date.today().year
                PreschoolSnapshot.objects.update_or_create(
                    site=site,
                    snapshot_date=date(year, 6, 1),
                    defaults={
                        "children_count": children,
                        "year": year,
                        "teachers_count": parsed.get("teachers_count"),
                        "notes": props.get("PreSchool") or "",
                    },
                )
                preschool_n += 1

            hours = parse_number(props.get("Hours Ploughed"))
            if hours is not None and hours >= MIN_PLOUGH_HOURS:
                year_raw = (props.get("Ploughing Season") or "").strip()
                year = int(year_raw) if year_raw.isdigit() else date.today().year
                families = parse_number(props.get("Families Ploughed for")) or 0
                hectares = parse_number(props.get("Area Ploughed")) or 0
                PloughingRecord.objects.update_or_create(
                    site=site,
                    year=year,
                    defaults={
                        "hours_ploughed": hours,
                        "families_impacted": int(families),
                        "hectares_ploughed": hectares,
                    },
                )
                plough_n += 1

            if site.maize_tonnes_purchased or site.maize_farmers_supported:
                year_raw = (props.get("Ploughing Season") or "").strip()
                year = int(year_raw) if year_raw.isdigit() else date.today().year
                kg = float(site.maize_tonnes_purchased or 0) * 1000
                MaizeBuybackRecord.objects.update_or_create(
                    site=site,
                    year=year,
                    defaults={
                        "farmers_impacted": site.maize_farmers_supported,
                        "kilograms_bought": kg,
                        "meals_made": 0,
                    },
                )

            site.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated coordinates: {coord_n}, preschool snapshots: {preschool_n}, "
                f"ploughing records (>={MIN_PLOUGH_HOURS}h): {plough_n}"
            )
        )
