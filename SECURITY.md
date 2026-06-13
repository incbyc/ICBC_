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

## GitHub repository settings (recommended)

On **https://github.com/incbyc/ICBC_** → Settings:

### Protect your code (who can change `main`)

1. **Settings → Collaborators** — only add people who need write access.
2. **Settings → Branches → Branch protection rules** → Add rule for `main`:
   - Require a pull request before merging (recommended if others contribute).
   - Require status checks to pass — select **Secret scan** (from `.github/workflows/secret-scan.yml`).
   - Do not allow bypassing the rule (including admins), if you want maximum safety.
3. **Settings → General → Pull Requests** — enable “Allow squash merging” if you prefer clean history.

### Protect secrets and dependencies

4. **Settings → Code security and analysis** — enable:
   - **Secret scanning** (alerts if keys are pushed).
   - **Push protection** (blocks pushes that contain known secret patterns).
   - **Dependabot alerts** and **Dependabot security updates** (works with `.github/dependabot.yml`).
5. **Settings → Actions → General** — “Workflow permissions”: read-only unless a workflow needs write access.

### Your account

6. Enable **two-factor authentication (2FA)** on your GitHub account (Settings → Password and authentication).
7. Store Supabase **service_role** only in `.streamlit/secrets.toml` on your PC — never in GitHub Secrets for this static site unless you add a trusted CI deploy that needs it.

### Supabase (database)

8. **Project Settings → API** — confirm only the **anon** key is in `index.html`; rotate **service_role** if it was ever committed.
9. **Authentication → Policies** — RLS in `supabase/schema.sql` allows public **SELECT** only; writes go through Seed Admin with service_role locally.
10. **Storage** — staff photo bucket should allow public read, not public write (see `supabase/storage_setup.sql`).

## Before every push

```bash
python scripts/check_secrets.py
```

This blocks commits/pushes if a service-role JWT or other sensitive patterns appear in tracked files. CI runs the same check on every push to `main`.

## If a secret was ever committed

1. **Rotate** the key immediately in Supabase (Project Settings → API) and GitHub (Settings → Developer settings).
2. Remove it from history (e.g. `git filter-repo`) or treat the old key as compromised.
3. Re-run `check_secrets.py` before pushing again.

## Streamlit → GitHub + Supabase workflow

1. Edit data in **Seed Admin** locally (`run_seed_admin.bat`).
2. CSV changes live under `supabase/seed/` — commit those with `git` (no secrets in CSVs).
3. Enable **Sync to Supabase on save** only when `.streamlit/secrets.toml` is configured.
4. Push to GitHub when ready; GitHub Pages serves the static map only (no server-side secrets).
5. Keep raw Word profiles in `Profiles/` locally — that folder is gitignored; use `scripts/extract_icbc_profiles.py` to update seed CSVs.
