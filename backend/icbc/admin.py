from django.contrib import admin, messages
from django.utils.html import format_html
from urllib.parse import quote as urlquote

from . import stats_parser
from .models import (
    BubeleCareSite,
    ICBCSite,
    MaizeBuybackRecord,
    Pastor,
    PloughingRecord,
    PreschoolSnapshot,
    SiteImage,
    SiteUpdate,
    StatsWorkbookUpload,
    WeeklyStat,
    Teacher,
    CompassionateCareMember,
)


class SiteImageInline(admin.TabularInline):
    model = SiteImage
    extra = 1


class SiteUpdateInline(admin.TabularInline):
    model = SiteUpdate
    extra = 1
    fields = ("title", "body", "image", "created_at")
    readonly_fields = ("created_at",)


class TeacherInline(admin.TabularInline):
    model = Teacher
    extra = 1


class CompassionateCareInline(admin.TabularInline):
    model = CompassionateCareMember
    extra = 1


class PreschoolSnapshotInline(admin.TabularInline):
    model = PreschoolSnapshot
    extra = 0


class PloughingRecordInline(admin.TabularInline):
    model = PloughingRecord
    extra = 0


class MaizeBuybackRecordInline(admin.TabularInline):
    model = MaizeBuybackRecord
    extra = 0


@admin.register(ICBCSite)
class ICBCSiteAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "year_constructed", "ploughing_season", "public_page")
    list_filter = ("region", "ploughing_season")
    search_fields = ("name", "region", "about", "projects")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [
        SiteImageInline,
        SiteUpdateInline,
        TeacherInline,
        CompassionateCareInline,
        PreschoolSnapshotInline,
        PloughingRecordInline,
        MaizeBuybackRecordInline,
    ]

    def public_page(self, obj):
        """
        Link to the public ICBC page that everyone sees.
        Adjust the URL pattern here if your frontend path changes.
        """
        name = urlquote(obj.name)
        # By default, point to the static frontend running on port 8080.
        # Change the host/port here if you serve the ICBC page elsewhere.
        url = f"http://127.0.0.1:8080/icbc.html?site={name}"
        return format_html('<a href="{}" target="_blank">View page</a>', url)

    public_page.short_description = "Public page"


@admin.register(Pastor)
class PastorAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "role")
    search_fields = ("name", "site__name")


@admin.register(BubeleCareSite)
class BubeleCareSiteAdmin(admin.ModelAdmin):
    list_display = ("site_name", "family_code", "region")
    list_filter = ("region",)
    search_fields = ("site_name", "family_code")


@admin.register(WeeklyStat)
class WeeklyStatAdmin(admin.ModelAdmin):
    list_display = ("site", "date", "total_attendance", "salvations", "baptisms")
    list_filter = ("site", "date")
    search_fields = ("site__name",)


@admin.register(StatsWorkbookUpload)
class StatsWorkbookUploadAdmin(admin.ModelAdmin):
    list_display = (
        "file",
        "uploaded_at",
        "processed",
        "processed_records",
        "skipped_duplicates",
    )
    readonly_fields = ("uploaded_at", "processed_records", "skipped_duplicates")

    def save_model(self, request, obj, form, change):
        """
        When a workbook is uploaded, parse it and create WeeklyStat rows.
        """
        super().save_model(request, obj, form, change)

        if obj.processed or not obj.file:
            return

        file_bytes = obj.file.read()
        filename = obj.file.name

        records, duplicates = stats_parser.parse_workbook(file_bytes, filename)

        created = 0
        unmatched = set()
        from django.utils.dateparse import parse_date
        from .models import ICBCSite, WeeklyStat  # local import to avoid circulars

        def normalise_site_name(name: str) -> str:
            """
            Normalise church names coming from spreadsheets so they match ICBCSite.name.
            Handles suffixes like 'CLC Church' and region qualifiers in brackets.
            """
            base = (name or "").strip().lower()
            # Drop region qualifiers like " (Shiselweni)"
            if "(" in base:
                base = base.split("(", 1)[0].strip()
            # Treat "Hawane CLC Church" / "Mpolonjeni CLC" as "hawane" / "mpolonjeni"
            base = base.replace(" clc church", "").strip()
            base = base.replace(" clc", "").strip()
            return base

        sites_by_key = {
            normalise_site_name(s.name): s for s in ICBCSite.objects.all()
        }

        for rec in records:
            site_name = rec.get("Church", "")
            site = sites_by_key.get(normalise_site_name(site_name))
            if not site:
                unmatched.add(site_name or "")
                continue

            date_str = rec.get("Date")
            date = parse_date(str(date_str))
            if not date:
                continue

            _, created_flag = WeeklyStat.objects.get_or_create(
                site=site,
                date=date,
                defaults={
                    "source_file": rec.get("Source File", ""),
                    "sheet_name": rec.get("Sheet", ""),
                    "total_attendance": rec.get("Total Attendance", 0) or 0,
                    "men": rec.get("Men", 0) or 0,
                    "women": rec.get("Women", 0) or 0,
                    "youth": rec.get("Youth", 0) or 0,
                    "children": rec.get("Children", 0) or 0,
                    "salvations": rec.get("Salvations", 0) or 0,
                    "baptisms": rec.get("Baptisms", 0) or 0,
                    "home_visits": rec.get("Home Visits", 0) or 0,
                    "meals_food_packs": rec.get("Meals / Food Packs", 0) or 0,
                    "preschool_attendance": rec.get("Preschool Attendance", 0) or 0,
                },
            )
            if created_flag:
                created += 1

        obj.processed = True
        obj.processed_records = created
        obj.skipped_duplicates = duplicates
        obj.save(update_fields=["processed", "processed_records", "skipped_duplicates"])

        unmatched_clean = [n for n in unmatched if n]
        if unmatched_clean:
            preview = ", ".join(sorted(unmatched_clean)[:5])
            extra = f" – unmatched churches (no ICBC site): {len(unmatched_clean)} (e.g. {preview})"
        else:
            extra = ""

        self.message_user(
            request,
            f"Processed stats workbook. New rows: {created}, duplicates inside workbook: {duplicates}.{extra}",
            level=messages.SUCCESS,
        )

