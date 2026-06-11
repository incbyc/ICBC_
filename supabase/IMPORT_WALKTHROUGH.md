# Move ICBC data to Supabase — step-by-step

Use this guide the first time you load your seed files into a new Supabase project.

**Time:** about 30–45 minutes  
**Files:** everything is already in `supabase/seed/*.csv` in this repo.

---

## Before you start

1. Finish any edits in the **Seed Admin** app (`streamlit run seed_admin_app.py`) so your CSVs are up to date.
2. Create a free account at [supabase.com](https://supabase.com) if you do not have one.
3. Have this folder open: `ICBC_-main/supabase/`

You will **not** put database passwords in GitHub. Only the public `anon` key goes in the static site later.

---

## Step 1 — Create a Supabase project

1. Log in to [Supabase Dashboard](https://supabase.com/dashboard).
2. **New project** → pick an organisation → name it (e.g. `icbc-eswatini`).
3. Set a **database password** (save it somewhere safe — you need it for direct DB access, not for the map).
4. Choose a **region** close to Eswatini if possible (e.g. South Africa).
5. Wait until the project status is **Active**.

---

## Step 2 — Run the database schema (tables + functions)

1. In your project, open **SQL Editor** (left sidebar).
2. Click **New query**.
3. On your computer, open `supabase/schema.sql`, copy **the entire file**, paste into the editor.
4. Click **Run** (or Ctrl+Enter).
5. You should see **Success**. If you get errors about objects already existing, you may have run it before — that is OK for `create table if not exists`.

**Optional (only if you created an old test DB earlier):**  
Run `supabase/programmes_setup.sql` the same way to drop legacy columns from `icbc_sites`.

**Check:** Table Editor → you should see tables including:
- `icbc_sites`, `staff`, `bubele_care_sites`
- `staff_import`, `preschool_snapshots_import`, `ploughing_records_import`, `maize_buyback_records_import`

---

## Step 3 — Import core site data (direct tables)

These CSVs go into the **real** tables (not staging).

| Step | Table in Supabase | CSV file on your PC |
|------|-------------------|---------------------|
| 3a | `icbc_sites` | `supabase/seed/icbc_sites.csv` |
| 3b | `bubele_care_sites` | `supabase/seed/bubele_care_sites.csv` |

For each table:

1. **Table Editor** → select the table.
2. **Insert** → **Import data from CSV** (or **Import** button).
3. Choose the CSV file.
4. Map columns if asked (headers should match).
5. Confirm import.

**Check:**

```sql
select count(*) as icbc_sites from public.icbc_sites;
select count(*) as bubele from public.bubele_care_sites;
```

Expect about **44** ICBC sites and **16** Bubele rows (numbers may vary slightly if you added sites).

---

## Step 4 — Import staff & programme history (staging tables)

These use `site_slug` in the CSV; Supabase links them to `icbc_sites` in the next step.

| Table in Supabase | CSV file |
|-------------------|----------|
| `staff_import` | `supabase/seed/staff.csv` |
| `preschool_snapshots_import` | `supabase/seed/preschool_snapshots.csv` |
| `ploughing_records_import` | `supabase/seed/ploughing_records.csv` |
| `maize_buyback_records_import` | `supabase/seed/maize_buyback_records.csv` |

Import each CSV the same way as Step 3.

**Tip:** `staff.csv` uses `site_slug` (e.g. `bulunga`), not UUIDs — that is correct.

**Check:**

```sql
select count(*) from public.staff_import;
select count(*) from public.ploughing_records_import;
```

---

## Step 5 — Process staging → live tables

In **SQL Editor**, run:

```sql
select public.process_all_site_imports();
```

You should get a JSON result with counts for staff, preschool, ploughing, and maize.

**Check:**

```sql
select count(*) from public.staff;
select count(*) from public.preschool_snapshots;
select count(*) from public.ploughing_records;
select count(*) from public.maize_buyback_records;
```

**If staff count is 0**, check for unmatched slugs:

```sql
select distinct site_slug
from public.staff_import i
where not exists (
  select 1 from public.icbc_sites s where s.slug = i.site_slug
);
```

Fix typos in the CSV or in `icbc_sites`, re-import `staff_import`, and run `process_all_site_imports()` again.

---

## Step 6 — Weekly stats (~8,600 rows)

### 6a — Staging table + import function

1. SQL Editor → New query.
2. Copy all of `supabase/weekly_stats_setup.sql` → **Run**.

### 6b — Import the CSV

1. Table Editor → `weekly_stats_import`.
2. Import `supabase/seed/weekly_stats.csv`.

This file is large; the import may take a minute. If the UI times out, try again or import in two halves (filter by church in Excel — last resort).

Columns in the CSV:

`church`, `date`, `total_attendance`, `men`, `women`, `youth`, `children`, `salvations`, `baptisms`, `home_visits`, `meals_food_packs`, `preschool_attendance`

### 6c — Process into `weekly_stats`

```sql
select * from public.process_weekly_stats_import();
```

Note the result: `inserted`, `updated`, `skipped_bad_date`, `unmatched_churches`.

**Check unmatched churches:**

```sql
select * from public.weekly_stats_unmatched_churches;
```

Should return **no rows** if every church name matches `icbc_sites.name`.

**Check totals:**

```sql
select count(*) from public.weekly_stats;
select church, count(*) from public.weekly_stats w
join public.icbc_sites s on s.id = w.site_id
group by church order by church;
```

---

## Step 7 — Sidebar stats view (for the map later)

SQL Editor → run the entire file:

`supabase/weekly_stats_sidebar_view.sql`

**Check:**

```sql
select slug, avg_attendance, total_salvations, sidebar_metrics
from public.icbc_site_stats_summary
where slug = 'bulunga';
```

You should see average attendance and a JSON `sidebar_metrics` array.

---

## Step 8 — Save API keys for the website (do not commit secrets)

1. Supabase → **Project Settings** → **API**.
2. Copy:
   - **Project URL** (e.g. `https://xxxxx.supabase.co`)
   - **anon public** key (safe for the browser with RLS enabled)

You will paste these into `index.html` / a small config file when we wire the map to Supabase.  
**Never** put the `service_role` key in GitHub or in the public site.

---

## Step 9 — Quick manual fixes in Table Editor

After import, you can edit rows directly in Supabase:

| Table | What to add/edit |
|-------|------------------|
| `icbc_sites` | `video_url` (YouTube per church) |
| `staff` | `description`, `photo_url` (GitHub image URLs) |
| `icbc_sites` | `cover_image_url` |

Staff photos: use full public URLs in `photo_url` (e.g. raw GitHub or jsDelivr), not only local paths.

---

## Re-importing later (without duplicates)

| Data | What to do |
|------|------------|
| Sites / Bubele | Update rows in Table Editor, or truncate table and re-import CSV |
| Staff / preschool / ploughing / maize | Truncate `*_import`, re-import CSV, run `process_all_site_imports()` again |
| Weekly stats | `truncate table public.weekly_stats_import;` → re-import CSV → `process_weekly_stats_import()` (same church+date **updates**, does not duplicate) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `process_all_site_imports` fails | Ensure `icbc_sites` imported first; check `staff_import.site_slug` matches `icbc_sites.slug` |
| Weekly stats `unmatched_churches` | Fix church name in CSV or add missing site to `icbc_sites` |
| CSV import column mismatch | CSV header row must match table columns exactly |
| Permission denied on map later | RLS policies in `schema.sql` allow public **read**; writes use dashboard only |
| Import too slow for weekly stats | Run during off-peak; or ask for a one-time SQL script import |

---

## What’s next (after data is in Supabase)

1. Wire `index.html` to fetch `icbc_site_sidebar` + `icbc_site_stats_summary` by site slug.
2. Deploy static site to GitHub Pages.
3. Keep using **Seed Admin** locally → re-export CSVs → re-import when you bulk-update data.

---

## File checklist

| File | When to run / import |
|------|----------------------|
| `schema.sql` | Once — SQL Editor |
| `programmes_setup.sql` | Only if upgrading an old DB |
| `seed/icbc_sites.csv` | Table Editor → `icbc_sites` |
| `seed/bubele_care_sites.csv` | Table Editor → `bubele_care_sites` |
| `seed/staff.csv` | Table Editor → `staff_import` |
| `seed/preschool_snapshots.csv` | → `preschool_snapshots_import` |
| `seed/ploughing_records.csv` | → `ploughing_records_import` |
| `seed/maize_buyback_records.csv` | → `maize_buyback_records_import` |
| `process_all_site_imports()` | SQL Editor |
| `weekly_stats_setup.sql` | Once — SQL Editor |
| `seed/weekly_stats.csv` | → `weekly_stats_import` |
| `process_weekly_stats_import()` | SQL Editor |
| `weekly_stats_sidebar_view.sql` | Once — SQL Editor |
