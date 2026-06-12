#!/usr/bin/env python3
"""Scan tracked project files for leaked secrets before commit/push."""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
}

SKIP_FILES = {
    ".streamlit/secrets.toml",
    "scripts/check_secrets.py",
    "SECURITY.md",
    "supabase/IMPORT_WALKTHROUGH.md",
}

TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".toml",
    ".json",
    ".csv",
    ".sql",
    ".bat",
    ".txt",
    ".yml",
    ".yaml",
    ".example",
}

# service_role JWT payload contains this role string
SERVICE_ROLE_RE = re.compile(r'"role"\s*:\s*"service_role"')
ASSIGN_SERVICE_KEY_RE = re.compile(
    r"SUPABASE_SERVICE_ROLE_KEY\s*=\s*['\"](?!your-service-role-key)[^'\"]{20,}",
    re.IGNORECASE,
)
GITHUB_TOKEN_RE = re.compile(r"ghp_[A-Za-z0-9]{20,}")
GENERIC_BEARER_RE = re.compile(r"Bearer\s+eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel in SKIP_FILES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            "Dockerfile",
            "Makefile",
        }:
            continue
        files.append(path)
    return files


def jwt_role(path: Path, token: str) -> str | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    pad = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except (json.JSONDecodeError, ValueError):
        return None
    return str(data.get("role", "")) or None


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []

    if SERVICE_ROLE_RE.search(text):
        issues.append(f"{rel}: contains service_role JWT payload")

    if ASSIGN_SERVICE_KEY_RE.search(text):
        issues.append(f"{rel}: SUPABASE_SERVICE_ROLE_KEY looks like a real value")

    if GITHUB_TOKEN_RE.search(text):
        issues.append(f"{rel}: possible GitHub personal access token (ghp_)")

    for match in re.finditer(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", text):
        token = match.group(0)
        role = jwt_role(path, token)
        if role == "service_role":
            issues.append(f"{rel}: service_role JWT token")

    if GENERIC_BEARER_RE.search(text) and "anon" not in text.lower():
        # Heuristic only; anon keys in index.html are expected
        if "service" in text.lower():
            issues.append(f"{rel}: suspicious Bearer JWT near 'service'")

    return issues


def main() -> int:
    all_issues: list[str] = []
    for path in iter_files():
        all_issues.extend(scan_file(path))

    if all_issues:
        print("SECRET SCAN FAILED — do not push until these are fixed:\n", file=sys.stderr)
        for issue in all_issues:
            print(f"  - {issue}", file=sys.stderr)
        print(
            "\nMove secrets to .streamlit/secrets.toml (gitignored). "
            "Rotate any key that was committed.",
            file=sys.stderr,
        )
        return 1

    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
