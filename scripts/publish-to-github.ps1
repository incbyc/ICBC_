# Publish this project to a new GitHub repository (run from project root).
# Prerequisites: GitHub CLI logged in (gh auth login) and Python 3.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python scripts/check_secrets.py
if ($LASTEXITCODE -ne 0) { exit 1 }

gh auth status
if ($LASTEXITCODE -ne 0) {
    Write-Host "Run: gh auth login" -ForegroundColor Yellow
    exit 1
}

$repoName = "icbc-eswatini-map"
if ($args.Count -ge 1) { $repoName = $args[0] }

$visibility = "public"
if ($args -contains "--private") { $visibility = "private" }

Write-Host "Creating GitHub repo: $repoName ($visibility)" -ForegroundColor Cyan

if (git remote get-url origin 2>$null) {
    git remote rename origin incbyc-legacy 2>$null
}

gh repo create $repoName --$visibility --source=. --remote=origin --push --description "ICBC Eswatini interactive map and Supabase seed admin"

Write-Host "Done. Enable GitHub Pages: Settings -> Pages -> Deploy from branch main, folder / (root)." -ForegroundColor Green
