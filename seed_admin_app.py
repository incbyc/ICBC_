#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from catchment_geometry import sync_catchment_for_site, sync_catchments_for_site_rows  # noqa: E402
from supabase_sync import DEFAULT_SUPABASE_URL, build_sync_client  # noqa: E402
SEED_DIR = ROOT / "supabase" / "seed"
DEFAULT_MEDIA_DIR = "images/seed_uploads"
STATS_PARSER_PATH = ROOT / "backend" / "icbc" / "stats_parser.py"

REGION_OPTIONS = ("", "Hhohho", "Lubombo", "Manzini", "Shiselweni")
ROLE_OPTIONS = ("Pastor", "Teacher", "Compassionate Care", "Other")
URL_STYLE_OPTIONS = {
    "Relative path only": "relative",
    "Raw GitHub URL": "raw",
    "jsDelivr CDN URL": "jsdelivr",
}


@dataclass(frozen=True)
class FieldSpec:
    label: str
    widget: str = "text"
    help: str = ""
    options: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class TableConfig:
    key: str
    title: str
    file_name: str
    fallback_columns: tuple[str, ...]
    unique_keys: tuple[str, ...]
    sort_keys: tuple[str, ...]
    intro: str
    template_name: str | None = None

    @property
    def path(self) -> Path:
        return SEED_DIR / self.file_name

    @property
    def template_path(self) -> Path | None:
        if not self.template_name:
            return None
        return SEED_DIR / self.template_name


FIELD_SPECS: dict[str, FieldSpec] = {
    "slug": FieldSpec("Slug", help="Leave blank to generate from the site name."),
    "name": FieldSpec("Site name", required=True),
    "region": FieldSpec("Region", widget="select", options=REGION_OPTIONS),
    "year_constructed": FieldSpec("Year constructed (YYYY or YYYY-MM-DD)"),
    "water_source": FieldSpec("Water source"),
    "projects": FieldSpec("Projects", widget="textarea"),
    "about": FieldSpec("About", widget="textarea"),
    "site_link": FieldSpec("Site link / main channel URL"),
    "video_url": FieldSpec("Video URL", help="Use a YouTube URL for the sidebar clip."),
    "photo_path": FieldSpec("Photo path", help="Repo-relative image path."),
    "cover_image_url": FieldSpec("Cover image URL", help="GitHub-friendly public URL."),
    "latitude": FieldSpec("Latitude"),
    "longitude": FieldSpec("Longitude"),
    "site_slug": FieldSpec("ICBC site", widget="site_slug", required=True),
    "full_name": FieldSpec("Full name", required=True),
    "description": FieldSpec("Description / bio", widget="textarea"),
    "role": FieldSpec("Role", widget="select", options=ROLE_OPTIONS, required=True),
    "year_joined": FieldSpec("Year joined"),
    "photo_url": FieldSpec(
        "Photo path",
        help="Repo-relative path from upload. Synced to Supabase so the map sidebar can load it.",
    ),
    "sort_order": FieldSpec("Sort order"),
    "children_count": FieldSpec("Children count", required=True),
    "snapshot_date": FieldSpec("Snapshot date", widget="date", help="Use YYYY-MM-DD.", required=True),
    "year": FieldSpec("Year", required=True),
    "teachers_count": FieldSpec("Teachers count"),
    "children_impacted_since_inception": FieldSpec("Children impacted since inception"),
    "notes": FieldSpec("Notes", widget="textarea"),
    "hours_ploughed": FieldSpec("Hours ploughed", required=True),
    "families_impacted": FieldSpec("Families impacted", required=True),
    "hectares_ploughed": FieldSpec("Hectares ploughed", required=True),
    "farmers_impacted": FieldSpec("Farmers impacted", required=True),
    "kilograms_bought": FieldSpec("Kilograms bought", required=True),
    "meals_made": FieldSpec("Meals made"),
    "site_name": FieldSpec("Site name", required=True),
    "family_code": FieldSpec("Family code", required=True),
    "church": FieldSpec("Church", widget="church", required=True),
    "date": FieldSpec("Date", widget="date", help="Use YYYY-MM-DD.", required=True),
    "total_attendance": FieldSpec("Total attendance", required=True),
    "men": FieldSpec("Men"),
    "women": FieldSpec("Women"),
    "youth": FieldSpec("Youth"),
    "children": FieldSpec("Children"),
    "salvations": FieldSpec("Salvations"),
    "baptisms": FieldSpec("Baptisms"),
}


TABLE_CONFIGS = {
    "icbc_sites": TableConfig(
        key="icbc_sites",
        title="ICBC Sites",
        file_name="icbc_sites.csv",
        fallback_columns=(
            "slug",
            "name",
            "region",
            "year_constructed",
            "water_source",
            "projects",
            "about",
            "site_link",
            "video_url",
            "photo_path",
            "cover_image_url",
            "latitude",
            "longitude",
        ),
        unique_keys=("slug",),
        sort_keys=("name",),
        intro="Core site profile data. Uploaded site media is copied into the repo and its path/URL is written back to the seed row.",
    ),
    "staff": TableConfig(
        key="staff",
        title="Staff",
        file_name="staff.csv",
        fallback_columns=(
            "site_slug",
            "full_name",
            "description",
            "role",
            "year_joined",
            "photo_url",
            "sort_order",
        ),
        unique_keys=("site_slug", "full_name", "role"),
        sort_keys=("site_slug", "role", "sort_order", "full_name"),
        intro="Pastors, teachers, compassionate care team members, and other staff.",
        template_name="staff_template.csv",
    ),
    "preschool_enrollment": TableConfig(
        key="preschool_enrollment",
        title="Preschool Enrollment",
        file_name="preschool_enrollment.csv",
        fallback_columns=(
            "site_slug",
            "year",
            "children_count",
            "teachers_count",
            "notes",
        ),
        unique_keys=("site_slug", "year"),
        sort_keys=("site_slug", "year"),
        intro=(
            "Annual preschool enrollment per site (2022–current). "
            "Re-import from Enrollment_Counts.xlsx with "
            "`python scripts/import_preschool_enrollment.py`. "
            "Latest year = current enrollment on the map."
        ),
        template_name="preschool_enrollment_template.csv",
    ),
    "ploughing_records": TableConfig(
        key="ploughing_records",
        title="Ploughing",
        file_name="ploughing_records.csv",
        fallback_columns=(
            "site_slug",
            "year",
            "hours_ploughed",
            "families_impacted",
            "hectares_ploughed",
            "notes",
        ),
        unique_keys=("site_slug", "year"),
        sort_keys=("year", "site_slug"),
        intro="Historical ploughing rows keyed by site and year. Saving the same site/year updates the row instead of duplicating it.",
        template_name="ploughing_records_template.csv",
    ),
    "maize_buyback_records": TableConfig(
        key="maize_buyback_records",
        title="Maize Buy-Back",
        file_name="maize_buyback_records.csv",
        fallback_columns=(
            "site_slug",
            "year",
            "farmers_impacted",
            "kilograms_bought",
            "meals_made",
            "notes",
        ),
        unique_keys=("site_slug", "year"),
        sort_keys=("year", "site_slug"),
        intro="Historical maize buy-back rows keyed by site and year.",
        template_name="maize_buyback_records_template.csv",
    ),
    "weekly_stats": TableConfig(
        key="weekly_stats",
        title="Weekly Stats",
        file_name="weekly_stats.csv",
        fallback_columns=(
            "church",
            "date",
            "total_attendance",
            "men",
            "women",
            "youth",
            "children",
            "salvations",
            "baptisms",
        ),
        unique_keys=("church", "date"),
        sort_keys=("date", "church"),
        intro="Weekly stats keyed by church name and date. The same church/date pair updates the existing row instead of creating a duplicate.",
        template_name="weekly_stats_template.csv",
    ),
    "bubele_care_sites": TableConfig(
        key="bubele_care_sites",
        title="Bubele Care",
        file_name="bubele_care_sites.csv",
        fallback_columns=("site_name", "family_code", "region", "latitude", "longitude"),
        unique_keys=("site_name", "family_code"),
        sort_keys=("site_name", "family_code"),
        intro="Bubele Care rows are kept in their own seed file.",
    ),
}


def slugify(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalise_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def seed_columns(config: TableConfig) -> list[str]:
    if not config.path.exists():
        return list(config.fallback_columns)
    with config.path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return list(config.fallback_columns)


def ensure_seed_file(config: TableConfig, columns: list[str]) -> None:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    if config.path.exists():
        return
    with config.path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()


def read_seed_rows(config: TableConfig, columns: list[str]) -> list[dict[str, str]]:
    ensure_seed_file(config, columns)
    with config.path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({column: format_value(row.get(column, "")) for column in columns})
        return rows


def write_seed_rows(config: TableConfig, columns: list[str], rows: list[dict[str, str]]) -> None:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    with config.path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_value(row.get(column, "")) for column in columns})


def sort_rows(rows: list[dict[str, str]], sort_keys: tuple[str, ...]) -> list[dict[str, str]]:
    def sort_key(row: dict[str, str]) -> tuple[str, ...]:
        return tuple(normalise_space(row.get(key, "")).lower() for key in sort_keys)

    return sorted(rows, key=sort_key)


def upsert_rows(
    config: TableConfig,
    columns: list[str],
    new_rows: list[dict[str, str]],
) -> tuple[int, int]:
    existing_rows = read_seed_rows(config, columns)
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    inserted = 0
    updated = 0

    for row in existing_rows:
        merged[row_key(row, config.unique_keys)] = row

    for row in new_rows:
        clean_row = sanitise_row(row, columns)
        key = row_key(clean_row, config.unique_keys)
        if key in merged:
            updated += 1
        else:
            inserted += 1
        merged[key] = clean_row

    final_rows = sort_rows(list(merged.values()), config.sort_keys)
    write_seed_rows(config, columns, final_rows)
    return inserted, updated


def sanitise_row(row: dict[str, str], columns: list[str]) -> dict[str, str]:
    clean_row = {column: format_value(row.get(column, "")) for column in columns}
    if "slug" in clean_row and not clean_row["slug"] and clean_row.get("name"):
        clean_row["slug"] = slugify(clean_row["name"])
    if "sort_order" in clean_row and not clean_row["sort_order"]:
        clean_row["sort_order"] = "0"
    return clean_row


def row_key(row: dict[str, str], unique_keys: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalise_space(row.get(key, "")).lower() for key in unique_keys)


def record_label(config: TableConfig, row: dict[str, str]) -> str:
    if config.key == "icbc_sites":
        name = row.get("name") or row.get("slug") or "Unnamed site"
        slug = row.get("slug", "")
        return f"{name} ({slug})" if slug else name
    if config.key == "staff":
        return f'{row.get("full_name", "Unnamed")} — {row.get("role", "Staff")} · {row.get("site_slug", "?")}'
    if config.key == "preschool_enrollment":
        return f'{row.get("site_slug", "?")} · year {row.get("year", "?")}'
    if config.key in {"ploughing_records", "maize_buyback_records"}:
        return f'{row.get("site_slug", "?")} · year {row.get("year", "?")}'
    if config.key == "weekly_stats":
        return f'{row.get("church", "?")} · {row.get("date", "no date")}'
    if config.key == "bubele_care_sites":
        return f'{row.get("site_name", "?")} · {row.get("family_code", "?")}'
    parts = [format_value(row.get(key, "")) for key in config.unique_keys if format_value(row.get(key, ""))]
    return " · ".join(parts) if parts else "Record"


def delete_row_by_key(config: TableConfig, columns: list[str], key: tuple[str, ...]) -> bool:
    rows = read_seed_rows(config, columns)
    remaining = [row for row in rows if row_key(row, config.unique_keys) != key]
    if len(remaining) == len(rows):
        return False
    write_seed_rows(config, columns, sort_rows(remaining, config.sort_keys))
    return True


def replace_row(
    config: TableConfig,
    columns: list[str],
    original_key: tuple[str, ...],
    new_row: dict[str, str],
) -> tuple[int, int]:
    rows = read_seed_rows(config, columns)
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    found = False

    for row in rows:
        key = row_key(row, config.unique_keys)
        if key == original_key:
            found = True
            continue
        merged[key] = row

    clean_row = sanitise_row(new_row, columns)
    new_key = row_key(clean_row, config.unique_keys)
    inserted = 0
    updated = 0

    if new_key in merged:
        updated += 1
    elif found:
        updated += 1
    else:
        inserted += 1
    merged[new_key] = clean_row

    write_seed_rows(config, columns, sort_rows(list(merged.values()), config.sort_keys))
    return inserted, updated


def selectbox_default_index(options: list[str], value: str) -> int:
    normalised = format_value(value)
    for index, option in enumerate(options):
        if option == normalised:
            return index
    return 0


def preview_image_if_local(path_value: str, caption: str) -> None:
    if not path_value:
        return
    candidate = ROOT / path_value
    if candidate.is_file():
        st.image(str(candidate), caption=caption, width=160)
        return
    if path_value.startswith(("http://", "https://")):
        st.image(path_value, caption=caption, width=160)


def csv_template_bytes(columns: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    return buffer.getvalue().encode("utf-8")


def template_bytes(config: TableConfig, columns: list[str]) -> bytes:
    if config.template_path and config.template_path.exists():
        return config.template_path.read_bytes()
    return csv_template_bytes(columns)


def parse_uploaded_csv(uploaded_file, columns: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    text = uploaded_file.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["The uploaded CSV has no header row."]

    missing = [column for column in columns if column not in reader.fieldnames]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}"]

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        rows.append({column: format_value(raw_row.get(column, "")) for column in columns})

    return rows, []


@st.cache_resource
def load_stats_parser():
    spec = importlib.util.spec_from_file_location("stats_parser", STATS_PARSER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load weekly stats parser from {STATS_PARSER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def weekly_record_to_row(record: dict) -> dict[str, str]:
    return {
        "church": format_value(record.get("Church", "")),
        "date": format_value(record.get("Date", "")),
        "total_attendance": format_value(int(record.get("Total Attendance") or 0)),
        "men": format_value(int(record.get("Men") or 0)),
        "women": format_value(int(record.get("Women") or 0)),
        "youth": format_value(int(record.get("Youth") or 0)),
        "children": format_value(int(record.get("Children") or 0)),
        "salvations": format_value(int(record.get("Salvations") or 0)),
        "baptisms": format_value(int(record.get("Baptisms") or 0)),
    }


def parse_weekly_workbook(uploaded_file) -> tuple[list[dict[str, str]], int]:
    parser = load_stats_parser()
    records, duplicate_count = parser.parse_workbook(uploaded_file.getvalue(), uploaded_file.name)
    return [weekly_record_to_row(record) for record in records], duplicate_count


def save_staff_photo_bytes(
    image_bytes: bytes,
    relative_root: str,
    entity_slug: str,
    *,
    filename_stem: str = "portrait",
) -> str:
    relative_dir = Path(relative_root.strip("/\\")) / "staff" / (entity_slug or "misc")
    safe_stem = slugify(filename_stem) or "portrait"
    candidate = ROOT / relative_dir / f"{safe_stem}.jpg"
    candidate.parent.mkdir(parents=True, exist_ok=True)

    suffix = 2
    while candidate.exists():
        candidate = ROOT / relative_dir / f"{safe_stem}-{suffix}.jpg"
        suffix += 1

    candidate.write_bytes(image_bytes)
    return candidate.relative_to(ROOT).as_posix()


def rotate_portrait_image(image, degrees: int):
    """Rotate a portrait image counter-clockwise; white fill in expanded corners."""
    from PIL import Image

    normalized = int(degrees) % 360
    if normalized == 0:
        return image.convert("RGB")

    return image.convert("RGB").rotate(
        normalized,
        expand=True,
        resample=Image.BICUBIC,
        fillcolor=(255, 255, 255),
    )


def show_round_photo_preview(pil_image, *, width: int = 148, caption: str = "Round preview (as on map)") -> None:
    buffer = io.BytesIO()
    pil_image.convert("RGB").save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    st.caption(caption)
    st.markdown(
        (
            f'<img src="data:image/jpeg;base64,{encoded}" alt="" '
            f'style="width:{width}px;height:{width}px;object-fit:cover;border-radius:50%;'
            f'border:3px solid #ffcdd2;box-shadow:0 2px 12px rgba(198,40,40,0.15);" />'
        ),
        unsafe_allow_html=True,
    )


def render_staff_photo_cropper(
    session_key: str,
    *,
    existing_path: str = "",
    upload=None,
) -> bytes | None:
    """Manual square crop with a round preview. Stores JPEG bytes in session_state."""
    from PIL import Image
    from streamlit_cropper import st_cropper

    source_bytes: bytes | None = None
    if upload is not None:
        source_bytes = bytes(upload.getvalue())
    elif existing_path:
        file_path = ROOT / existing_path
        if file_path.is_file():
            source_bytes = file_path.read_bytes()

    if not source_bytes:
        st.session_state.pop(session_key, None)
        return None

    st.markdown("#### Portrait crop")
    st.caption(
        "Rotate the photo if needed, then drag and resize the square crop box so the face is centred. "
        "The map sidebar shows this image in a round frame."
    )

    image = Image.open(io.BytesIO(source_bytes))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    source_id = hashlib.md5(source_bytes).hexdigest()
    source_key = f"{session_key}-source-id"
    rotation_key = f"{session_key}-rotation"
    if st.session_state.get(source_key) != source_id:
        st.session_state[source_key] = source_id
        st.session_state[rotation_key] = 0

    angle = int(st.session_state.get(rotation_key, 0))
    rot_left, rot_right, rot_flip, rot_reset = st.columns(4)
    with rot_left:
        if st.button("↺ Left 90°", key=f"{session_key}-rot-left", use_container_width=True):
            st.session_state[rotation_key] = (angle + 90) % 360
            st.rerun()
    with rot_right:
        if st.button("↻ Right 90°", key=f"{session_key}-rot-right", use_container_width=True):
            st.session_state[rotation_key] = (angle - 90) % 360
            st.rerun()
    with rot_flip:
        if st.button("Flip 180°", key=f"{session_key}-rot-flip", use_container_width=True):
            st.session_state[rotation_key] = (angle + 180) % 360
            st.rerun()
    with rot_reset:
        if st.button("Reset", key=f"{session_key}-rot-reset", use_container_width=True):
            st.session_state[rotation_key] = 0
            st.rerun()

    angle = st.slider(
        "Rotation (degrees)",
        min_value=0,
        max_value=359,
        value=angle,
        step=1,
        help="Turn the image counter-clockwise before cropping.",
    )
    st.session_state[rotation_key] = angle
    image = rotate_portrait_image(image, angle)

    cropped = st_cropper(
        image,
        realtime_update=True,
        aspect_ratio=(1, 1),
        return_type="image",
        key=f"{session_key}-widget-{angle}",
    )

    preview_cols = st.columns([1, 2])
    with preview_cols[0]:
        show_round_photo_preview(cropped)
    with preview_cols[1]:
        st.image(cropped, caption="Square crop (saved file)", width=200)

    buffer = io.BytesIO()
    cropped.convert("RGB").save(buffer, format="JPEG", quality=92)
    cropped_bytes = buffer.getvalue()
    st.session_state[session_key] = cropped_bytes
    return cropped_bytes


def save_media_file(uploaded_file, relative_root: str, subfolder: str, entity_slug: str) -> str:
    relative_dir = Path(relative_root.strip("/\\")) / subfolder / (entity_slug or "misc")
    safe_stem = slugify(Path(uploaded_file.name).stem) or "upload"
    extension = Path(uploaded_file.name).suffix.lower() or ".bin"
    candidate = ROOT / relative_dir / f"{safe_stem}{extension}"
    candidate.parent.mkdir(parents=True, exist_ok=True)

    suffix = 2
    while candidate.exists():
        candidate = ROOT / relative_dir / f"{safe_stem}-{suffix}{extension}"
        suffix += 1

    candidate.write_bytes(uploaded_file.getbuffer())
    return candidate.relative_to(ROOT).as_posix()


def public_media_url(relative_path: str, repo_slug: str, branch: str, url_style: str) -> str:
    if not relative_path:
        return ""
    relative_path = relative_path.strip("/")
    if url_style == "relative" or not repo_slug.strip():
        return relative_path
    if url_style == "jsdelivr":
        return f"https://cdn.jsdelivr.net/gh/{repo_slug.strip()}@{branch.strip()}/{relative_path}"
    return f"https://raw.githubusercontent.com/{repo_slug.strip()}/{branch.strip()}/{relative_path}"


def site_display_map(site_rows: list[dict[str, str]]) -> dict[str, str]:
    display = {}
    for row in site_rows:
        slug = format_value(row.get("slug", ""))
        if not slug:
            continue
        name = format_value(row.get("name", "")) or slug
        display[slug] = f"{name} ({slug})"
    return display


def normalise_icbc_site_row(row: dict[str, str]) -> dict[str, str]:
    if not format_value(row.get("slug", "")):
        row["slug"] = slugify(row.get("name", ""))
    for key in ("latitude", "longitude"):
        value = format_value(row.get(key, ""))
        if value:
            row[key] = value.replace(",", ".")
    return row


def load_icbc_sites_for_picker(
    site_config: TableConfig,
    site_columns: list[str],
) -> list[dict[str, str]]:
    """ICBC sites from local CSV, merged with any extra rows in Supabase."""
    rows = read_seed_rows(site_config, site_columns)
    for row in rows:
        normalise_icbc_site_row(row)

    known_slugs = {format_value(row.get("slug", "")) for row in rows if format_value(row.get("slug", ""))}
    client = get_supabase_sync_client()
    if client:
        try:
            response = (
                client.client.table("icbc_sites")
                .select("slug,name,region")
                .order("name")
                .execute()
            )
            for site in response.data or []:
                slug = format_value(site.get("slug", ""))
                if not slug or slug in known_slugs:
                    continue
                blank = {column: "" for column in site_columns}
                blank.update(
                    {
                        "slug": slug,
                        "name": format_value(site.get("name", "")),
                        "region": format_value(site.get("region", "")),
                    }
                )
                rows.append(blank)
                known_slugs.add(slug)
        except Exception as exc:
            st.caption(f"Could not load extra sites from Supabase: {exc}")

    return sort_rows(rows, site_config.sort_keys)


def site_name_options(site_rows: list[dict[str, str]]) -> list[str]:
    return sorted({row["name"] for row in site_rows if row.get("name")})


def field_value_from_widget(
    column: str,
    spec: FieldSpec,
    site_rows: list[dict[str, str]],
    key_prefix: str,
    default_value: str = "",
):
    widget_key = f"{key_prefix}-{column}"
    default_value = format_value(default_value)

    if spec.widget == "site_slug":
        display_map = site_display_map(site_rows)
        options = sorted(display_map.keys())
        if default_value and default_value not in options:
            options = [default_value] + options
        if not options:
            st.caption("Add ICBC sites first so staff can be linked to a site.")
            return ""
        return st.selectbox(
            spec.label,
            options=options,
            index=selectbox_default_index(options, default_value),
            format_func=lambda value: display_map.get(value, value),
            help=spec.help,
            key=widget_key,
        )

    if spec.widget == "church":
        options = site_name_options(site_rows)
        if not options:
            return st.text_input(spec.label, value=default_value, help=spec.help, key=widget_key)
        return st.selectbox(
            spec.label,
            options=options,
            index=selectbox_default_index(options, default_value),
            help=spec.help,
            key=widget_key,
        )

    if spec.widget == "select":
        options = list(spec.options)
        if default_value and default_value not in options:
            options = [default_value] + options
        return st.selectbox(
            spec.label,
            options=options,
            index=selectbox_default_index(options, default_value),
            help=spec.help,
            key=widget_key,
        )

    if spec.widget == "textarea":
        return st.text_area(
            spec.label,
            value=default_value,
            help=spec.help,
            key=widget_key,
            height=120,
        )

    if spec.widget == "date":
        return st.text_input(
            spec.label,
            value=default_value,
            help=spec.help,
            placeholder="YYYY-MM-DD",
            key=widget_key,
        )

    return st.text_input(spec.label, value=default_value, help=spec.help, key=widget_key)


def render_form_fields(
    config: TableConfig,
    columns: list[str],
    site_rows: list[dict[str, str]],
    key_prefix: str,
    defaults: dict[str, str] | None = None,
) -> dict[str, str]:
    defaults = defaults or {}
    row: dict[str, str] = {}
    form_columns = st.columns(2)
    for index, column in enumerate(columns):
        if config.key == "staff" and column == "photo_url":
            row[column] = format_value(defaults.get(column, ""))
            continue
        spec = FIELD_SPECS.get(column, FieldSpec(column.replace("_", " ").title()))
        with form_columns[index % 2]:
            row[column] = format_value(
                field_value_from_widget(
                    column=column,
                    spec=spec,
                    site_rows=site_rows,
                    key_prefix=key_prefix,
                    default_value=defaults.get(column, ""),
                )
            )
    return row


def apply_media_uploads(
    config: TableConfig,
    columns: list[str],
    row: dict[str, str],
    *,
    site_photo_upload,
    cover_upload,
    staff_photo_upload,
    media_root: str,
    repo_slug: str,
    branch: str,
    url_style: str,
    staff_cropped_bytes: bytes | None = None,
) -> dict[str, str]:
    if config.key == "icbc_sites":
        entity_slug = row.get("slug") or slugify(row.get("name", ""))
        row["slug"] = entity_slug
        if site_photo_upload is not None and "photo_path" in columns:
            row["photo_path"] = save_media_file(site_photo_upload, media_root, "sites", entity_slug)
        if cover_upload is not None and "cover_image_url" in columns:
            row["cover_image_url"] = save_media_file(cover_upload, media_root, "covers", entity_slug)
    elif config.key == "staff" and row.get("site_slug") and (staff_cropped_bytes or staff_photo_upload):
        staff_folder = f'{row.get("site_slug", "")}-{slugify(row.get("full_name", ""))}'
        stem = slugify(row.get("full_name", "")) or "portrait"
        if staff_cropped_bytes:
            relative_path = save_staff_photo_bytes(
                staff_cropped_bytes,
                media_root,
                staff_folder,
                filename_stem=stem,
            )
        elif staff_photo_upload is not None:
            relative_path = save_media_file(
                staff_photo_upload,
                media_root,
                "staff",
                staff_folder,
            )
        else:
            relative_path = ""
        if "photo_url" in columns and relative_path:
            row["photo_url"] = relative_path
    return row


def validate_rows(config: TableConfig, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        for key in config.unique_keys:
            if not format_value(row.get(key, "")):
                errors.append(f"Row {idx} is missing `{key}`.")

        if config.key == "icbc_sites":
            if not format_value(row.get("name", "")):
                errors.append(f"Row {idx} is missing `name`.")
            for coord_key in ("latitude", "longitude"):
                coord_value = format_value(row.get(coord_key, "")).replace(",", ".")
                if coord_value:
                    try:
                        float(coord_value)
                    except ValueError:
                        errors.append(
                            f"Row {idx} has an invalid `{coord_key}` value: {row.get(coord_key, '')}"
                        )
        elif config.key == "staff":
            if not format_value(row.get("full_name", "")):
                errors.append(f"Row {idx} is missing `full_name`.")
        elif config.key == "weekly_stats":
            date_value = format_value(row.get("date", ""))
            if date_value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                errors.append(f"Row {idx} has an invalid `date` value: {date_value}")
        elif config.key == "preschool_enrollment":
            year_value = format_value(row.get("year", ""))
            if year_value and not re.fullmatch(r"\d{4}", year_value):
                errors.append(f"Row {idx} has an invalid `year` value: {year_value}")

    return errors


def preview_dataframe(rows: list[dict[str, str]], max_rows: int = 50) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[:max_rows])


def load_local_secrets_file() -> dict[str, str]:
    """Read `.streamlit/secrets.toml` without using st.secrets (avoids Streamlit errors when missing)."""
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in secrets_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        value = raw_value.strip().strip('"').strip("'")
        if value and not value.startswith("your-"):
            values[key.strip()] = value
    return values


def supabase_secrets() -> tuple[str, str]:
    secrets = load_local_secrets_file()
    url = secrets.get("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    service_key = secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return url, service_key


def get_supabase_sync_client():
    return st.session_state.get("supabase_sync_client")


def maybe_sync_supabase(config: TableConfig, row: dict[str, str], *, deleted: bool = False) -> None:
    client = get_supabase_sync_client()
    if not client:
        return
    try:
        message = client.delete_row(config.key, row) if deleted else client.sync_row(config.key, row)
        st.caption(f"Supabase: {message}")
    except Exception as exc:
        st.warning(f"Local CSV saved, but Supabase sync failed: {exc}")


def maybe_sync_icbc_catchment(
    row: dict[str, str],
    *,
    previous_name: str | None = None,
) -> None:
    try:
        message = sync_catchment_for_site(row, previous_name=previous_name)
        st.caption(message)
    except Exception as exc:
        st.warning(f"Site saved, but 7 km catchment update failed: {exc}")


def maybe_sync_all_supabase(config: TableConfig, columns: list[str]) -> None:
    client = get_supabase_sync_client()
    if not client:
        return
    rows = read_seed_rows(config, columns)
    try:
        message = client.sync_all(config.key, rows)
        st.success(message)
    except Exception as exc:
        st.error(f"Supabase bulk sync failed: {exc}")


def render_media_uploads(config: TableConfig, key_prefix: str):
    site_photo_upload = None
    cover_upload = None
    staff_photo_upload = None

    if config.key == "icbc_sites":
        st.markdown("#### Replace media (optional)")
        site_photo_upload = st.file_uploader(
            "Upload new site photo",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{key_prefix}-site-photo",
        )
        cover_upload = st.file_uploader(
            "Upload new cover image",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{key_prefix}-cover-photo",
        )
    return site_photo_upload, cover_upload, staff_photo_upload


def render_edit_existing_panel(
    config: TableConfig,
    columns: list[str],
    site_rows: list[dict[str, str]],
    repo_slug: str,
    branch: str,
    url_style: str,
    media_root: str,
) -> None:
    rows = read_seed_rows(config, columns)
    st.subheader(f"Edit existing {config.title}")
    st.caption("Pick a record, change the fields below, then save. Your edits update the seed CSV in place.")

    if not rows:
        st.info(f"No {config.title.lower()} records yet. Use **Add new** below.")
        return

    filtered_rows = rows
    if config.key == "staff":
        site_options = sorted({row.get("site_slug", "") for row in rows if row.get("site_slug")})
        display_map = site_display_map(site_rows)
        filter_labels = ["All ICBC sites"] + [
            display_map.get(slug, slug) for slug in site_options
        ]
        filter_choice = st.selectbox(
            "Filter by ICBC",
            options=filter_labels,
            key=f"{config.key}-staff-site-filter",
        )
        if filter_choice != "All ICBC sites":
            slug_for_filter = next(
                (slug for slug, label in display_map.items() if label == filter_choice),
                "",
            )
            if not slug_for_filter and " (" in filter_choice:
                slug_for_filter = filter_choice.rsplit("(", 1)[-1].rstrip(")")
            filtered_rows = [
                row for row in rows if row.get("site_slug", "") == slug_for_filter
            ]

    if not filtered_rows:
        st.warning("No records match this filter.")
        return

    record_options = [record_label(config, row) for row in filtered_rows]
    selected_label = st.selectbox(
        "Choose record",
        options=record_options,
        key=f"{config.key}-edit-record-picker",
    )
    selected_row = next(
        row for row, label in zip(filtered_rows, record_options) if label == selected_label
    )
    original_key = row_key(selected_row, config.unique_keys)

    if config.key == "icbc_sites":
        preview_cols = st.columns(2)
        with preview_cols[0]:
            preview_image_if_local(selected_row.get("photo_path", ""), "Current site photo")
        with preview_cols[1]:
            preview_image_if_local(
                selected_row.get("cover_image_url", ""),
                "Current cover image",
            )
    elif config.key == "staff":
        preview_image_if_local(selected_row.get("photo_url", ""), "Current staff photo")
        crop_session_key = f"{config.key}-edit-crop-{original_key}"
        staff_upload_new = st.file_uploader(
            "Upload a new staff photo (optional)",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{config.key}-edit-staff-upload-{original_key}",
        )
        render_staff_photo_cropper(
            crop_session_key,
            existing_path="" if staff_upload_new else selected_row.get("photo_url", ""),
            upload=staff_upload_new,
        )

    with st.form(f"{config.key}-edit-form"):
        row = render_form_fields(
            config,
            columns,
            site_rows,
            key_prefix=f"{config.key}-edit",
            defaults=selected_row,
        )
        site_photo_upload, cover_upload, staff_photo_upload = render_media_uploads(
            config,
            key_prefix=f"{config.key}-edit",
        )

        action_cols = st.columns([2, 1])
        with action_cols[0]:
            save_clicked = st.form_submit_button("Save changes", type="primary")
        with action_cols[1]:
            delete_clicked = st.form_submit_button("Delete record")

    if delete_clicked:
        if delete_row_by_key(config, columns, original_key):
            maybe_sync_supabase(config, selected_row, deleted=True)
            st.success(f"Deleted `{selected_label}` from `{config.path}`.")
            st.rerun()
        st.error("Could not delete the selected record.")
        return

    if not save_clicked:
        return

    row = sanitise_row(row, columns)
    if config.key == "icbc_sites":
        row = normalise_icbc_site_row(row)
    staff_crop_bytes = None
    if config.key == "staff":
        staff_crop_bytes = st.session_state.get(f"{config.key}-edit-crop-{original_key}")
    row = apply_media_uploads(
        config,
        columns,
        row,
        site_photo_upload=site_photo_upload,
        cover_upload=cover_upload,
        staff_photo_upload=staff_photo_upload,
        media_root=media_root,
        repo_slug=repo_slug,
        branch=branch,
        url_style=url_style,
        staff_cropped_bytes=staff_crop_bytes,
    )

    errors = validate_rows(config, [row])
    if errors:
        for error in errors:
            st.error(error)
        return

    replace_row(config, columns, original_key, row)
    maybe_sync_supabase(config, row)
    st.success(f"Updated `{record_label(config, row)}` in `{config.path}`.")
    if config.key == "icbc_sites":
        maybe_sync_icbc_catchment(row, previous_name=format_value(selected_row.get("name", "")))
        lat_ok = format_value(row.get("latitude", ""))
        lng_ok = format_value(row.get("longitude", ""))
        if lat_ok and lng_ok:
            st.info(
                "Site updated. Refresh the map page to see the marker and 7 km catchment "
                "(loaded from seed CSV and Supabase)."
            )
        else:
            st.warning("Add latitude and longitude so the site appears on the map.")
    if config.key == "staff" and row.get("photo_url"):
        st.info(
            "Staff photo path saved. With **Sync to Supabase on save** enabled, "
            "refresh the map to see the image (serve the repo locally so paths load)."
        )
    if config.key == "staff":
        st.session_state.pop(f"{config.key}-edit-crop-{original_key}", None)
    st.rerun()


def render_add_new_panel(
    config: TableConfig,
    columns: list[str],
    site_rows: list[dict[str, str]],
    repo_slug: str,
    branch: str,
    url_style: str,
    media_root: str,
) -> None:
    staff_add_upload = None
    staff_add_crop_key = f"{config.key}-add-crop"
    if config.key == "staff":
        staff_add_upload = st.file_uploader(
            "Staff photo (optional — crop before saving)",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{config.key}-add-staff-upload",
        )
        if staff_add_upload:
            render_staff_photo_cropper(staff_add_crop_key, upload=staff_add_upload)

    with st.form(f"{config.key}-add-form", clear_on_submit=True):
        st.subheader(f"Add new {config.title}")
        row = render_form_fields(
            config,
            columns,
            site_rows,
            key_prefix=f"{config.key}-add",
            defaults={},
        )
        site_photo_upload, cover_upload, staff_photo_upload = render_media_uploads(
            config,
            key_prefix=f"{config.key}-add",
        )
        submitted = st.form_submit_button(f"Add {config.title} row", type="primary")

    if not submitted:
        return

    row = sanitise_row(row, columns)
    if config.key == "icbc_sites":
        row = normalise_icbc_site_row(row)
    staff_crop_bytes = st.session_state.get(staff_add_crop_key) if config.key == "staff" else None
    row = apply_media_uploads(
        config,
        columns,
        row,
        site_photo_upload=site_photo_upload,
        cover_upload=cover_upload,
        staff_photo_upload=staff_add_upload if config.key == "staff" else staff_photo_upload,
        media_root=media_root,
        repo_slug=repo_slug,
        branch=branch,
        url_style=url_style,
        staff_cropped_bytes=staff_crop_bytes,
    )

    errors = validate_rows(config, [row])
    if errors:
        for error in errors:
            st.error(error)
        return

    inserted, updated = upsert_rows(config, columns, [row])
    maybe_sync_supabase(config, row)
    st.success(f"Saved row to `{config.path}`. Inserted: {inserted}, updated: {updated}.")
    if config.key == "icbc_sites":
        maybe_sync_icbc_catchment(row)
        lat_ok = format_value(row.get("latitude", ""))
        lng_ok = format_value(row.get("longitude", ""))
        if lat_ok and lng_ok:
            st.info(
                "Site saved. Refresh the map page to see the marker and 7 km catchment — "
                "new and updated sites are loaded from Supabase (requires **Sync to Supabase on save**)."
            )
        else:
            st.warning("Add latitude and longitude so the site appears on the map.")
    if config.key == "staff":
        st.session_state.pop(staff_add_crop_key, None)
    st.rerun()


def render_record_workspace(
    config: TableConfig,
    columns: list[str],
    site_rows: list[dict[str, str]],
    repo_slug: str,
    branch: str,
    url_style: str,
    media_root: str,
) -> None:
    render_edit_existing_panel(
        config,
        columns,
        site_rows,
        repo_slug,
        branch,
        url_style,
        media_root,
    )
    st.divider()
    render_add_new_panel(
        config,
        columns,
        site_rows,
        repo_slug,
        branch,
        url_style,
        media_root,
    )


def render_bulk_csv_upload(config: TableConfig, columns: list[str]) -> None:
    st.subheader("Bulk CSV Upload")
    st.caption("Upload a CSV with the same columns as the seed file. Matching key rows will be updated, not duplicated.")

    st.download_button(
        "Download template CSV",
        data=template_bytes(config, columns),
        file_name=config.template_name or config.file_name,
        mime="text/csv",
        key=f"{config.key}-download-template",
    )

    uploaded_csv = st.file_uploader(
        f"Upload {config.title} CSV",
        type=["csv"],
        key=f"{config.key}-csv-uploader",
    )
    if uploaded_csv is None:
        return

    rows, errors = parse_uploaded_csv(uploaded_csv, columns)
    errors.extend(validate_rows(config, rows[:200]))
    if errors:
        for error in errors:
            st.error(error)
        return

    st.caption(f"Previewing {min(len(rows), 50)} of {len(rows)} row(s).")
    st.dataframe(preview_dataframe(rows), use_container_width=True, hide_index=True)

    if st.button(f"Merge CSV into {config.file_name}", key=f"{config.key}-merge-csv"):
        inserted, updated = upsert_rows(config, columns, rows)
        maybe_sync_all_supabase(config, columns)
        if config.key == "icbc_sites":
            for message in sync_catchments_for_site_rows(rows):
                st.caption(message)
        st.success(f"Merged CSV into `{config.path}`. Inserted: {inserted}, updated: {updated}.")
        st.rerun()


def render_weekly_excel_upload(config: TableConfig, columns: list[str]) -> None:
    st.subheader("Weekly Stats Workbook Upload")
    st.markdown(
        "\n".join(
            [
                "- Upload the weekly stats workbook here.",
                "- The app parses all sheets using the same parser already used by the project scripts.",
                "- Duplicates inside the workbook are removed by `church + date` before saving.",
                "- Saving again with the same `church + date` updates the seed row instead of duplicating it.",
            ]
        )
    )

    uploaded_workbook = st.file_uploader(
        "Upload weekly stats Excel workbook",
        type=["xlsx", "xlsm"],
        key="weekly-stats-workbook-uploader",
    )
    if uploaded_workbook is None:
        return

    rows, duplicate_count = parse_weekly_workbook(uploaded_workbook)
    errors = validate_rows(config, rows[:500])
    if errors:
        for error in errors:
            st.error(error)
        return

    st.info(
        f"Parsed {len(rows)} unique weekly stat row(s). "
        f"Duplicates removed inside workbook: {duplicate_count}."
    )
    st.dataframe(preview_dataframe(rows), use_container_width=True, hide_index=True)

    if st.button("Merge workbook into weekly_stats.csv", key="weekly-stats-merge-workbook"):
        inserted, updated = upsert_rows(config, columns, rows)
        maybe_sync_all_supabase(config, columns)
        st.success(
            f"Merged workbook rows into `{config.path}`. Inserted: {inserted}, updated: {updated}."
        )
        st.rerun()


def render_current_rows(config: TableConfig, columns: list[str]) -> None:
    rows = read_seed_rows(config, columns)
    with st.expander(f"Browse all rows ({len(rows)})", expanded=False):
        st.caption(f"Read-only overview of `{config.path}`. Use **Edit existing** above to change records.")
        if not rows:
            st.info("This seed file is currently empty.")
            return
        st.dataframe(preview_dataframe(rows, max_rows=500), use_container_width=True, hide_index=True)


def render_table_tab(
    config: TableConfig,
    site_rows: list[dict[str, str]],
    site_config: TableConfig,
    site_columns: list[str],
    repo_slug: str,
    branch: str,
    url_style: str,
    media_root: str,
) -> None:
    if config.key == "staff":
        site_rows = load_icbc_sites_for_picker(site_config, site_columns)
        if not site_rows:
            st.warning(
                "No ICBC sites found yet. Add a site under **ICBC Sites** first, "
                "then return here to link staff."
            )
    columns = seed_columns(config)
    st.markdown(config.intro)
    st.caption(f"Seed file: `{config.path}`")

    render_record_workspace(config, columns, site_rows, repo_slug, branch, url_style, media_root)
    if get_supabase_sync_client():
        st.divider()
        st.subheader("Push to Supabase")
        st.caption("Upload the full seed file for this tab to Supabase (upserts matching keys).")
        if st.button(f"Push all {config.title} to Supabase", key=f"{config.key}-push-all"):
            maybe_sync_all_supabase(config, columns)
    st.divider()
    render_bulk_csv_upload(config, columns)
    if config.key == "weekly_stats":
        st.divider()
        render_weekly_excel_upload(config, columns)
    st.divider()
    render_current_rows(config, columns)


def sidebar_settings():
    st.sidebar.header("Seed Admin Settings")
    secrets_url, secrets_service_key = supabase_secrets()

    st.sidebar.markdown("### Supabase")
    st.sidebar.caption(
        "Streamlit writes need the **service_role** key (Supabase → Project Settings → API). "
        "Paste it in the sidebar below, or in `.streamlit/secrets.toml` (see `secrets.toml.example`)."
    )
    if not (ROOT / ".streamlit" / "secrets.toml").is_file():
        st.sidebar.info(
            "Tip: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` "
            "to store your service role key locally."
        )
    supabase_url = st.sidebar.text_input("Supabase URL", value=secrets_url)
    service_role_key = st.sidebar.text_input(
        "Service role key",
        value=secrets_service_key,
        type="password",
        help="Optional in UI if set in `.streamlit/secrets.toml`.",
    )
    sync_enabled = st.sidebar.checkbox(
        "Sync to Supabase on save",
        value=bool(service_role_key),
        help=(
            "When enabled, rows are upserted to Supabase on save/delete. "
            "Staff photo paths are included; ICBC site marker/cover images stay local only."
        ),
    )
    sync_client = None
    sync_error = None
    if sync_enabled:
        if not format_value(service_role_key):
            sync_error = "Enter the service role key to enable Supabase sync."
        else:
            try:
                sync_client = build_sync_client(supabase_url, service_role_key)
            except ImportError as exc:
                sync_error = str(exc)
            except RuntimeError as exc:
                sync_error = str(exc)
    st.session_state["supabase_sync_client"] = sync_client
    if sync_error:
        st.sidebar.warning(sync_error)

    repo_slug = st.sidebar.text_input(
        "GitHub repo slug",
        value="",
        help="Optional. Example: `your-org/your-repo`.",
    )
    branch = st.sidebar.text_input("GitHub branch", value="main")
    url_style_label = st.sidebar.selectbox("Media URL style", options=list(URL_STYLE_OPTIONS.keys()))
    media_root = st.sidebar.text_input(
        "Repo media folder",
        value=DEFAULT_MEDIA_DIR,
        help="Uploaded files are copied into this folder inside the repo.",
    )

    cleaned_media_root = media_root.strip("/\\")
    example_path = f"{cleaned_media_root}/sites/example/photo.jpg"
    st.sidebar.markdown("### Media strategy")
    st.sidebar.write(
        "Staff photos are saved locally and the path is synced to Supabase for the map. "
        "ICBC site marker and cover images stay local only (not pushed to Supabase)."
    )
    st.sidebar.code(example_path)

    return repo_slug, branch, URL_STYLE_OPTIONS[url_style_label], media_root


def main() -> None:
    st.set_page_config(page_title="ICBC Seed Admin", layout="wide")
    st.title("ICBC Seed Admin")
    st.caption(
        "Edit local `supabase/seed/*.csv` files. Images are stored locally; enable "
        "**Sync text to Supabase on save** to push text fields live (requires service role key)."
    )

    repo_slug, branch, url_style, media_root = sidebar_settings()
    site_config = TABLE_CONFIGS["icbc_sites"]
    site_columns = seed_columns(site_config)
    site_rows = load_icbc_sites_for_picker(site_config, site_columns)

    tab_order = [
        "icbc_sites",
        "staff",
        "preschool_enrollment",
        "ploughing_records",
        "maize_buyback_records",
        "weekly_stats",
        "bubele_care_sites",
    ]
    tabs = st.tabs([TABLE_CONFIGS[key].title for key in tab_order])

    for tab, key in zip(tabs, tab_order):
        with tab:
            render_table_tab(
                config=TABLE_CONFIGS[key],
                site_rows=site_rows,
                site_config=site_config,
                site_columns=site_columns,
                repo_slug=repo_slug,
                branch=branch,
                url_style=url_style,
                media_root=media_root,
            )


if __name__ == "__main__":
    main()
