"""Test Laundry Monitor translation files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


COMPONENT_DIR = (
    Path(__file__).resolve().parents[3]
    / "custom_components"
    / "laundry_monitor"
)
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"
REFERENCE_LANGUAGE = "en"


def _load_translation(language: str) -> dict[str, Any]:
    """Load and validate a translation JSON file."""
    path = TRANSLATIONS_DIR / f"{language}.json"

    assert path.is_file(), f"Missing translation file: {path}"

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    assert isinstance(data, dict), (
        f"Translation file {path.name} must contain a JSON object"
    )
    return data


def _leaf_paths(value: Any, prefix: str = "") -> set[str]:
    """Return dotted paths for all leaf values in a nested mapping."""
    if not isinstance(value, dict):
        return {prefix}

    paths: set[str] = set()

    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else key
        paths.update(_leaf_paths(child, child_prefix))

    return paths


def _leaf_values(value: Any) -> list[Any]:
    """Return all leaf values from a nested mapping."""
    if not isinstance(value, dict):
        return [value]

    values: list[Any] = []

    for child in value.values():
        values.extend(_leaf_values(child))

    return values


def _translation_languages() -> list[str]:
    """Return all available translation language codes."""
    return sorted(path.stem for path in TRANSLATIONS_DIR.glob("*.json"))


def test_english_translation_exists() -> None:
    """Test that the required English translation is present."""
    assert (TRANSLATIONS_DIR / "en.json").is_file()


@pytest.mark.parametrize("language", _translation_languages())
def test_translation_file_is_valid(language: str) -> None:
    """Test that every translation file is valid JSON."""
    _load_translation(language)


@pytest.mark.parametrize(
    "language",
    [
        language
        for language in _translation_languages()
        if language != REFERENCE_LANGUAGE
    ],
)
def test_translation_keys_match_english(language: str) -> None:
    """Test that translated files contain exactly the English keys."""
    english = _load_translation(REFERENCE_LANGUAGE)
    translated = _load_translation(language)

    english_paths = _leaf_paths(english)
    translated_paths = _leaf_paths(translated)

    missing = english_paths - translated_paths
    unexpected = translated_paths - english_paths

    assert not missing, (
        f"{language}.json is missing translation keys: "
        f"{sorted(missing)}"
    )
    assert not unexpected, (
        f"{language}.json contains unexpected translation keys: "
        f"{sorted(unexpected)}"
    )


@pytest.mark.parametrize("language", _translation_languages())
def test_translation_leaf_values_are_non_empty_strings(
    language: str,
) -> None:
    """Test that all translation leaf values are non-empty strings."""
    translation = _load_translation(language)

    for value in _leaf_values(translation):
        assert isinstance(value, str), (
            f"{language}.json contains a non-string translation value: "
            f"{value!r}"
        )
        assert value.strip(), (
            f"{language}.json contains an empty translation string"
        )


@pytest.mark.parametrize("language", _translation_languages())
def test_translation_files_do_not_use_core_key_references(
    language: str,
) -> None:
    """Test that custom integration translations contain no key references."""
    translation = _load_translation(language)

    for value in _leaf_values(translation):
        assert "[%key:" not in value, (
            f"{language}.json contains an unsupported Home Assistant Core "
            f"translation reference: {value!r}"
        )


def test_no_strings_json_is_present() -> None:
    """Test that the custom integration does not ship strings.json."""
    assert not (COMPONENT_DIR / "strings.json").exists(), (
        "Custom integrations must keep complete translations in "
        "translations/en.json and must not ship strings.json"
    )
