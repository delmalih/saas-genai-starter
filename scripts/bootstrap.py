#!/usr/bin/env python3
"""Rebrand the starter into your product — see BOOTSTRAP.md.

Reads the current identity from bootstrap.config.json, replaces every
occurrence across git-tracked text files with the values you provide, then
updates the manifest so the operation stays repeatable.

Usage (flags, or interactive when omitted):
    python3 scripts/bootstrap.py --name "Acme Notes" --slug acme-notes \
        --tagline "..." --description "..." --github-repo acme/acme-notes
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "bootstrap.config.json"

# Generated or vendored files where replacements would be overwritten or noisy.
SKIP_SUFFIXES = (".lock", ".svg", ".png", ".ico", ".jsonl")
SKIP_PARTS = ("node_modules", ".next", "__pycache__", ".terraform", "results")
SKIP_FILES = ("pnpm-lock.yaml", "uv.lock", "bootstrap.config.json")

FIELDS = {
    "productName": ("--name", "Product name (e.g. Acme Notes)"),
    "slug": ("--slug", "Slug, kebab-case (e.g. acme-notes)"),
    "tagline": ("--tagline", "Landing page tagline"),
    "description": ("--description", "One-sentence description (meta/README)"),
    "githubRepo": ("--github-repo", "GitHub repository (owner/name)"),
}


def tracked_text_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    files = []
    for line in output.splitlines():
        path = ROOT / line
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES or path.name in SKIP_FILES:
            continue
        if path.is_file():
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field, (flag, help_text) in FIELDS.items():
        parser.add_argument(flag, dest=field, help=help_text)
    args = parser.parse_args()

    current = json.loads(MANIFEST.read_text())
    target: dict[str, str] = {}
    for field, (flag, prompt) in FIELDS.items():
        value = getattr(args, field) or input(f"{prompt} [{current[field]}]: ").strip()
        target[field] = value or current[field]

    if " " in target["slug"]:
        print("error: the slug must not contain spaces", file=sys.stderr)
        return 1

    # Longest-first so the repo path doesn't eat the bare slug, and the
    # underscore variant (python module-ish contexts) comes along.
    replacements = [
        (current["githubRepo"], target["githubRepo"]),
        (current["description"], target["description"]),
        (current["tagline"], target["tagline"]),
        (current["productName"], target["productName"]),
        (current["slug"].replace("-", "_"), target["slug"].replace("-", "_")),
        (current["slug"], target["slug"]),
    ]
    replacements = [(old, new) for old, new in replacements if old != new]
    if not replacements:
        print("Nothing to do — all values unchanged.")
        return 0

    changed = 0
    for path in tracked_text_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        updated = text
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated)
            changed += 1
            print(f"  rewrote {path.relative_to(ROOT)}")

    manifest = {k: v for k, v in current.items() if k == "$comment"}
    manifest.update(target)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\n{changed} files rewritten. Now run the gates:")
    print("  make generate-client && make lint && make test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
