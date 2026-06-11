from django.db import models
from django.utils.text import slugify


class ICBCSite(models.Model):
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    name = models.CharField(max_length=120)

    region = models.CharField(max_length=80, blank=True)
    year_constructed = models.CharField(max_length=16, blank=True)
    water_source = models.CharField(max_length=255, blank=True)
    preschool_summary = models.CharField(max_length=255, blank=True)

    projects = models.TextField(blank=True)
    about = models.TextField(blank=True)

    ploughing_season = models.CharField(max_length=16, blank=True)
    hours_ploughed = models.CharField(max_length=64, blank=True)
    families_ploughed_for = models.CharField(max_length=128, blank=True)
    area_ploughed = models.CharField(max_length=128, blank=True)

    site_link = models.URLField(blank=True)

    # Legacy relative path used by the existing Leaflet map (images/…)
    photo_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Relative image path used for the panorama/cover image (existing static assets).",
    )

    # New uploaded cover image (drag & drop in admin, used on ICBC page)
    cover_image = models.ImageField(
        upload_to="icbc_covers/",
        blank=True,
        null=True,
        help_text="Panoramic cover photo for this ICBC site.",
    )

    # Maize buy-back stats (can be managed/imported via admin)
    maize_tonnes_purchased = models.FloatField(
        default=0,
        help_text="Total tonnes of maize purchased so far for this ICBC.",
    )
    maize_farmers_supported = models.PositiveIntegerField(
        default=0,
        help_text="Number of farmers supported through the maize buy-back programme.",
    )

    preschool_children_impacted = models.PositiveIntegerField(
        default=0,
        help_text="Total preschool children impacted since the programme began.",
    )

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Pastor(models.Model):
    site = models.OneToOneField(
        ICBCSite,
        related_name="pastor",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    photo_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Relative pastor photo path (existing static asset).",
    )
    photo = models.ImageField(
        upload_to="pastors/",
        blank=True,
        null=True,
        help_text="Uploaded pastor portrait used on the ICBC page.",
    )
    role = models.CharField(max_length=80, default="Pastor", blank=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.site.name})"


class BubeleCareSite(models.Model):
    site_name = models.CharField(max_length=120)
    family_code = models.CharField(max_length=40)
    region = models.CharField(max_length=80, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Bubele Care site"
        verbose_name_plural = "Bubele Care sites"
        ordering = ["site_name"]

    def __str__(self) -> str:
        return f"{self.site_name} ({self.family_code})"


class SiteImage(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="images",
        on_delete=models.CASCADE,
    )
    image = models.ImageField(upload_to="icbc_sites/gallery/")
    caption = models.CharField(max_length=255, blank=True)
    is_featured = models.BooleanField(
        default=False,
        help_text="If checked, this image may be highlighted on the ICBC page.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"Image for {self.site.name}"


class SiteUpdate(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="updates",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="icbc_updates/",
        blank=True,
        null=True,
        help_text="Optional photo for this update.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.site.name} – {self.title}"


class PreschoolSnapshot(models.Model):
    """Point-in-time preschool enrolment for an ICBC."""

    site = models.ForeignKey(
        ICBCSite,
        related_name="preschool_snapshots",
        on_delete=models.CASCADE,
    )
    children_count = models.PositiveIntegerField()
    snapshot_date = models.DateField()
    year = models.PositiveIntegerField(
        help_text="Reporting year (e.g. 2024).",
    )
    teachers_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-snapshot_date", "-year"]
        unique_together = ("site", "snapshot_date")

    def __str__(self) -> str:
        return f"{self.site.name} preschool – {self.snapshot_date}"


class PloughingRecord(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="ploughing_records",
        on_delete=models.CASCADE,
    )
    year = models.PositiveIntegerField()
    hours_ploughed = models.FloatField(default=0)
    families_impacted = models.PositiveIntegerField(default=0)
    hectares_ploughed = models.FloatField(default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-year"]
        unique_together = ("site", "year")

    def __str__(self) -> str:
        return f"{self.site.name} ploughing {self.year}"


class MaizeBuybackRecord(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="maize_buyback_records",
        on_delete=models.CASCADE,
    )
    year = models.PositiveIntegerField()
    farmers_impacted = models.PositiveIntegerField(default=0)
    kilograms_bought = models.FloatField(default=0)
    meals_made = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-year"]
        unique_together = ("site", "year")

    def __str__(self) -> str:
        return f"{self.site.name} maize {self.year}"


class WeeklyStat(models.Model):
    """Weekly statistics for an ICBC site (one row per church per Sunday)."""

    site = models.ForeignKey(
        ICBCSite,
        related_name="weekly_stats",
        on_delete=models.CASCADE,
    )
    date = models.DateField()

    source_file = models.CharField(max_length=255, blank=True)
    sheet_name = models.CharField(max_length=100, blank=True)

    total_attendance = models.IntegerField(default=0)
    men = models.IntegerField(default=0)
    women = models.IntegerField(default=0)
    youth = models.IntegerField(default=0)
    children = models.IntegerField(default=0)

    salvations = models.IntegerField(default=0)
    baptisms = models.IntegerField(default=0)
    home_visits = models.IntegerField(default=0)
    meals_food_packs = models.IntegerField(default=0)
    preschool_attendance = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("site", "date")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.site.name} – {self.date}"


class StatsWorkbookUpload(models.Model):
    """
    Raw Excel upload for weekly statistics.
    Dropping a workbook here parses all churches & creates WeeklyStat rows.
    """

    file = models.FileField(upload_to="stats_workbooks/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_records = models.PositiveIntegerField(default=0)
    skipped_duplicates = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"Stats workbook – {self.file.name}"


class Teacher(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="teachers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    role = models.CharField(
        max_length=120,
        blank=True,
        help_text="e.g. Lead Teacher, Assistant Teacher",
    )
    photo = models.ImageField(
        upload_to="teachers/",
        blank=True,
        null=True,
        help_text="Portrait photo of this teacher.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"Teacher {self.name} ({self.site.name})"


class CompassionateCareMember(models.Model):
    site = models.ForeignKey(
        ICBCSite,
        related_name="care_team",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    role = models.CharField(
        max_length=120,
        blank=True,
        help_text="e.g. Coordinator, Volunteer",
    )
    photo = models.ImageField(
        upload_to="care_team/",
        blank=True,
        null=True,
        help_text="Portrait photo of this care team member.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Compassionate care team member"
        verbose_name_plural = "Compassionate care team members"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"Care team {self.name} ({self.site.name})"

