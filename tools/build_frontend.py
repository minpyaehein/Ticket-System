#!/usr/bin/env python3
"""Rebuild js/app.js from the ordered source modules in js/modules/."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "00-app-shell.js",
    "10-form-controls.js",
    "20-records-dashboard.js",
    "30-ticket-workflows.js",
    "40-settings-admin.js",
    "90-page-initialization.js",
]

source_dir = PROJECT_ROOT / "js" / "modules"
output_file = PROJECT_ROOT / "js" / "app.js"
output = "".join((source_dir / name).read_text(encoding="utf-8") for name in MODULES)
with output_file.open("w", encoding="utf-8", newline="") as output_stream:
    output_stream.write(output)
print(f"Built {output_file.relative_to(PROJECT_ROOT)} from {len(MODULES)} source modules.")
