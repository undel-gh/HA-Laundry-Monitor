"""Regression tests for the GitHub Release metadata preflight."""

import json
from pathlib import Path

import pytest

from scripts.verify_release import main, validate_release


CHANGELOG_RC = "# Changelog\n\n## [0.1.8-rc8] - 2026-11-12\n\n- Fixes\n"
CHANGELOG_STABLE = "# Changelog\n\n## [0.1.8] - 2026-11-12\n\n- Fixes\n"
NOTES = "Release candidate with fixes and documented upgrade guidance."


def test_valid_rc_release() -> None:
    """A properly marked prerelease with matching manifest and notes passes."""
    assert validate_release("0.1.8-rc8", True, "0.1.8-rc8", CHANGELOG_RC, NOTES) == []


def test_valid_stable_release() -> None:
    """Stable versions must be marked non-prerelease."""
    assert validate_release("0.1.8", False, "0.1.8", CHANGELOG_STABLE, NOTES) == []


def test_reject_rc_marked_stable() -> None:
    errors = validate_release("0.1.8-rc8", False, "0.1.8-rc8", CHANGELOG_RC, NOTES)
    assert any("prerelease=true" in error for error in errors)


def test_reject_stable_marked_prerelease() -> None:
    errors = validate_release("0.1.8", True, "0.1.8", CHANGELOG_STABLE, NOTES)
    assert any("prerelease=false" in error for error in errors)


def test_reject_tag_manifest_mismatch() -> None:
    errors = validate_release("0.1.8-rc8", True, "0.1.8-rc7", CHANGELOG_RC, NOTES)
    assert any("does not match tag" in error for error in errors)


def test_reject_missing_changelog_entry() -> None:
    errors = validate_release("0.1.8-rc8", True, "0.1.8-rc8", "# Changelog", NOTES)
    assert any("dated heading" in error for error in errors)


def test_reject_invalid_changelog_date() -> None:
    bad = "## [0.1.8-rc8] - 2026-02-31\n"
    errors = validate_release("0.1.8-rc8", True, "0.1.8-rc8", bad, NOTES)
    assert any("invalid date" in error for error in errors)


def test_reject_empty_release_notes() -> None:
    errors = validate_release("0.1.8-rc8", True, "0.1.8-rc8", CHANGELOG_RC, "  ")
    assert any("notes" in error.lower() for error in errors)


def test_reject_v_prefixed_or_unknown_tag_format() -> None:
    errors = validate_release("v0.1.8-rc8", True, "v0.1.8-rc8", "# Changelog", NOTES)
    assert any("without a v prefix" in error for error in errors)


def _cli_args(
    tmp_path: Path,
    *,
    tag: str = "0.1.8-rc8",
    manifest_version: str = "0.1.8-rc8",
    prerelease: str = "true",
    changelog: str = CHANGELOG_RC,
    notes: str = NOTES,
) -> list[str]:
    """Write isolated release metadata and return the CLI argument vector."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps({"version": manifest_version}), encoding="utf-8"
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(changelog, encoding="utf-8")
    notes_file = tmp_path / "notes.md"
    notes_file.write_text(notes, encoding="utf-8")
    return [
        "--tag", tag,
        "--prerelease", prerelease,
        "--manifest", str(manifest_file),
        "--changelog", str(changelog_file),
        "--notes-file", str(notes_file),
    ]


@pytest.mark.parametrize(
    ("tag", "manifest_version", "prerelease", "changelog"),
    [
        ("0.1.8-rc8", "0.1.8-rc8", "true", CHANGELOG_RC),
        ("0.1.8", "0.1.8", "false", CHANGELOG_STABLE),
    ],
)
def test_main_accepts_valid_release_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    tag: str,
    manifest_version: str,
    prerelease: str,
    changelog: str,
) -> None:
    """The CLI loads real files and exits successfully for both channels."""
    argv = _cli_args(
        tmp_path,
        tag=tag,
        manifest_version=manifest_version,
        prerelease=prerelease,
        changelog=changelog,
    )
    assert main(argv) == 0
    output = capsys.readouterr().out
    assert f"Release metadata OK: {tag}" in output


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"manifest_version": "0.1.8-rc7"}, "does not match tag"),
        ({"notes": "  "}, "notes must not be empty"),
        ({"changelog": "# Changelog"}, "dated heading"),
        ({"prerelease": "false"}, "prerelease=true"),
    ],
)
def test_main_returns_failure_for_invalid_release_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, str],
    message: str,
) -> None:
    """The CLI reports semantic errors and returns a nonzero exit status."""
    assert main(_cli_args(tmp_path, **overrides)) == 1
    assert message in capsys.readouterr().out


@pytest.mark.parametrize("invalid_content", ["not json", "{}"])
def test_main_handles_invalid_or_missing_manifest_version(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    invalid_content: str,
) -> None:
    """Malformed JSON and missing version fail gracefully, not with a traceback."""
    argv = _cli_args(tmp_path)
    (tmp_path / "manifest.json").write_text(
        invalid_content, encoding="utf-8"
    )
    assert main(argv) == 1
    assert "Release preflight failed to load metadata" in capsys.readouterr().out


def test_main_handles_missing_input_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unreadable input path results in exit code 1."""
    argv = _cli_args(tmp_path)
    (tmp_path / "notes.md").unlink()
    assert main(argv) == 1
    assert "Release preflight failed to load metadata" in capsys.readouterr().out


@pytest.mark.parametrize(
    "bad_arguments",
    [
        ["--tag", "0.1.8-rc8", "--prerelease", "true"],
        ["--tag", "0.1.8-rc8", "--prerelease", "maybe"],
    ],
)
def test_main_rejects_missing_or_invalid_cli_arguments(
    bad_arguments: list[str],
) -> None:
    """argparse rejects absent required options and invalid prerelease flags."""
    with pytest.raises(SystemExit) as exc:
        main(bad_arguments)
    assert exc.value.code == 2
