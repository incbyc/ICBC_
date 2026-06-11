from django.db.models import Avg, Count, Sum
from rest_framework import serializers

from .models import (
    ICBCSite,
    Pastor,
    SiteImage,
    SiteUpdate,
    WeeklyStat,
    Teacher,
    CompassionateCareMember,
)
from .programme_utils import parse_number, parse_preschool_summary
from .summary import build_global_summary

SIDEBAR_MIN_SALVATIONS = 20
SIDEBAR_MIN_BAPTISMS = 20
SIDEBAR_MIN_HOME_VISITS = 10
SIDEBAR_MIN_PLOUGH_HOURS = 20


class PastorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pastor
        fields = ("name", "role", "photo", "photo_path")


class SiteImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteImage
        fields = ("image", "caption", "is_featured", "sort_order")


class SiteUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteUpdate
        fields = ("title", "body", "image", "created_at")


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ("name", "role", "photo", "sort_order")


class CompassionateCareSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompassionateCareMember
        fields = ("name", "role", "photo", "sort_order")


class StaffMemberSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    role = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    year_joined = serializers.IntegerField(allow_null=True)
    photo = serializers.CharField(allow_null=True, required=False)
    photo_path = serializers.CharField(allow_blank=True, required=False)
    sort_order = serializers.IntegerField(required=False)


class StatsSummarySerializer(serializers.Serializer):
    sundays_recorded = serializers.IntegerField()
    avg_total_attendance = serializers.FloatField()
    avg_children = serializers.FloatField()
    avg_preschool = serializers.FloatField()
    total_preschool_attendance = serializers.IntegerField()
    total_salvations = serializers.IntegerField()
    total_baptisms = serializers.IntegerField()
    total_home_visits = serializers.IntegerField()
    avg_home_visits = serializers.FloatField()
    total_meals = serializers.IntegerField()


class ICBCSiteDetailSerializer(serializers.ModelSerializer):
    pastor = PastorSerializer(read_only=True)
    images = SiteImageSerializer(many=True, read_only=True)
    updates = SiteUpdateSerializer(many=True, read_only=True)
    teachers = TeacherSerializer(many=True, read_only=True)
    care_team = CompassionateCareSerializer(many=True, read_only=True)
    staff = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()
    stats_summary = serializers.SerializerMethodField()
    sidebar_dashboard = serializers.SerializerMethodField()

    class Meta:
        model = ICBCSite
        fields = (
            "slug",
            "name",
            "region",
            "year_constructed",
            "water_source",
            "preschool_summary",
            "preschool_children_impacted",
            "projects",
            "about",
            "ploughing_season",
            "hours_ploughed",
            "families_ploughed_for",
            "area_ploughed",
            "site_link",
            "photo_path",
            "cover_image",
            "latitude",
            "longitude",
            "pastor",
            "staff",
            "staff_count",
            "images",
            "updates",
            "teachers",
            "care_team",
            "stats_summary",
            "sidebar_dashboard",
        )

    def _photo_url(self, image_field):
        if not image_field:
            return None
        request = self.context.get("request")
        url = image_field.url
        if request and url and not url.startswith("http"):
            return request.build_absolute_uri(url)
        return url

    def _build_staff_list(self, obj):
        staff = []

        pastor = None
        try:
            pastor = obj.pastor
        except Pastor.DoesNotExist:
            pastor = None
        if pastor and pastor.name:
            staff.append(
                {
                    "full_name": pastor.name,
                    "role": "Pastor",
                    "description": "",
                    "year_joined": None,
                    "photo": self._photo_url(pastor.photo),
                    "photo_path": pastor.photo_path or "",
                    "sort_order": 0,
                }
            )

        for teacher in obj.teachers.all():
            staff.append(
                {
                    "full_name": teacher.name,
                    "role": "Teacher",
                    "description": "",
                    "year_joined": None,
                    "photo": self._photo_url(teacher.photo),
                    "photo_path": "",
                    "sort_order": teacher.sort_order,
                }
            )

        for member in obj.care_team.all():
            staff.append(
                {
                    "full_name": member.name,
                    "role": "Compassionate Care",
                    "description": "",
                    "year_joined": None,
                    "photo": self._photo_url(member.photo),
                    "photo_path": "",
                    "sort_order": member.sort_order,
                }
            )

        return staff

    def get_staff(self, obj):
        return self._build_staff_list(obj)

    def get_staff_count(self, obj):
        return len(self._build_staff_list(obj))

    def get_stats_summary(self, obj):
        qs = WeeklyStat.objects.filter(site=obj)

        if not qs.exists():
            return None

        sunday_count = qs.filter(total_attendance__gt=0).count()

        aggregates = qs.aggregate(
            avg_total_attendance=Avg("total_attendance"),
            avg_children=Avg("children"),
            avg_preschool=Avg("preschool_attendance"),
            total_preschool_attendance=Sum("preschool_attendance"),
            total_salvations=Sum("salvations"),
            total_baptisms=Sum("baptisms"),
            total_home_visits=Sum("home_visits"),
            avg_home_visits=Avg("home_visits"),
            total_meals=Sum("meals_food_packs"),
        )

        return {
            "sundays_recorded": sunday_count,
            "avg_total_attendance": round(
                aggregates["avg_total_attendance"] or 0, 1
            ),
            "avg_children": round(aggregates["avg_children"] or 0, 1),
            "avg_preschool": round(aggregates["avg_preschool"] or 0, 1),
            "total_preschool_attendance": int(
                aggregates["total_preschool_attendance"] or 0
            ),
            "total_salvations": int(aggregates["total_salvations"] or 0),
            "total_baptisms": int(aggregates["total_baptisms"] or 0),
            "total_home_visits": int(aggregates["total_home_visits"] or 0),
            "avg_home_visits": round(aggregates["avg_home_visits"] or 0, 1),
            "total_meals": int(aggregates["total_meals"] or 0),
        }

    def get_sidebar_dashboard(self, obj):
        stats = self.get_stats_summary(obj)
        metrics = []
        staff_count = self.get_staff_count(obj)
        if staff_count > 0:
            metrics.append(
                {
                    "key": "staff",
                    "title": "Staff",
                    "value": staff_count,
                    "format": "integer",
                }
            )

        if stats:
            metrics.append(
                {
                    "key": "avg_attendance",
                    "title": "Avg attendance",
                    "value": stats["avg_total_attendance"],
                    "format": "decimal",
                }
            )
            if stats["total_salvations"] >= SIDEBAR_MIN_SALVATIONS:
                metrics.append(
                    {
                        "key": "salvations",
                        "title": "Total salvations",
                        "value": stats["total_salvations"],
                        "format": "integer",
                    }
                )
            if stats["total_baptisms"] >= SIDEBAR_MIN_BAPTISMS:
                metrics.append(
                    {
                        "key": "baptisms",
                        "title": "Total baptisms",
                        "value": stats["total_baptisms"],
                        "format": "integer",
                    }
                )
            home_visits = stats["total_home_visits"]
            if home_visits >= SIDEBAR_MIN_HOME_VISITS:
                metrics.append(
                    {
                        "key": "home_visits",
                        "title": "Total home visits",
                        "value": home_visits,
                        "format": "integer",
                    }
                )

        coordinates = None
        if obj.latitude is not None and obj.longitude is not None:
            coordinates = {
                "latitude": obj.latitude,
                "longitude": obj.longitude,
                "label": f"{obj.latitude:.5f}, {obj.longitude:.5f}",
            }

        preschool = None
        snapshot = obj.preschool_snapshots.order_by("-snapshot_date").first()
        if snapshot:
            preschool = {
                "children_count": snapshot.children_count,
                "teachers_count": snapshot.teachers_count,
                "snapshot_date": snapshot.snapshot_date.isoformat(),
                "year": snapshot.year,
                "children_impacted_since_inception": obj.preschool_children_impacted,
            }
        elif obj.preschool_summary:
            parsed = parse_preschool_summary(obj.preschool_summary)
            if parsed.get("children_count"):
                preschool = {
                    "children_count": parsed["children_count"],
                    "teachers_count": parsed.get("teachers_count"),
                    "snapshot_date": None,
                    "year": None,
                    "children_impacted_since_inception": obj.preschool_children_impacted,
                    "summary_text": obj.preschool_summary,
                }

        ploughing = []
        for row in obj.ploughing_records.filter(
            hours_ploughed__gte=SIDEBAR_MIN_PLOUGH_HOURS
        ).order_by("-year"):
            ploughing.append(
                {
                    "year": row.year,
                    "hours_ploughed": row.hours_ploughed,
                    "families_impacted": row.families_impacted,
                    "hectares_ploughed": row.hectares_ploughed,
                }
            )

        if not ploughing:
            hours = parse_number(obj.hours_ploughed)
            if hours is not None and hours >= SIDEBAR_MIN_PLOUGH_HOURS:
                year_raw = (obj.ploughing_season or "").strip()
                year = int(year_raw) if year_raw.isdigit() else None
                ploughing.append(
                    {
                        "year": year,
                        "hours_ploughed": hours,
                        "families_impacted": int(
                            parse_number(obj.families_ploughed_for) or 0
                        ),
                        "hectares_ploughed": parse_number(obj.area_ploughed) or 0,
                    }
                )

        maize = []
        for row in obj.maize_buyback_records.order_by("-year"):
            if not (
                row.farmers_impacted
                or row.kilograms_bought
                or row.meals_made
            ):
                continue
            maize.append(
                {
                    "year": row.year,
                    "farmers_impacted": row.farmers_impacted,
                    "kilograms_bought": row.kilograms_bought,
                    "meals_made": row.meals_made,
                }
            )

        if not maize and (
            obj.maize_farmers_supported or obj.maize_tonnes_purchased
        ):
            year_raw = (obj.ploughing_season or "").strip()
            year = int(year_raw) if year_raw.isdigit() else None
            maize.append(
                {
                    "year": year,
                    "farmers_impacted": obj.maize_farmers_supported,
                    "kilograms_bought": float(obj.maize_tonnes_purchased or 0)
                    * 1000,
                    "meals_made": 0,
                }
            )

        return {
            "coordinates": coordinates,
            "metrics": metrics,
            "preschool": preschool,
            "ploughing": ploughing,
            "maize_buyback": maize,
        }


class GlobalSummarySerializer(serializers.Serializer):
    total_icbcs = serializers.IntegerField()
    total_attendance = serializers.IntegerField()
    total_preschool_children_impacted = serializers.IntegerField()
    total_salvations = serializers.IntegerField()
    total_baptisms = serializers.IntegerField()
    total_home_visits = serializers.IntegerField()
    total_meals = serializers.IntegerField()
    total_plough_hours = serializers.FloatField()
    total_plough_hectares = serializers.FloatField()
    total_plough_families = serializers.IntegerField()
    total_maize_tonnes = serializers.FloatField()
    total_maize_farmers = serializers.IntegerField()

    @classmethod
    def from_db(cls):
        data = build_global_summary()
        return cls(data)

