#!/usr/bin/env python3
"""Add last_unloaded_at entity translations without replacing JSON files."""

from __future__ import annotations

import json
from pathlib import Path

TRANSLATIONS = {
    "en": "Last unloaded at",
    "ru": "Последняя выгрузка белья",
}

base = Path("custom_components/laundry_monitor/translations")

for language, name in TRANSLATIONS.items():
    path = base / f"{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sensors = data.setdefault("entity", {}).setdefault("sensor", {})
    sensors["last_unloaded_at"] = {"name": name}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {path}")
