"""Regression tests for the GitHub Release metadata preflight."""

from scripts.verify_release import validate_release


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
