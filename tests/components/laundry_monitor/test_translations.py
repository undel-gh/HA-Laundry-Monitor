"""Test Laundry Monitor translation files."""

from pathlib import Path
import json


COMPONENT_DIR = (
    Path(__file__).parents[3]
    / "custom_components"
    / "laundry_monitor"
)


def _leaf_paths(value: object, prefix: str = "") -> set[str]:
    """Return all leaf paths in a nested JSON-compatible value."""
    if not isinstance(value, dict):
        return {prefix}

    paths: set[str] = set()
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else key
        paths.update(_leaf_paths(child, child_prefix))
    return paths


def test_translation_files_are_valid_and_complete() -> None:
    """Test that translations are valid JSON and have matching keys."""
    strings = json.loads(
        (COMPONENT_DIR / "strings.json").read_text(encoding="utf-8")
    )
    english = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(
            encoding="utf-8"
        )
    )
    russian = json.loads(
        (COMPONENT_DIR / "translations" / "ru.json").read_text(
            encoding="utf-8"
        )
    )

    assert english == strings
    assert _leaf_paths(russian) == _leaf_paths(english)
