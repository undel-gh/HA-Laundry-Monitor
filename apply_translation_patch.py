"""Add Cycle Statistics entity translations without replacing other keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRANSLATIONS = Path(
    "custom_components/laundry_monitor/translations"
)

PATCHES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "sensor": {
            "current_cycle_duration": "Current cycle duration",
            "last_cycle_duration": "Last cycle duration",
            "last_cycle_energy": "Last cycle energy",
        },
        "binary_sensor": {
            "final_spin_detected": "Final spin detected",
        },
    },
    "ru": {
        "sensor": {
            "current_cycle_duration": "Длительность текущего цикла",
            "last_cycle_duration": "Длительность последнего цикла",
            "last_cycle_energy": "Энергия последнего цикла",
        },
        "binary_sensor": {
            "final_spin_detected": "Обнаружен финальный отжим",
        },
    },
}


def _entity_section(
    document: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    """Return one mutable entity translation section."""
    entity = document.setdefault("entity", {})
    if not isinstance(entity, dict):
        raise TypeError("Top-level 'entity' must be an object")

    section = entity.setdefault(platform, {})
    if not isinstance(section, dict):
        raise TypeError(f"entity.{platform} must be an object")
    return section


def main() -> None:
    """Patch both complete translation files idempotently."""
    for language, platform_patches in PATCHES.items():
        path = TRANSLATIONS / f"{language}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise TypeError(f"{path} must contain a JSON object")

        for platform, names in platform_patches.items():
            section = _entity_section(document, platform)
            for key, name in names.items():
                item = section.setdefault(key, {})
                if not isinstance(item, dict):
                    raise TypeError(
                        f"entity.{platform}.{key} must be an object"
                    )
                item["name"] = name

        path.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Patched {path}")


if __name__ == "__main__":
    main()
