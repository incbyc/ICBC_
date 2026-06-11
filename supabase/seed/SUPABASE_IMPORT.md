# Import ICBC data into Supabase

**First-time setup?** Use the detailed guide: [`../IMPORT_WALKTHROUGH.md`](../IMPORT_WALKTHROUGH.md)

This project uses a normalized schema:
- `icbc_sites` stores core site profile data only
- staff and programme history live in separate tables
- CSV imports that use `site_slug` go into staging tables first

## 1. Create tables

Run `schema.sql` in Supabase SQL Editor.

If you already created an older database with ploughing / maize fields on `icbc_sites`,
run `programmes_setup.sql` after `schema.sql` to clean that up.

## 2. Import direct CSVs

Use Supabase Table Editor → Import CSV for these tables:

| Table | CSV file |
|-------|----------|
| `icbc_sites` | `seed/icbc_sites.csv` |
| `bubele_care_sites` | `seed/bubele_care_sites.csv` |
| `staff_import` | `seed/staff.csv` |
| `preschool_snapshots_import` | `seed/preschool_snapshots.csv` |
| `ploughing_records_import` | `seed/ploughing_records.csv` |
| `maize_buyback_records_import` | `seed/maize_buyback_records.csv` |

For staff photos, leave `photo_url` blank until your Streamlit uploader sends the image
to GitHub and writes the final GitHub URL back to Supabase.

## 3. Process staging imports

Run this once after the CSV imports:

```sql
select public.process_all_site_imports();
```

That will move rows from the staging import tables into:
- `staff`
- `preschool_snapshots`
- `ploughing_records`
- `maize_buyback_records`

## 4. Weekly stats

Regenerate the seed CSV from the consolidated workbook (Weekly Data sheet only):

```bash
python scripts/excel_to_weekly_stats_csv.py "ICBC_Church_Stats_Consolidated (7).xlsx"
```

Run `weekly_stats_setup.sql`, then import `seed/weekly_stats.csv` into `weekly_stats_import`,
then run:

```sql
select * from public.process_weekly_stats_import();
```

5. Run **`weekly_stats_sidebar_view.sql`** in the SQL Editor (creates `icbc_site_stats_summary` for the map sidebar).

## 5. Regenerate seed files after editing map JS

```bash
python scripts/generate_supabase_seed.py
```
