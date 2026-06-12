# Security

## What must stay private

| Secret | Where it lives | Never commit? |
|--------|----------------|---------------|
| **Supabase service_role key** | `.streamlit/secrets.toml` (local only) | **Yes** — full database write access |
| GitHub personal access token (if used) | OS credential manager / `gh auth` | **Yes** |
| Django `SECRET_KEY` (if you deploy the backend) | Environment variable | **Yes** |

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste your **service_role** key there. That file is listed in `.gitignore`.

## What is public in this repo (by design)

The **map** (`index.html` on GitHub Pages) uses the Supabase **anon** key in the browser. That is normal for static sites: the anon key is not a secret; **Row Level Security (RLS)** and table grants in Supabase must restrict what it can read or write.

- Do **not** put the **service_role** key in `index.html`, JavaScript, or any committed file.
- Run **Streamlit Seed Admin** only on your machine; it uses the service role locally to sync CSV seed data to Supabase.

## Before every push

```bash
python scripts/check_secrets.py
```

This blocks commits/pushes if a service-role JWT or other sensitive patterns appear in tracked files.

## If a secret was ever committed

1. **Rotate** the key immediately in Supabase (Project Settings → API) and GitHub (Settings → Developer settings).
2. Remove it from history (e.g. `git filter-repo`) or treat the old key as compromised.
3. Re-run `check_secrets.py` before pushing again.

## Streamlit → GitHub + Supabase workflow

1. Edit data in **Seed Admin** locally (`run_seed_admin.bat`).
2. CSV changes live under `supabase/seed/` — commit those with `git` (no secrets in CSVs).
3. Enable **Sync to Supabase on save** only when `.streamlit/secrets.toml` is configured.
4. Push to GitHub when ready; GitHub Pages serves the static map only (no server-side secrets).

## GitHub repository settings (recommended)

On the new repo, enable:

- **Secret scanning** (Settings → Code security)
- **Dependabot alerts** (Settings → Code security)
- Branch protection on `main` (optional): require PR reviews before merge
