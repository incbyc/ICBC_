"""Generate and maintain 7 km catchment polygons for ICBC sites."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATCHMENT_JS = ROOT / "data" / "7kmCatchmentArea_3.js"
CATCHMENT_RADIUS_M = 7000.0
CATCHMENT_SEGMENTS = 20
EARTH_RADIUS_M = 6378137.0


def normalise_site_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def parse_coord(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def geodesic_destination(
    lat_deg: float, lon_deg: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def build_catchment_ring(
    lat: float,
    lon: float,
    *,
    radius_m: float = CATCHMENT_RADIUS_M,
    segments: int = CATCHMENT_SEGMENTS,
) -> list[list[float]]:
    ring: list[list[float]] = []
    for index in range(segments):
        bearing = (360.0 / segments) * index
        point_lat, point_lon = geodesic_destination(lat, lon, bearing, radius_m)
        ring.append([point_lon, point_lat])
    ring.append(ring[0][:])
    return ring


def build_catchment_geometry(lat: float, lon: float) -> dict[str, Any]:
    return {
        "type": "MultiPolygon",
        "coordinates": [[build_catchment_ring(lat, lon)]],
    }


def build_catchment_feature(
    site_name: str,
    lat: float,
    lon: float,
    feature_id: int,
    *,
    region: str = "",
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "ID": str(feature_id),
            "Site Name": site_name,
            "Pastor Nam": "",
            "Contact No": "",
            "Year Est.": "",
            "Region": region,
            "Latitude": lat,
            "Longitude": lon,
            "Main Water": "",
            "Current\u00a0S": "",
            "PreSchool": "",
            "Area Descr": None,
        },
        "geometry": build_catchment_geometry(lat, lon),
    }


def load_catchment_geojson(path: Path = CATCHMENT_JS) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"=\s*(\{.*\})\s*$", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not parse catchment GeoJSON from {path}")
    return json.loads(match.group(1))


def save_catchment_geojson(data: dict[str, Any], path: Path = CATCHMENT_JS) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=4)
    path.write_text(f"var json_7kmCatchmentArea_3 = {payload}\n", encoding="utf-8")


def load_icbc_site_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    import csv

    path = csv_path or (ROOT / "supabase" / "seed" / "icbc_sites.csv")
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = str(row.get("name", "")).strip()
            lat = parse_coord(row.get("latitude"))
            lon = parse_coord(row.get("longitude"))
            if not name or lat is None or lon is None:
                continue
            rows.append(
                {
                    "name": name,
                    "slug": str(row.get("slug", "")).strip(),
                    "region": str(row.get("region", "")).strip(),
                    "latitude": str(lat),
                    "longitude": str(lon),
                }
            )
    rows.sort(key=lambda item: item["name"].lower())
    return rows


def _legacy_property_match(
    features: list[dict[str, Any]],
    site_name: str,
    slug: str,
) -> dict[str, Any] | None:
    targets = {
        normalise_site_name(site_name),
        normalise_site_name(slug.replace("-", " ")),
    }
    for feature in features:
        props = feature.get("properties") or {}
        candidate = normalise_site_name(str(props.get("Site Name", "")))
        if candidate in targets:
            return props
        if candidate.replace(" ", "") == normalise_site_name(site_name).replace(" ", ""):
            return props
    aliases = {
        "mangcongco": "mangcongo",
        "mangcongo": "mangcongco",
    }
    alias = aliases.get(normalise_site_name(site_name))
    if alias:
        for feature in features:
            props = feature.get("properties") or {}
            if normalise_site_name(str(props.get("Site Name", ""))) == alias:
                return props
    return None


def regenerate_all_catchments(
    *,
    csv_path: Path | None = None,
    path: Path = CATCHMENT_JS,
) -> tuple[int, int]:
    """Rebuild every catchment polygon from ICBC site coordinates."""
    site_rows = load_icbc_site_rows(csv_path)
    existing = load_catchment_geojson(path)
    old_features = list(existing.get("features") or [])
    old_ids = {
        normalise_site_name(str((feature.get("properties") or {}).get("Site Name", ""))): str(
            (feature.get("properties") or {}).get("ID", "")
        )
        for feature in old_features
    }
    next_id = _next_feature_id(old_features)

    rebuilt: list[dict[str, Any]] = []
    for row in site_rows:
        site_name = row["name"]
        lat = parse_coord(row["latitude"])
        lon = parse_coord(row["longitude"])
        if lat is None or lon is None:
            continue

        name_key = normalise_site_name(site_name)
        legacy_props = _legacy_property_match(old_features, site_name, row.get("slug", ""))
        feature_id = old_ids.get(name_key, "")
        if not str(feature_id).isdigit():
            feature_id = str(next_id)
            next_id += 1

        props = {
            "ID": str(feature_id),
            "Site Name": site_name,
            "Pastor Nam": (legacy_props or {}).get("Pastor Nam", ""),
            "Contact No": (legacy_props or {}).get("Contact No", ""),
            "Year Est.": (legacy_props or {}).get("Year Est.", ""),
            "Region": row.get("region") or (legacy_props or {}).get("Region", ""),
            "Latitude": lat,
            "Longitude": lon,
            "Main Water": (legacy_props or {}).get("Main Water", ""),
            "Current\u00a0S": (legacy_props or {}).get("Current\u00a0S", ""),
            "PreSchool": (legacy_props or {}).get("PreSchool", ""),
            "Area Descr": (legacy_props or {}).get("Area Descr"),
        }
        rebuilt.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": build_catchment_geometry(lat, lon),
            }
        )

    existing["features"] = rebuilt
    save_catchment_geojson(existing, path)
    return len(rebuilt), len(old_features)


def audit_catchment_alignment(
    *,
    csv_path: Path | None = None,
    path: Path = CATCHMENT_JS,
    tolerance_m: float = 50.0,
) -> list[str]:
    import math

    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat_a = math.radians(lat1)
        lat_b = math.radians(lat2)
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lon / 2) ** 2
        )
        return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))

    issues: list[str] = []
    site_rows = {
        normalise_site_name(row["name"]): row for row in load_icbc_site_rows(csv_path)
    }
    data = load_catchment_geojson(path)
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        name = str(props.get("Site Name", ""))
        key = normalise_site_name(name)
        site = site_rows.get(key)
        if not site:
            issues.append(f"{name}: no matching ICBC site row")
            continue
        lat = parse_coord(site["latitude"])
        lon = parse_coord(site["longitude"])
        if lat is None or lon is None:
            continue
        ring = feature["geometry"]["coordinates"][0][0][:-1]
        radii = [haversine(lat, lon, point[1], point[0]) for point in ring]
        min_radius = min(radii)
        max_radius = max(radii)
        if abs(min_radius - CATCHMENT_RADIUS_M) > tolerance_m or abs(max_radius - CATCHMENT_RADIUS_M) > tolerance_m:
            issues.append(
                f"{name}: radius {min_radius:.0f}-{max_radius:.0f} m (expected ~{CATCHMENT_RADIUS_M:.0f} m)"
            )
    return issues


def _next_feature_id(features: list[dict[str, Any]]) -> int:
    highest = 0
    for feature in features:
        raw_id = str((feature.get("properties") or {}).get("ID", "")).strip()
        if raw_id.isdigit():
            highest = max(highest, int(raw_id))
    return highest + 1


def _find_feature_index(
    features: list[dict[str, Any]],
    site_name: str,
    *,
    previous_name: str | None = None,
) -> int | None:
    targets = {
        normalise_site_name(site_name),
        normalise_site_name(previous_name or ""),
    }
    targets.discard("")
    for index, feature in enumerate(features):
        props = feature.get("properties") or {}
        candidate = normalise_site_name(str(props.get("Site Name", "")))
        if candidate in targets:
            return index
    return None


def sync_catchment_for_site(
    row: dict[str, str],
    *,
    previous_name: str | None = None,
    path: Path = CATCHMENT_JS,
) -> str:
    site_name = str(row.get("name", "")).strip()
    lat = parse_coord(row.get("latitude"))
    lon = parse_coord(row.get("longitude"))
    if not site_name:
        return "Skipped catchment sync: site name is required."
    if lat is None or lon is None:
        return f"Skipped catchment sync for `{site_name}`: latitude and longitude are required."

    data = load_catchment_geojson(path)
    features: list[dict[str, Any]] = list(data.get("features") or [])
    index = _find_feature_index(features, site_name, previous_name=previous_name)
    region = str(row.get("region", "")).strip()

    if index is None:
        feature = build_catchment_feature(
            site_name,
            lat,
            lon,
            _next_feature_id(features),
            region=region,
        )
        features.append(feature)
        action = "Added"
    else:
        feature = features[index]
        props = feature.setdefault("properties", {})
        props["Site Name"] = site_name
        props["Latitude"] = lat
        props["Longitude"] = lon
        props["Region"] = region or props.get("Region", "")
        feature["geometry"] = build_catchment_geometry(lat, lon)
        action = "Updated"

    data["features"] = features
    save_catchment_geojson(data, path)
    return f"{action} 7 km catchment for `{site_name}` in `{path.name}`."


def sync_catchments_for_site_rows(
    rows: list[dict[str, str]],
    *,
    path: Path = CATCHMENT_JS,
) -> list[str]:
    messages: list[str] = []
    for row in rows:
        messages.append(sync_catchment_for_site(row, path=path))
    return messages


if __name__ == "__main__":
    rebuilt, previous = regenerate_all_catchments()
    print(f"Rebuilt {rebuilt} catchment(s) (was {previous}).")
    issues = audit_catchment_alignment()
    if issues:
        print("Alignment issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All catchments are 7 km and aligned to site coordinates.")
