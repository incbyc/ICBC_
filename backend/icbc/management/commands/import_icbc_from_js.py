import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from icbc.models import BubeleCareSite, ICBCSite, Pastor


class Command(BaseCommand):
    help = "Import ICBC and Bubele Care sites from existing JS data files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing ICBCSite, Pastor and BubeleCareSite rows before import.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        project_root = base_dir.parent

        icbc_js_path = project_root / "data" / "ICBCSites_6.js"
        bubele_js_path = project_root / "data" / "BubeleCare_10.js"

        if options["reset"]:
            self.stdout.write("Reset requested: deleting existing rows…")
            Pastor.objects.all().delete()
            ICBCSite.objects.all().delete()
            BubeleCareSite.objects.all().delete()

        self._import_icbc(icbc_js_path)
        self._import_bubele(bubele_js_path)

        self.stdout.write(self.style.SUCCESS("Import completed."))

    def _load_js_feature_collection(self, path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(path)

        text = path.read_text(encoding="utf-8")
        # Strip "var json_xxx = " prefix and optional trailing semicolon.
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            raise ValueError(f"Could not locate JSON object in {path}")

        json_str = text[first_brace : last_brace + 1]
        return json.loads(json_str)

    def _import_icbc(self, path: Path) -> None:
        self.stdout.write(f"Importing ICBC sites from {path}…")
        data = self._load_js_feature_collection(path)
        features = data.get("features", [])

        for feature in features:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None]

            name = (props.get("Site Name") or "").strip()
            if not name:
                continue

            slug = slugify(name)

            longitude, latitude = None, None
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                longitude, latitude = coords[0], coords[1]

            site, _created = ICBCSite.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "region": props.get("Region") or "",
                    "year_constructed": (props.get("Year Constructed") or "").strip(),
                    "water_source": props.get("Water Source") or "",
                    "preschool_summary": props.get("PreSchool") or "",
                    "projects": props.get("Projects") or "",
                    "about": props.get("About") or "",
                    "ploughing_season": (props.get("Ploughing Season") or "").strip(),
                    "hours_ploughed": (props.get("Hours Ploughed") or "").strip(),
                    "families_ploughed_for": (props.get("Families Ploughed for") or "").strip(),
                    "area_ploughed": (props.get("Area Ploughed") or "").strip(),
                    "site_link": props.get("Site Link") or "",
                    "photo_path": self._normalise_image_path(props.get("Photo")),
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )

            pastor_name = (props.get("Pastor") or "").strip()
            if pastor_name:
                Pastor.objects.update_or_create(
                    site=site,
                    defaults={
                        "name": pastor_name,
                        "photo_path": self._normalise_image_path(props.get("Pastors Photo")),
                    },
                )

        self.stdout.write(f"Imported or updated {ICBCSite.objects.count()} ICBC sites.")

    def _import_bubele(self, path: Path) -> None:
        self.stdout.write(f"Importing Bubele Care sites from {path}…")
        data = self._load_js_feature_collection(path)
        features = data.get("features", [])

        for feature in features:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None]

            site_name = (props.get("Site") or "").strip()
            family_code = (props.get("Family Code") or "").strip()
            if not site_name or not family_code:
                continue

            longitude, latitude = None, None
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                longitude, latitude = coords[0], coords[1]

            BubeleCareSite.objects.update_or_create(
                family_code=family_code,
                defaults={
                    "site_name": site_name,
                    "region": props.get("Region") or "",
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )

        self.stdout.write(
            f"Imported or updated {BubeleCareSite.objects.count()} Bubele Care sites."
        )

    def _normalise_image_path(self, raw):
        """Return a sanitised relative image filename or empty string."""
        if not raw:
            return ""
        safe = str(raw).replace("\\", "_").replace("/", "_").replace(":", "_").strip()
        return safe

