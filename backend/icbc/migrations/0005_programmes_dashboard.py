# Generated manually for programme tables

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("icbc", "0004_teacher_compassionatecaremember"),
    ]

    operations = [
        migrations.AddField(
            model_name="icbcsite",
            name="preschool_children_impacted",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Total preschool children impacted since the programme began.",
            ),
        ),
        migrations.CreateModel(
            name="PreschoolSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("children_count", models.PositiveIntegerField()),
                ("snapshot_date", models.DateField()),
                (
                    "year",
                    models.PositiveIntegerField(
                        help_text="Reporting year (e.g. 2024)."
                    ),
                ),
                (
                    "teachers_count",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preschool_snapshots",
                        to="icbc.icbcsite",
                    ),
                ),
            ],
            options={
                "ordering": ["-snapshot_date", "-year"],
                "unique_together": {("site", "snapshot_date")},
            },
        ),
        migrations.CreateModel(
            name="PloughingRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("year", models.PositiveIntegerField()),
                ("hours_ploughed", models.FloatField(default=0)),
                ("families_impacted", models.PositiveIntegerField(default=0)),
                ("hectares_ploughed", models.FloatField(default=0)),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ploughing_records",
                        to="icbc.icbcsite",
                    ),
                ),
            ],
            options={
                "ordering": ["-year"],
                "unique_together": {("site", "year")},
            },
        ),
        migrations.CreateModel(
            name="MaizeBuybackRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("year", models.PositiveIntegerField()),
                ("farmers_impacted", models.PositiveIntegerField(default=0)),
                ("kilograms_bought", models.FloatField(default=0)),
                ("meals_made", models.PositiveIntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maize_buyback_records",
                        to="icbc.icbcsite",
                    ),
                ),
            ],
            options={
                "ordering": ["-year"],
                "unique_together": {("site", "year")},
            },
        ),
    ]
