#!/usr/bin/env python3
"""Apply targeted heated-cycle terminal-spin correlation hardening.

Run from the HA-Laundry-Monitor repository root.

Preview:
    python apply_terminal_spin_hardening.py

Apply:
    python apply_terminal_spin_hardening.py --apply

The script is deliberately strict: every expected source fragment must match
exactly once (or already contain the replacement), otherwise it aborts.
"""

from __future__ import annotations

import argparse
import difflib
import json
import py_compile
import tempfile
from pathlib import Path


def replace_once(text: str, old: str, new: str, *, path: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one match, got {count}: {old[:120]!r}"
        )
    return text.replace(old, new, 1)


def replace_if_present(text: str, old: str, new: str) -> str:
    if new in text:
        return text
    if old in text:
        return text.replace(old, new, 1)
    return text


def insert_before_one_of(
    text: str,
    anchors: tuple[str, ...],
    addition: str,
    *,
    path: str,
) -> str:
    """Insert before the first unique anchor from a small approved set."""
    matches = [(anchor, text.count(anchor)) for anchor in anchors]
    for anchor, count in matches:
        if count == 1:
            return text.replace(anchor, addition + anchor, 1)
    raise RuntimeError(
        f"{path}: no unique insertion anchor found: {matches!r}"
    )


def insert_before_heading_prefix(
    text: str,
    heading_prefix: str,
    addition: str,
    *,
    path: str,
) -> str:
    """Insert before one uniquely matching Markdown heading prefix."""
    lines = text.splitlines(keepends=True)
    indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith(heading_prefix)
    ]
    if len(indexes) != 1:
        raise RuntimeError(
            f"{path}: expected one heading starting {heading_prefix!r}, "
            f"got {len(indexes)}"
        )
    index = indexes[0]
    lines.insert(index, addition)
    return "".join(lines)






def transform_const(text: str) -> str:
    path = "custom_components/laundry_monitor/const.py"
    text = replace_once(
        text,
        'DEFAULT_HYBRID_SPIN_REQUIRED_EVENTS: Final = 2\n'
        'DEFAULT_FINISH_CONFIRMATION: Final = 180',
        'DEFAULT_HYBRID_SPIN_REQUIRED_EVENTS: Final = 2\n'
        '# Experimental heated-cycle terminal-profile hardening.\n'
        'HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION: Final = 45\n'
        'DEFAULT_FINISH_CONFIRMATION: Final = 180',
        path=path,
    )
    return text

def transform_spin(text: str) -> str:
    path = "custom_components/laundry_monitor/spin.py"
    text = replace_once(
        text,
        '    new_evidence: bool\n'
        '    activity_recent: bool\n'
        '    cycle_mature: bool',
        '    new_evidence: bool\n'
        '    latest_evidence_at: datetime | None\n'
        '    activity_recent: bool\n'
        '    cycle_mature: bool',
        path=path,
    )
    text = replace_once(
        text,
        '            evidence_count=evidence_count,\n'
        '            new_evidence=new_evidence,\n'
        '            activity_recent=activity_recent,',
        '            evidence_count=evidence_count,\n'
        '            new_evidence=new_evidence,\n'
        '            latest_evidence_at=(\n'
        '                self._evidence[-1] if self._evidence else None\n'
        '            ),\n'
        '            activity_recent=activity_recent,',
        path=path,
    )
    text = replace_once(
        text,
        '    def _prune(self, now: datetime) -> None:\n',
        '    @property\n'
        '    def latest_evidence_at(self) -> datetime | None:\n'
        '        """Return the newest currently retained vibration edge."""\n'
        '        return self._evidence[-1] if self._evidence else None\n\n'
        '    def _prune(self, now: datetime) -> None:\n',
        path=path,
    )
    return text


def transform_runtime(text: str) -> str:
    path = "custom_components/laundry_monitor/runtime.py"
    text = replace_once(
        text,
        '    EVENT_TRANSITION_REJECTED,\n    LaundryCycleState,',
        '    EVENT_TRANSITION_REJECTED,\n'
        '    HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION,\n'
        '    LaundryCycleState,',
        path=path,
    )
    text = replace_once(
        text,
        '    @property\n    def current_cycle_duration(self) -> float | None:\n',
        '    @property\n'
        '    def spin_electrical_candidate_age_seconds(self) -> float | None:\n'
        '        """Return how long the current electrical candidate has lived."""\n'
        '        if (\n'
        '            not self.spin_electrical_candidate\n'
        '            or self.spin_electrical_candidate_since is None\n'
        '        ):\n'
        '            return None\n'
        '        return round(\n'
        '            max(\n'
        '                (\n'
        '                    dt_util.utcnow()\n'
        '                    - self.spin_electrical_candidate_since\n'
        '                ).total_seconds(),\n'
        '                0.0,\n'
        '            ),\n'
        '            1,\n'
        '        )\n\n'
        '    @property\n'
        '    def heated_electrical_candidate_min_duration_seconds(self) -> int:\n'
        '        """Return the heated-cycle electrical maturity requirement."""\n'
        '        return HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n\n'
        '    def _heated_electrical_candidate_is_mature(\n'
        '        self,\n'
        '        now: datetime,\n'
        '    ) -> bool:\n'
        '        """Return whether the current candidate survived the maturity gate."""\n'
        '        since = self.spin_electrical_candidate_since\n'
        '        return bool(\n'
        '            self.spin_electrical_candidate\n'
        '            and since is not None\n'
        '            and now - since\n'
        '            >= timedelta(\n'
        '                seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n'
        '            )\n'
        '        )\n\n'
        '    @property\n'
        '    def current_cycle_duration(self) -> float | None:\n',
        path=path,
    )
    text = replace_once(
        text,
        '                if cycle_age < effective_min:\n'
        '                    gate_reason = "heated_cycle_too_young"\n'
        '                else:\n'
        '                    confirmation_path = "hybrid"\n'
        '                    hybrid_variant = "reduced"\n'
        '                    gate_reason = "confirmed_hybrid_reduced"',
        '                if cycle_age < effective_min:\n'
        '                    gate_reason = "heated_cycle_too_young"\n'
        '                elif not self._heated_electrical_candidate_is_mature(\n'
        '                    timestamp\n'
        '                ):\n'
        '                    gate_reason = "heated_electrical_candidate_immature"\n'
        '                elif (\n'
        '                    self.spin_electrical_candidate_since is None\n'
        '                    or evaluation.latest_evidence_at is None\n'
        '                    or evaluation.latest_evidence_at\n'
        '                    < self.spin_electrical_candidate_since\n'
        '                ):\n'
        '                    gate_reason = (\n'
        '                        "heated_cycle_requires_fresh_vibration_"\n'
        '                        "after_electrical_candidate"\n'
        '                    )\n'
        '                else:\n'
        '                    confirmation_path = "hybrid"\n'
        '                    hybrid_variant = "reduced"\n'
        '                    gate_reason = "confirmed_hybrid_reduced"',
        path=path,
    )
    text = replace_once(
        text,
        '                    "electrical_candidate": self.spin_electrical_candidate,\n'
        '                    "power_rolling_median": self.spin_power_rolling_median,',
        '                    "electrical_candidate": self.spin_electrical_candidate,\n'
        '                    "electrical_candidate_since": (\n'
        '                        self.spin_electrical_candidate_since.isoformat()\n'
        '                        if self.spin_electrical_candidate_since is not None\n'
        '                        else None\n'
        '                    ),\n'
        '                    "electrical_candidate_age_seconds": (\n'
        '                        self.spin_electrical_candidate_age_seconds\n'
        '                    ),\n'
        '                    "heated_candidate_min_duration_seconds": (\n'
        '                        self.heated_electrical_candidate_min_duration_seconds\n'
        '                    ),\n'
        '                    "latest_vibration_evidence_at": (\n'
        '                        evaluation.latest_evidence_at.isoformat()\n'
        '                        if evaluation.latest_evidence_at is not None\n'
        '                        else None\n'
        '                    ),\n'
        '                    "power_rolling_median": self.spin_power_rolling_median,',
        path=path,
    )
    return text

def transform_diagnostics(text: str) -> str:
    path = "custom_components/laundry_monitor/diagnostics.py"
    text = replace_once(
        text,
        '                "evidence_count": (\n'
        '                    runtime.final_spin_evidence_count\n'
        '                ),\n'
        '                "confirmation_path": runtime.final_spin_confirmation_path,',
        '                "evidence_count": (\n'
        '                    runtime.final_spin_evidence_count\n'
        '                ),\n'
        '                "latest_vibration_evidence_at": _serialize_datetime(\n'
        '                    runtime.spin_detector.latest_evidence_at\n'
        '                ),\n'
        '                "confirmation_path": runtime.final_spin_confirmation_path,',
        path=path,
    )
    text = replace_once(
        text,
        '                    "candidate_since": _serialize_datetime(\n'
        '                        runtime.spin_electrical_candidate_since\n'
        '                    ),\n'
        '                    "window_seconds": (',
        '                    "candidate_since": _serialize_datetime(\n'
        '                        runtime.spin_electrical_candidate_since\n'
        '                    ),\n'
        '                    "candidate_age_seconds": (\n'
        '                        runtime.spin_electrical_candidate_age_seconds\n'
        '                    ),\n'
        '                    "heated_min_duration_seconds": (\n'
        '                        runtime.heated_electrical_candidate_min_duration_seconds\n'
        '                    ),\n'
        '                    "window_seconds": (',
        path=path,
    )
    return text

def transform_test_diagnostics(text: str) -> str:
    return replace_if_present(text, '    device = dr.async_get(hass).async_get_device(\n        identifiers={(DOMAIN, entry.entry_id)}\n    )', '    device_registry = dr.async_get(hass)\n    device = device_registry.async_get_device_by_identifier(\n        (DOMAIN, entry.entry_id),\n        entry.entry_id,\n    )')


def transform_ru_json(text: str) -> str:
    return replace_if_present(text, '          "": "Минимальное время цикла до финального отжима",', '          "spin_min_cycle_time": "Минимальное время цикла до финального отжима",')


def transform_spin_runtime_tests(text: str) -> str:
    path = "tests/components/laundry_monitor/test_spin_runtime.py"
    text = replace_once(
        text,
        '    DOMAIN,\n'
        '    LaundryCycleState,\n'
        '    REASON_FINAL_SPIN_CONFIRMED,',
        '    DOMAIN,\n'
        '    HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION,\n'
        '    LaundryCycleState,\n'
        '    REASON_FINAL_SPIN_CONFIRMED,',
        path=path,
    )
    text = replace_once(
        text,
        '    await _vibration_pulse(hass)\n'
        '    await _vibration_pulse(hass)\n'
        '\n'
        '    assert runtime.cycle_state is LaundryCycleState.RUNNING\n'
        '    assert runtime.spin_gate_reason == "heated_cycle_too_young"\n'
        '\n'
        '    runtime.cycle_started_at = dt_util.utcnow() - timedelta(minutes=16)\n'
        '    assert runtime._evaluate_spin()\n',
        '    assert runtime.spin_electrical_candidate is True\n'
        '    runtime.electrical_spin_detector.candidate_since = (\n'
        '        dt_util.utcnow()\n'
        '        - timedelta(\n'
        '            seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n'
        '        )\n'
        '    )\n'
        '    await _vibration_pulse(hass)\n'
        '    await _vibration_pulse(hass)\n'
        '\n'
        '    assert runtime.cycle_state is LaundryCycleState.RUNNING\n'
        '    assert runtime.spin_gate_reason == "heated_cycle_too_young"\n'
        '\n'
        '    runtime.cycle_started_at = dt_util.utcnow() - timedelta(minutes=16)\n'
        '    assert runtime._evaluate_spin()\n',
        path=path,
    )
    text = replace_once(
        text,
        '    assert runtime.spin_electrical_candidate is True\n'
        '    assert runtime._evaluate_spin(now=candidate_now)\n'
        '    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n'
        '    assert runtime.final_spin_confirmation_path == "hybrid"\n'
        '    assert runtime.final_spin_hybrid_variant == "reduced"\n',
        '    assert runtime.spin_electrical_candidate is True\n'
        '    assert not runtime._evaluate_spin(now=candidate_now)\n'
        '    assert runtime.spin_gate_reason == "heated_electrical_candidate_immature"\n'
        '\n'
        '    mature_now = candidate_now + timedelta(\n'
        '        seconds=HEATED_ELECTRICAL_CANDIDATE_MIN_DURATION\n'
        '    )\n'
        '    assert not runtime._evaluate_spin(now=mature_now)\n'
        '    assert runtime.spin_gate_reason == (\n'
        '        "heated_cycle_requires_fresh_vibration_after_electrical_candidate"\n'
        '    )\n'
        '\n'
        '    runtime.vibration_active = True\n'
        '    assert runtime._evaluate_spin(now=mature_now + timedelta(seconds=1))\n'
        '    runtime.vibration_active = False\n'
        '\n'
        '    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN\n'
        '    assert runtime.final_spin_confirmation_path == "hybrid"\n'
        '    assert runtime.final_spin_hybrid_variant == "reduced"\n',
        path=path,
    )

    recovery_test = """

async def test_snapshot_recovery_requires_new_heated_candidate_correlation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    \"\"\"FR-059/060: restart cannot reuse old electrical maturity.\"\"\"
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
        spin_min_cycle_time=0,
        heated_cycle_min_time=0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    evidence = (
        now - timedelta(seconds=120),
        now - timedelta(seconds=60),
    )
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason=\"stored_running\",
        last_state_change=now - timedelta(seconds=5),
        cycle_started_at=now - timedelta(minutes=20),
        laundry_present=True,
        heating_detected=True,
        heating_detected_at=now - timedelta(minutes=15),
        spin_evidence_timestamps=evidence,
    )
    runtime.state_store.async_get = AsyncMock(return_value=snapshot)

    await runtime._async_restore_snapshot()

    assert runtime.heating_state is HeatingState.DETECTED
    assert runtime.final_spin_evidence_count == 2
    assert runtime.spin_electrical_candidate is False
    assert runtime.spin_electrical_candidate_since is None

    assert not runtime._evaluate_spin(now=now)
    assert runtime.spin_gate_reason == \"heated_cycle_requires_electrical_candidate\"
"""
    anchor = '\n\nasync def test_snapshot_recovery_restores_latched_heating_fact('
    if 'test_snapshot_recovery_requires_new_heated_candidate_correlation' not in text:
        text = replace_once(text, anchor, recovery_test + anchor, path=path)
    return text

def transform_requirements(text: str) -> str:
    path = "docs/en/REQUIREMENTS.md"
    addition = """## FR-059

When hybrid terminal-spin confirmation is enabled and heating has been latched as `detected`, the electrical spin candidate shall not corroborate `final_spin` immediately upon becoming active. It shall first satisfy a minimum maturity duration. The initial experimental implementation uses 45 seconds. This requirement is based on sustained terminal-profile structure rather than a second machine-specific power threshold.

---

## FR-060

For a heated cycle using hybrid confirmation, at least one retained vibration rising edge used for terminal confirmation shall occur at or after the start of the current electrical spin candidate. Vibration evidence accumulated entirely before the current electrical episode shall not be sufficient, even after the candidate becomes mature. The maturity requirement from FR-059 and this temporal-correlation requirement are cumulative.

---

"""
    if '## FR-059\n' not in text:
        text = replace_once(
            text,
            '# Non-Functional Requirements\n',
            addition + '# Non-Functional Requirements\n',
            path=path,
        )
    return text

def transform_state_machine_doc(text: str) -> str:
    path = "docs/en/STATE_MACHINE.md"
    addition = (
        "For heated cycles using hybrid confirmation, the electrical candidate "
        "must also mature for the experimental 45-second minimum, and at least "
        "one retained vibration rising edge must occur at or after the start of "
        "that same electrical candidate. Old vibration evidence from before the "
        "current electrical episode cannot complete heated-cycle confirmation.\n\n"
    )
    if "experimental 45-second minimum" not in text:
        text = insert_before_one_of(
            text,
            (
                "The experimental hybrid detector combines vibration and electrical evidence with heating-aware cycle context.\n",
                "The normal reduced-evidence hybrid path requires:\n",
            ),
            addition,
            path=path,
        )
    return text

def transform_spec(text: str) -> str:
    path = "docs/en/SPECIFICATION.md"
    addition = (
        "For a heated cycle with hybrid confirmation enabled, the electrical "
        "spin candidate must remain active for an experimental minimum of 45 "
        "seconds before it may corroborate `final_spin`. At least one retained "
        "vibration rising edge must also occur at or after the start of that "
        "same electrical candidate. A short intermediate electrical spin or "
        "vibration evidence accumulated only before the current candidate "
        "cannot satisfy the heated terminal rule.\n\n"
    )
    if "experimental minimum of 45 seconds" not in text:
        text = insert_before_one_of(
            text,
            (
                "The electrical candidate corroborates mechanical evidence; it never replaces it.",
                "The runtime supports two confirmation paths:",
            ),
            addition,
            path=path,
        )
    if "| Heated electrical candidate maturity | 45 s |" not in text:
        lines = text.splitlines(keepends=True)
        matches = [
            i for i, line in enumerate(lines)
            if line.lstrip().startswith("| Hybrid spin required events |")
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"{path}: expected one Hybrid spin required events row, got {len(matches)}"
            )
        lines.insert(
            matches[0] + 1,
            "| Heated electrical candidate maturity | 45 s | "
            "Experimental internal minimum candidate age before heated hybrid confirmation |\n",
        )
        text = "".join(lines)
    return text

def transform_architecture(text: str) -> str:
    path = "docs/en/ARCHITECTURE.md"
    addition = (
        "For heated hybrid confirmation, the electrical candidate is not usable "
        "immediately when it becomes active. It must survive an experimental "
        "45-second maturity gate, and at least one retained vibration rising "
        "edge must belong temporally to the same candidate episode by occurring "
        "at or after its start. This temporal correlation is intended to reject "
        "short intermediate spins without introducing a second machine-specific "
        "power threshold.\n\n"
    )
    if "45-second maturity gate" not in text:
        text = insert_before_one_of(
            text,
            (
                "Window, coverage, freshness, electrical thresholds, heating threshold, and heating timing values are configurable.",
                "The detector must not assume that the terminal spin sequence has a fixed duration",
            ),
            addition,
            path=path,
        )
    return text

def transform_readme(text: str) -> str:
    path = "README.md"
    bullet = (
        "- In a heated hybrid cycle, the electrical spin candidate must mature "
        "for 45 seconds and at least one vibration edge must occur at or after "
        "the start of that candidate before it may confirm `final_spin`.\n"
    )
    if "must mature for 45 seconds" not in text:
        text = insert_before_one_of(
            text,
            (
                "- Stale electrical samples must not continue supporting an electrical candidate after the configured maximum source age.\n",
                "- Finish is inferred from the absence of meaningful electrical activity over time rather than from an exact standby-power value.\n",
            ),
            bullet,
            path=path,
        )
    return text

def transform_project_map(text: str) -> str:
    path = "PROJECT_MAP.md"
    text = replace_if_present(
        text,
        "Terminal-phase, hybrid-spin, heating-context, and recovery rules are currently FR-029 through FR-058.",
        "Terminal-phase, hybrid-spin, heating-context, and recovery rules are currently FR-029 through FR-060.",
    )
    return text

def transform_user_manual_en(text: str) -> str:
    path = "docs/en/USER_MANUAL.md"
    addition = (
        "### 10.9 Heated-cycle terminal-profile maturity\n\n"
        "For a cycle where heating has been detected and hybrid confirmation is "
        "enabled, an electrical spin candidate does not confirm the terminal "
        "phase immediately. The current experimental implementation requires "
        "the candidate to remain active for at least **45 seconds** and requires "
        "at least one retained vibration OFF-to-ON edge to occur at or after "
        "the start of that same electrical candidate. Vibration accumulated only "
        "before the electrical episode cannot complete heated-cycle confirmation.\n\n"
        "This is a targeted heated-cycle safeguard. It does not change the "
        "non-heated hybrid path, hybrid-disabled vibration-only behavior, or "
        "finish detection semantics.\n\n"
        "---\n\n"
    )
    if "### 10.9 Heated-cycle terminal-profile maturity" not in text:
        text = insert_before_heading_prefix(text, "## 11.", addition, path=path)
    return text

def transform_user_manual_ru(text: str) -> str:
    path = "docs/ru/USER_MANUAL.md"
    addition = (
        "### 10.9 Зрелость terminal-profile в heated-цикле\n\n"
        "Если в цикле был обнаружен нагрев и включён hybrid, одного появления "
        "electrical spin candidate недостаточно для подтверждения терминальной "
        "фазы. В текущей экспериментальной реализации candidate должен "
        "оставаться активным не менее **45 секунд**, а как минимум один "
        "сохранённый фронт вибрации OFF → ON должен произойти не раньше начала "
        "этого же electrical candidate. События вибрации, накопленные только до "
        "начала электрического эпизода, не могут завершить heated-cycle "
        "подтверждение.\n\n"
        "Это точечная защита для heated-cycle. Она не меняет non-heated hybrid "
        "path, vibration-only поведение при отключённом hybrid и семантику "
        "finish detection.\n\n"
        "---\n\n"
    )
    if "### 10.9 Зрелость terminal-profile в heated-цикле" not in text:
        text = insert_before_heading_prefix(text, "## 11.", addition, path=path)
    return text

TRANSFORMS = {
    "README.md": transform_readme,
    "custom_components/laundry_monitor/const.py": transform_const,
    "custom_components/laundry_monitor/spin.py": transform_spin,
    "custom_components/laundry_monitor/runtime.py": transform_runtime,
    "custom_components/laundry_monitor/diagnostics.py": transform_diagnostics,
    "custom_components/laundry_monitor/translations/ru.json": transform_ru_json,
    "tests/components/laundry_monitor/test_diagnostics.py": transform_test_diagnostics,
    "tests/components/laundry_monitor/test_spin_runtime.py": transform_spin_runtime_tests,
    "docs/en/REQUIREMENTS.md": transform_requirements,
    "docs/en/STATE_MACHINE.md": transform_state_machine_doc,
    "docs/en/SPECIFICATION.md": transform_spec,
    "docs/en/ARCHITECTURE.md": transform_architecture,
    "PROJECT_MAP.md": transform_project_map,
    "docs/en/USER_MANUAL.md": transform_user_manual_en,
    "docs/ru/USER_MANUAL.md": transform_user_manual_ru,
}

NEW_FILES: dict[str, str] = {}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    rendered: dict[str, tuple[str, str]] = {}

    for rel, transformer in TRANSFORMS.items():
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"Run from repository root; missing {rel}")
        before = path.read_text(encoding="utf-8")
        after = transformer(before)
        rendered[rel] = (before, after)

    for rel, content in NEW_FILES.items():
        path = root / rel
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if before and before != content:
            raise RuntimeError(f"{rel} already exists with different content")
        rendered[rel] = (before, content)

    for rel in (
        "custom_components/laundry_monitor/translations/en.json",
        "custom_components/laundry_monitor/translations/ru.json",
    ):
        if rel in rendered:
            json.loads(rendered[rel][1])
        else:
            json.loads((root / rel).read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for rel, (_before, after) in rendered.items():
            if not rel.endswith(".py"):
                continue
            temp_path = tmpdir / Path(rel).name
            temp_path.write_text(after, encoding="utf-8")
            py_compile.compile(str(temp_path), doraise=True)

    diff_lines: list[str] = []
    for rel, (before, after) in rendered.items():
        if before == after:
            continue
        diff_lines.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )

    print("".join(diff_lines), end="")
    if args.apply:
        for rel, (_before, after) in rendered.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(after, encoding="utf-8")
        print(f"\nApplied heated-cycle spin correlation hardening to {len(rendered)} files.")
    else:
        print("\nPreview only. Re-run with --apply to write the changes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
