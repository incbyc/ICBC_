"""Push seed-admin rows to Supabase (requires service_role key — not the anon key)."""
from __future__ import annotations

import hashlib
import re
from typing import Any

DEFAULT_SUPABASE_URL = "https://oalwyosxclspdkwmivfb.supabase.co"
STAFF_PHOTOS_BUCKET = "staff-photos"
STAFF_PHOTO_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]
STAFF_PHOTO_SIZE_LIMIT = 5 * 1024 * 1024


def normalise_church_name(raw: str) -> str:
    text = str(raw or "").strip().lower()
    text = text.split("(", 1)[0]
    text = re.sub(r"\s+clc\s+church\s*$", "", text)
    text = re.sub(r"\s+clc\s*$", "", text)
    return text.strip()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slugify(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "staff"


def _int_or_none(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    return int(float(text))


def _float_or_none(value: Any) -> float | None:
    text = _text(value).replace(",", ".")
    if not text:
        return None
    return float(text)


def _project_root() -> "Path":
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


def _import_create_client():
    import importlib
    import sys
    from pathlib import Path

    project_root = _project_root().resolve()
    local_supabase_dir = (project_root / "supabase").resolve()

    for name in list(sys.modules):
        if name != "supabase" and not name.startswith("supabase."):
            continue
        module = sys.modules[name]
        module_paths: list[Path] = []
        module_file = getattr(module, "__file__", None)
        if module_file:
            module_paths.append(Path(module_file).resolve().parent)
        module_path = getattr(module, "__path__", None)
        if module_path is not None:
            module_paths.extend(Path(entry).resolve() for entry in module_path)
        if any(
            path == local_supabase_dir or local_supabase_dir in path.parents
            for path in module_paths
        ):
            del sys.modules[name]

    original_path = sys.path[:]
    filtered_path: list[str] = []
    for entry in original_path:
        if entry in ("", "."):
            continue
        try:
            resolved = Path(entry).resolve()
        except OSError:
            filtered_path.append(entry)
            continue
        if resolved == project_root:
            continue
        filtered_path.append(entry)

    try:
        sys.path[:] = filtered_path
        module = importlib.import_module("supabase")
    finally:
        sys.path[:] = original_path

    create_client = getattr(module, "create_client", None)
    if create_client is None:
        raise ImportError(
            "Could not import `create_client` from the Supabase Python package. "
            "Install it with `pip install \"supabase>=2.0,<3.0\"`. "
            "Your repo folder `supabase/` can shadow that package name, so this app "
            "loads the pip package explicitly."
        )
    return create_client


class SupabaseSeedSync:
    def __init__(self, url: str, service_role_key: str) -> None:
        create_client = _import_create_client()

        self.url = url.rstrip("/")
        self.client = create_client(self.url, service_role_key)
        self._sites: list[dict[str, Any]] | None = None

    def staff_photo_public_url(self, object_path: str) -> str:
        clean_path = object_path.strip("/")
        return f"{self.url}/storage/v1/object/public/{STAFF_PHOTOS_BUCKET}/{clean_path}"

    def ensure_staff_photos_bucket(self) -> None:
        """Create the public staff-photos bucket if the project has none yet."""
        try:
            buckets = self.client.storage.list_buckets() or []
        except Exception as exc:
            raise RuntimeError(f"Could not list Supabase Storage buckets: {exc}") from exc

        if any(getattr(bucket, "name", "") == STAFF_PHOTOS_BUCKET for bucket in buckets):
            return

        try:
            self.client.storage.create_bucket(
                STAFF_PHOTOS_BUCKET,
                options={
                    "public": True,
                    "file_size_limit": STAFF_PHOTO_SIZE_LIMIT,
                    "allowed_mime_types": STAFF_PHOTO_MIME_TYPES,
                },
            )
        except Exception as exc:
            message = str(exc).lower()
            if "already exists" in message or "duplicate" in message:
                return
            raise RuntimeError(
                "Could not create the `staff-photos` storage bucket. "
                "Run `supabase/storage_setup.sql` in the Supabase SQL Editor, "
                f"or check project permissions. Details: {exc}"
            ) from exc

    def upload_staff_photo(
        self,
        image_bytes: bytes,
        site_slug: str,
        full_name: str,
    ) -> str:
        if not image_bytes:
            raise ValueError("Staff photo upload requires image bytes.")
        self.ensure_staff_photos_bucket()
        site_part = _slugify(site_slug) or "site"
        name_part = _slugify(full_name) or "portrait"
        content_id = hashlib.md5(image_bytes).hexdigest()[:10]
        object_path = f"{site_part}/{name_part}-{content_id}.jpg"
        bucket = self.client.storage.from_(STAFF_PHOTOS_BUCKET)
        try:
            bucket.upload(
                object_path,
                image_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Supabase Storage upload failed for `{object_path}`: {exc}"
            ) from exc
        return self.staff_photo_public_url(object_path)

    def _load_sites(self) -> list[dict[str, Any]]:
        if self._sites is None:
            response = self.client.table("icbc_sites").select("id, slug, name").execute()
            self._sites = response.data or []
        return self._sites

    def _site_id_for_slug(self, site_slug: str) -> str | None:
        slug = _text(site_slug).lower()
        for site in self._load_sites():
            if _text(site.get("slug")).lower() == slug:
                return site["id"]
        return None

    def _site_id_for_church(self, church: str) -> str | None:
        target = normalise_church_name(church)
        for site in self._load_sites():
            if normalise_church_name(site.get("name", "")) == target:
                return site["id"]
        return None

    def sync_row(self, table_key: str, row: dict[str, str]) -> str:
        if table_key == "icbc_sites":
            return self._sync_icbc_site(row)
        if table_key == "staff":
            return self._sync_staff(row)
        if table_key == "preschool_snapshots":
            return self._sync_preschool(row)
        if table_key == "preschool_enrollment":
            return self._sync_preschool_enrollment(row)
        if table_key == "ploughing_records":
            return self._sync_ploughing(row)
        if table_key == "maize_buyback_records":
            return self._sync_maize(row)
        if table_key == "rainfall_monthly":
            return self._sync_rainfall_monthly(row)
        if table_key == "weekly_stats":
            return self._sync_weekly_stat(row)
        if table_key == "bubele_care_sites":
            return self._sync_bubele(row)
        raise ValueError(f"Unsupported table key: {table_key}")

    def delete_row(self, table_key: str, row: dict[str, str]) -> str:
        if table_key == "icbc_sites":
            slug = _text(row.get("slug"))
            self.client.table("icbc_sites").delete().eq("slug", slug).execute()
            self._sites = None
            return f"Deleted ICBC site `{slug}` from Supabase."
        if table_key == "staff":
            site_id = self._site_id_for_slug(row.get("site_slug", ""))
            if not site_id:
                raise ValueError(f"Unknown site slug: {row.get('site_slug')}")
            (
                self.client.table("staff")
                .delete()
                .eq("site_id", site_id)
                .eq("full_name", _text(row.get("full_name")))
                .eq("role", _text(row.get("role")))
                .execute()
            )
            return "Deleted staff row from Supabase."
        if table_key == "preschool_snapshots":
            site_id = self._require_site_id(row.get("site_slug", ""))
            (
                self.client.table("preschool_snapshots")
                .delete()
                .eq("site_id", site_id)
                .eq("snapshot_date", _text(row.get("snapshot_date")))
                .execute()
            )
            return "Deleted preschool snapshot from Supabase."
        if table_key == "preschool_enrollment":
            site_id = self._require_site_id(row.get("site_slug", ""))
            (
                self.client.table("preschool_enrollment")
                .delete()
                .eq("site_id", site_id)
                .eq("year", _int_or_none(row.get("year")))
                .execute()
            )
            return "Deleted preschool enrollment row from Supabase."
        if table_key == "ploughing_records":
            site_id = self._require_site_id(row.get("site_slug", ""))
            (
                self.client.table("ploughing_records")
                .delete()
                .eq("site_id", site_id)
                .eq("year", _int_or_none(row.get("year")))
                .execute()
            )
            return "Deleted ploughing record from Supabase."
        if table_key == "maize_buyback_records":
            site_id = self._require_site_id(row.get("site_slug", ""))
            (
                self.client.table("maize_buyback_records")
                .delete()
                .eq("site_id", site_id)
                .eq("year", _int_or_none(row.get("year")))
                .execute()
            )
            return "Deleted maize buy-back record from Supabase."
        if table_key == "rainfall_monthly":
            site_id = self._require_site_id(row.get("site_slug", ""))
            (
                self.client.table("site_rainfall_monthly")
                .delete()
                .eq("site_id", site_id)
                .eq("month", _int_or_none(row.get("month")))
                .execute()
            )
            return "Deleted rainfall row from Supabase."
        if table_key == "weekly_stats":
            site_id = self._site_id_for_church(row.get("church", ""))
            if not site_id:
                raise ValueError(f"Unknown church name: {row.get('church')}")
            (
                self.client.table("weekly_stats")
                .delete()
                .eq("site_id", site_id)
                .eq("stat_date", _text(row.get("date")))
                .execute()
            )
            return "Deleted weekly stat from Supabase."
        if table_key == "bubele_care_sites":
            (
                self.client.table("bubele_care_sites")
                .delete()
                .eq("family_code", _text(row.get("family_code")))
                .execute()
            )
            return "Deleted Bubele Care row from Supabase."
        raise ValueError(f"Unsupported table key: {table_key}")

    def sync_all(self, table_key: str, rows: list[dict[str, str]]) -> str:
        synced = 0
        errors: list[str] = []
        for row in rows:
            try:
                self.sync_row(table_key, row)
                synced += 1
            except Exception as exc:  # noqa: BLE001 — collect row-level failures for bulk push
                label = row.get("slug") or row.get("full_name") or row.get("church") or "row"
                errors.append(f"{label}: {exc}")
        if errors:
            preview = "; ".join(errors[:5])
            suffix = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
            raise RuntimeError(f"Synced {synced}/{len(rows)}. Errors: {preview}{suffix}")
        return f"Synced {synced} row(s) to Supabase."

    def _require_site_id(self, site_slug: str) -> str:
        site_id = self._site_id_for_slug(site_slug)
        if not site_id:
            raise ValueError(f"Unknown site slug: {site_slug}")
        return site_id

    def _sync_icbc_site(self, row: dict[str, str]) -> str:
        payload = {
            "slug": _text(row.get("slug")),
            "name": _text(row.get("name")),
            "region": _text(row.get("region")),
            "year_constructed": _text(row.get("year_constructed")),
            "water_source": _text(row.get("water_source")),
            "projects": _text(row.get("projects")),
            "about": _text(row.get("about")),
            "site_link": _text(row.get("site_link")),
            "video_url": _text(row.get("video_url")),
            "latitude": _float_or_none(row.get("latitude")),
            "longitude": _float_or_none(row.get("longitude")),
        }
        self.client.table("icbc_sites").upsert(payload, on_conflict="slug").execute()
        self._sites = None
        return f"Synced ICBC site `{payload['slug']}` to Supabase."

    def _sync_staff(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "full_name": _text(row.get("full_name")),
            "description": _text(row.get("description")),
            "role": _text(row.get("role")),
            "year_joined": _int_or_none(row.get("year_joined")),
            "photo_url": _text(row.get("photo_url")),
            "spouse_name": _text(row.get("spouse_name")),
            "children_count": _int_or_none(row.get("children_count")),
            "sort_order": _int_or_none(row.get("sort_order")) or 0,
        }
        self.client.table("staff").upsert(
            payload,
            on_conflict="site_id,full_name,role",
        ).execute()
        return f"Synced staff `{payload['full_name']}` to Supabase."

    def _sync_preschool(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "children_count": _int_or_none(row.get("children_count")) or 0,
            "snapshot_date": _text(row.get("snapshot_date")),
            "year": _int_or_none(row.get("year")) or 0,
            "teachers_count": _int_or_none(row.get("teachers_count")),
            "children_impacted_since_inception": _int_or_none(
                row.get("children_impacted_since_inception")
            ),
            "notes": _text(row.get("notes")),
        }
        self.client.table("preschool_snapshots").upsert(
            payload,
            on_conflict="site_id,snapshot_date",
        ).execute()
        return f"Synced preschool snapshot `{payload['snapshot_date']}` to Supabase."

    def _sync_preschool_enrollment(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "year": _int_or_none(row.get("year")) or 0,
            "children_count": _int_or_none(row.get("children_count")) or 0,
            "teachers_count": _int_or_none(row.get("teachers_count")),
            "notes": _text(row.get("notes")),
        }
        self.client.table("preschool_enrollment").upsert(
            payload,
            on_conflict="site_id,year",
        ).execute()
        return f"Synced preschool enrollment year `{payload['year']}` to Supabase."

    def _sync_ploughing(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "year": _int_or_none(row.get("year")) or 0,
            "hours_ploughed": _float_or_none(row.get("hours_ploughed")) or 0,
            "families_impacted": _int_or_none(row.get("families_impacted")) or 0,
            "hectares_ploughed": _float_or_none(row.get("hectares_ploughed")) or 0,
            "notes": _text(row.get("notes")),
        }
        self.client.table("ploughing_records").upsert(
            payload,
            on_conflict="site_id,year",
        ).execute()
        return f"Synced ploughing year `{payload['year']}` to Supabase."

    def _sync_maize(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "year": _int_or_none(row.get("year")) or 0,
            "farmers_impacted": _int_or_none(row.get("farmers_impacted")) or 0,
            "kilograms_bought": _float_or_none(row.get("kilograms_bought")) or 0,
            "meals_made": _int_or_none(row.get("meals_made")) or 0,
            "notes": _text(row.get("notes")),
        }
        self.client.table("maize_buyback_records").upsert(
            payload,
            on_conflict="site_id,year",
        ).execute()
        return f"Synced maize buy-back year `{payload['year']}` to Supabase."

    def _sync_rainfall_monthly(self, row: dict[str, str]) -> str:
        site_id = self._require_site_id(row.get("site_slug", ""))
        payload = {
            "site_id": site_id,
            "month": _int_or_none(row.get("month")) or 0,
            "month_label": _text(row.get("month_label")),
            "rainfall_mm": _float_or_none(row.get("rainfall_mm")) or 0,
            "temperature_c": _float_or_none(row.get("temperature_c")),
        }
        self.client.table("site_rainfall_monthly").upsert(
            payload,
            on_conflict="site_id,month",
        ).execute()
        return f"Synced rainfall month `{payload['month']}` to Supabase."

    def _sync_weekly_stat(self, row: dict[str, str]) -> str:
        site_id = self._site_id_for_church(row.get("church", ""))
        if not site_id:
            raise ValueError(
                f"Church `{row.get('church')}` does not match any `icbc_sites.name` in Supabase."
            )
        payload = {
            "site_id": site_id,
            "stat_date": _text(row.get("date")),
            "total_attendance": _int_or_none(row.get("total_attendance")) or 0,
            "men": _int_or_none(row.get("men")) or 0,
            "women": _int_or_none(row.get("women")) or 0,
            "youth": _int_or_none(row.get("youth")) or 0,
            "children": _int_or_none(row.get("children")) or 0,
            "salvations": _int_or_none(row.get("salvations")) or 0,
            "baptisms": _int_or_none(row.get("baptisms")) or 0,
            "home_visits": _int_or_none(row.get("home_visits")) or 0,
            "meals_food_packs": _int_or_none(row.get("meals_food_packs")) or 0,
            "preschool_attendance": _int_or_none(row.get("preschool_attendance")) or 0,
        }
        self.client.table("weekly_stats").upsert(
            payload,
            on_conflict="site_id,stat_date",
        ).execute()
        return f"Synced weekly stat `{payload['stat_date']}` for `{row.get('church')}` to Supabase."

    def _sync_bubele(self, row: dict[str, str]) -> str:
        payload = {
            "site_name": _text(row.get("site_name")),
            "family_code": _text(row.get("family_code")),
            "region": _text(row.get("region")),
            "latitude": _float_or_none(row.get("latitude")),
            "longitude": _float_or_none(row.get("longitude")),
        }
        self.client.table("bubele_care_sites").upsert(
            payload,
            on_conflict="family_code",
        ).execute()
        return f"Synced Bubele Care `{payload['family_code']}` to Supabase."


def build_sync_client(url: str, service_role_key: str) -> SupabaseSeedSync | None:
    if not _text(url) or not _text(service_role_key):
        return None
    try:
        return SupabaseSeedSync(_text(url), _text(service_role_key))
    except ImportError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Could not connect Supabase sync client: {exc}") from exc
