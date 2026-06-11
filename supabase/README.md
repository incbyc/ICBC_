# Supabase database for ICBC map

Yes — you can keep the **GitHub Pages static site** and store all editable data in **Supabase**. Use the Supabase Table Editor as your admin UI.

## Quick start (import into Supabase)

**Full step-by-step checklist:** [`IMPORT_WALKTHROUGH.md`](IMPORT_WALKTHROUGH.md) (recommended) · [`seed/SUPABASE_IMPORT.md`](seed/SUPABASE_IMPORT.md) (short reference)

1. **SQL Editor** → run `schema.sql`.
2. **Table Editor** → import `seed/icbc_sites.csv` and `seed/bubele_care_sites.csv`.
3. **Table Editor** → import `seed/staff.csv`, `seed/preschool_snapshots.csv`, `seed/ploughing_records.csv`, and `seed/maize_buyback_records.csv` into their matching `*_import` staging tables.
4. **SQL Editor** → run `select public.process_all_site_imports();`
5. Edit rows in Table Editor (videos, historical maize rows, more staff, weekly stats).

Regenerate CSVs after editing map JS data:

```bash
python scripts/generate_supabase_seed.py
```

## Questionnaire → staff import

Filled **ICBC Of The Month** Word files in `Questionnaires/` can be parsed into `seed/staff.csv`:

```bash
python scripts/questionnaires_to_staff.py
```

This adds/updates **Pastor**, **Teacher**, and **Compassionate Care** rows with narrative descriptions compiled from each questionnaire. See `seed/questionnaire_import_report.md` for per-site coverage.

## Local seed admin app

There is now a local Streamlit tool for editing the seed files before you import them into Supabase:

```bash
pip install -r requirements.txt
streamlit run seed_admin_app.py
```

What it does:

- edits local `supabase/seed/*.csv` files only
- upserts rows instead of creating duplicate key rows
- supports manual entry per tab (`ICBC Sites`, `Staff`, `Preschools`, `Ploughing`, `Maize Buy-Back`, `Weekly Stats`, `Bubele Care`)
- supports bulk CSV uploads for each tab
- supports weekly-stats Excel workbook uploads using the existing parser
- can copy uploaded images into the repo and write repo-friendly paths / GitHub-friendly URLs into the seed rows

### Media strategy

For now, uploaded media is stored in the repo first, not in Supabase Storage.

- site images are copied into `images/seed_uploads/...`
- `photo_path` keeps a repo-relative path for static assets
- `cover_image_url` / `photo_url` can be written as:
  - a repo-relative path, or
  - a public GitHub URL when you fill in the repo + branch settings in the Streamlit sidebar

That means you can commit the CSVs and the uploaded images together, push the repo to GitHub, and import the same seed data later.

## What’s in this folder

| File | Purpose |
|------|---------|
| `schema.sql` | Normalized schema + RLS + import staging tables |
| `programmes_setup.sql` | Cleanup helper for an older database that still had programme fields on `icbc_sites` |
| `weekly_stats_setup.sql` | Staging import for spreadsheet weekly stats |
| `weekly_stats_sidebar_view.sql` | Sidebar rollups view (`icbc_site_stats_summary`) |
| `seed/icbc_sites.csv` | Core ICBC site profile data only |
| `seed/bubele_care_sites.csv` | Bubele Care sites in their own table |
| `seed/staff.csv` | Staff import CSV keyed by `site_slug` |
| `seed/preschool_snapshots.csv` | Historical preschool snapshots keyed by `site_slug` |
| `seed/ploughing_records.csv` | Historical ploughing rows keyed by `site_slug` |
| `seed/maize_buyback_records.csv` | Historical maize buy-back rows keyed by `site_slug` |
| `seed/*_template.csv` | Manual import templates for staging tables |

## Normalized design

- `icbc_sites` stores only core site profile data.
- `staff` stores pastors, teachers, care team, and other people.
- `preschool_snapshots`, `ploughing_records`, `maize_buyback_records`, and `weekly_stats` store historical programme data.
- `bubele_care_sites` stays completely separate from `icbc_sites`.

The `*_import` staging tables exist so you can import CSVs with `site_slug` directly, then let Supabase link those rows to the real `site_id`.

For staff photos, use `photo_url` only. The intended flow is:
- upload the image from your local Streamlit tool to GitHub
- store the final GitHub URL in `staff.photo_url`

**UI behaviour:**
- **Map sidebar** — pastor photo, pastor description, total staff count
- **Full profile** (`icbc.html`) — pastor + teachers + care team with descriptions

## Per-ICBC video (for map sidebar)

Each row in `icbc_sites` has a **`video_url`** column.

In Supabase Table Editor, paste a YouTube link per church, for example:

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`

The static map will embed this in the sidebar (we’ll wire `index.html` to Supabase next).

`site_link` can stay as a general channel or website; **`video_url`** is the dedicated clip for that ICBC.

## Historical programme data

Historical programme imports belong in these tables:

- `preschool_snapshots`
- `ploughing_records`
- `maize_buyback_records`
- `weekly_stats`

That keeps programme history out of `icbc_sites` and makes it easy to import multiple years cleanly.

## Weekly stats (your spreadsheet columns)

Your table headers map to Supabase like this:

| Your spreadsheet   | Import column (`weekly_stats_import`) | Stored in `weekly_stats` |
|--------------------|----------------------------------------|---------------------------|
| Church             | `church`                               | linked via `site_id`      |
| Date               | `date`                                 | `stat_date`               |
| Total Attendance   | `total_attendance`                     | `total_attendance`        |
| Men                | `men`                                  | `men`                     |
| Women              | `women`                                | `women`                     |
| Youth              | `youth`                                | `youth`                     |
| Children           | `children`                             | `children`                |
| Salvations         | `salvations`                           | `salvations`                |
| Baptisms           | `baptisms`                             | `baptisms`                |
| Home Visits        | `home_visits`                          | `home_visits`             |
| Meals / Food Packs | `meals_food_packs`                     | `meals_food_packs`        |
| Preschool Attendance | `preschool_attendance`               | `preschool_attendance`    |

Use `ICBC_Church_Stats_Consolidated*.xlsx` → **Weekly Data** sheet only (not Monthly Summary).

### Setup (once)

1. Run `weekly_stats_setup.sql` in the SQL Editor (creates staging table + import function).
2. Make sure `icbc_sites` is already imported.

### Option A — Import from Excel

```bash
python scripts/excel_to_weekly_stats_csv.py "path/to/your-stats.xlsx"
```

This writes `supabase/seed/weekly_stats.csv`.

3. Supabase → **Table Editor** → `weekly_stats_import` → **Import CSV** → choose that file.
4. **SQL Editor** → run:

```sql
select * from public.process_weekly_stats_import();
```

The result shows how many rows were inserted, updated, skipped (bad date), and any **unmatched church** names.

Check unmatched names:

```sql
select * from public.weekly_stats_unmatched_churches;
```

Fix church spelling in the CSV or add/fix the site in `icbc_sites`, then import again.

### Option B — Edit directly in Supabase

1. Open `weekly_stats_import` in Table Editor.
2. Add rows (or import `seed/weekly_stats_template.csv` as a starting point).
3. Use **dates as `YYYY-MM-DD`** (example: `2024-12-29`).
4. Run `select * from process_weekly_stats_import();`

### Clear staging before a re-import

```sql
truncate table public.weekly_stats_import;
```

`weekly_stats` keeps existing rows; re-processing the same church+date **updates** numbers (does not duplicate).

### Sidebar rollups view (not a CSV)

After weekly stats are loaded, run **`weekly_stats_sidebar_view.sql`** in the SQL Editor.

This creates **`icbc_site_stats_summary`** — one row per ICBC with:

| Column | Meaning |
|--------|---------|
| `avg_attendance` | Average Sunday attendance (always in `sidebar_metrics`) |
| `total_salvations` | Raw total (shown in sidebar only if **> 10**) |
| `total_baptisms` | Raw total (shown in sidebar only if **> 10**) |
| `total_home_visits` | Raw total (shown in sidebar only if **> 50**) |
| `show_salvations`, `show_baptisms`, `show_home_visits` | Boolean flags |
| `sidebar_metrics` | JSON array ready for `index.html` (same shape as Django) |

Example query in Supabase or from the map:

```sql
select slug, avg_attendance, sidebar_metrics
from public.icbc_site_stats_summary
where slug = 'bulunga';
```

## Tables you can grow later

- `site_updates`, `site_images` — news & gallery
- Supabase Storage buckets for uploaded photos if you move beyond GitHub `images/`

## Static site + Supabase

- **Read**: browser uses the public Supabase URL + `anon` key (with Row Level Security allowing `SELECT`).
- **Write**: you edit in Supabase UI (service role / dashboard), not from the public map.
- **No Django server** required in production.

When you’re ready, we can connect `index.html` / `icbc.html` to Supabase and add the video player in the sidebar.
