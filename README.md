# ICBC Eswatini Map

Interactive map of ICBC sites, Challenge Ministries overview, and Bubele Care families. Data is stored in **Supabase**; seed CSVs are edited locally with **Streamlit Seed Admin**.

## Quick start

### Map (GitHub Pages or local)

Open `index.html` over HTTP (not `file://`) so YouTube embeds and Supabase work:

```bash
npx serve .
```

### Seed Admin (local only)

```bash
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# Edit secrets.toml — add your Supabase service_role key (never commit this file)

pip install -r requirements.txt
run_seed_admin.bat
```

See [SECURITY.md](SECURITY.md) for which keys are safe to publish vs. must stay local.

## Project layout

| Path | Purpose |
|------|---------|
| `index.html` | Main map UI |
| `supabase/seed/*.csv` | Source data synced to Supabase |
| `seed_admin_app.py` | Streamlit admin for CSV + media |
| `scripts/` | Import/sync helpers |
| `data/` | GeoJSON/JS layers for the map |

## Supabase setup

SQL scripts under `supabase/` — run in the Supabase SQL Editor as described in `supabase/README.md` and `supabase/IMPORT_WALKTHROUGH.md`.

## Push to GitHub

```bash
python scripts/check_secrets.py
git add -A
git commit -m "Your message"
git push
```
