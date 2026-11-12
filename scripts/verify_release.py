"""Read-only preflight for Laundry Monitor GitHub Releases.

This checks metadata at the tagged commit; it never creates or edits releases.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-rc[1-9]\d*)?\Z")


def validate_release(
    tag: str,
    prerelease: bool,
    manifest_version: str,
    changelog: str,
    notes: str,
) -> list[str]:
    """Return release contract violations without modifying repository files."""
    errors: list[str] = []

    if _VERSION.fullmatch(tag) is None:
        errors.append(
            "Release tag must be X.Y.Z or X.Y.Z-rcN, without a v prefix."
        )
    else:
        is_rc = "-rc" in tag
        if is_rc != prerelease:
            errors.append(
                "RC tags require prerelease=true; stable tags require "
                "prerelease=false."
            )

    if manifest_version != tag:
        errors.append(
            f"Manifest version {manifest_version!r} does not match tag {tag!r}."
        )

    heading = re.search(
        rf"(?m)^## \[{re.escape(tag)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\s*$",
        changelog,
    )
    if heading is None:
        errors.append(
            f"CHANGELOG.md needs a dated heading: ## [{tag}] - YYYY-MM-DD."
        )
    else:
        try:
            date.fromisoformat(heading.group(1))
        except ValueError:
            errors.append("CHANGELOG.md release heading has an invalid date.")

    if not notes.strip():
        errors.append("GitHub Release notes must not be empty.")

    return errors


def main(argv: list[str] | None = None) -> int:
    """Check a proposed or already published release against repository files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--prerelease", required=True, choices=("true", "false"))
    parser.add_argument("--notes-file", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("custom_components/laundry_monitor/manifest.json"),
    )
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    args = parser.parse_args(argv)

    try:
        manifest_version = json.loads(
            args.manifest.read_text(encoding="utf-8")
        )["version"]
        changelog = args.changelog.read_text(encoding="utf-8")
        notes = args.notes_file.read_text(encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(f"Release preflight failed to load metadata: {exc}")
        return 1

    errors = validate_release(
        tag=args.tag,
        prerelease=args.prerelease == "true",
        manifest_version=manifest_version,
        changelog=changelog,
        notes=notes,
    )
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1

    print(f"Release metadata OK: {args.tag} (prerelease={args.prerelease})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
