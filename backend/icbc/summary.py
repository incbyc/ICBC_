import re
from typing import Dict

from django.db.models import Sum

from .models import ICBCSite, WeeklyStat


def _parse_number(text: str) -> float:
    """
    Best-effort numeric parser for strings like '50', '75 Hectares', '31 (310 people impacted)'.
    Returns 0.0 when no number can be found.
    """
    if not text:
        return 0.0
    s = str(text)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def build_global_summary() -> Dict:
    """
    Aggregate summary across all ICBC sites for the CMS overview page.
    """
    total_sites = ICBCSite.objects.count()

    # Ploughing aggregates from per-site fields (strings parsed to numbers).
    sites = ICBCSite.objects.all()
    total_plough_hours = 0.0
    total_plough_hectares = 0.0
    total_plough_families = 0.0
    total_maize_tonnes = 0.0
    total_maize_farmers = 0

    for site in sites:
        total_plough_hours += _parse_number(site.hours_ploughed)
        total_plough_hectares += _parse_number(site.area_ploughed)
        total_plough_families += _parse_number(site.families_ploughed_for)
        total_maize_tonnes += float(site.maize_tonnes_purchased or 0)
        total_maize_farmers += int(site.maize_farmers_supported or 0)

    # Weekly stats aggregates
    weekly_qs = WeeklyStat.objects.all()
    stats_agg = weekly_qs.aggregate(
        total_preschool_attendance=Sum("preschool_attendance"),
        total_salvations=Sum("salvations"),
        total_baptisms=Sum("baptisms"),
        total_home_visits=Sum("home_visits"),
        total_meals=Sum("meals_food_packs"),
        total_attendance=Sum("total_attendance"),
    )

    return {
        "total_icbcs": total_sites,
        "total_attendance": int(stats_agg["total_attendance"] or 0),
        "total_preschool_children_impacted": int(
            stats_agg["total_preschool_attendance"] or 0
        ),
        "total_salvations": int(stats_agg["total_salvations"] or 0),
        "total_baptisms": int(stats_agg["total_baptisms"] or 0),
        "total_home_visits": int(stats_agg["total_home_visits"] or 0),
        "total_meals": int(stats_agg["total_meals"] or 0),
        "total_plough_hours": round(total_plough_hours, 1),
        "total_plough_hectares": round(total_plough_hectares, 1),
        "total_plough_families": int(total_plough_families),
        "total_maize_tonnes": round(total_maize_tonnes, 2),
        "total_maize_farmers": int(total_maize_farmers),
    }

