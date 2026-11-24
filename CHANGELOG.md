# Changelog

Notable user-facing changes are recorded at publication time, not on every
issue-fix PR. Releases use the exact version in
`custom_components/laundry_monitor/manifest.json`: `X.Y.Z-rcN` for a
release candidate and `X.Y.Z` for a stable release. Tags use no `v` prefix.

For existing releases up to `0.1.8-rc7`, consult
[GitHub Releases](https://github.com/undel-gh/HA-Laundry-Monitor/releases).
This file starts tracking the next release; earlier release history is not
retrospectively reconstructed here.

## [Unreleased]

No additional changes recorded.

## [0.1.9] - 2026-11-24

Stable maintenance release covering changes since the published 0.1.8 tag.

### Fixed
- Salvage valid independent laundry-tracking data and finalized statistics
  from partially corrupt snapshots; invalid mandatory transition timing
  always falls back to idle, clears active context and schedules a
  sanitized save without synthetic lifecycle events (#29).
- Degrade invalid optional unload timestamps and energy/duration fields
  individually; retain mandatory non-timing fail-closed guards (#29).
- Reject boolean, non-finite, non-numeric and overflowing optional
  numeric values; preserve finite legacy numeric strings and valid zero (#32).
- Reject non-string/blank persisted energy units without losing valid
  independent amounts; never calculate a new completed-cycle energy delta
  from unknown units. Reject corrupt numeric heating thresholds as
  proof for restoring NOT_SEEN; preserve independent valid DETECTED (#32).

### Changed
- Extract the ordered heating-aware spin-confirmation policy into a pure
  decision function without changing thresholds, gate ordering, public
  events, diagnostic contracts or detector behavior (#31).
- Reorganize bilingual user guides, canonical references, maintainer
  checklists and release notes; remove legacy paths and redundant card
  page before 1.0.0. Published historical notes remain unchanged (#33, #35).
- Add read-only Markdown local-link/heading validation and nine
  checker tests to required CI; extend HA regression coverage to
  452 tests on each of the three Core targets (#29, #31, #32, #33).

### Compatibility and upgrade
- Minimum Core remains 2026.6.0; CI targets 2026.6.0, 2026.10.4 and
  2026.11.1. Storage version remains 1; no config migration, public
  entity/event renaming or detector recalibration required.
- Existing dashboards, Diagnostics and Recorder behavior remain unchanged
  from 0.1.8. Old documentation URLs on main no longer resolve; use the
  [documentation index](docs/README.md). Versioned historical paths
  remain available at their original tags.
- Intended stable publication: 0.1.9, prerelease=false, after release
  checklist validation; no new field or HACS installation results
  are claimed at preparation. #34 remains planned before 1.0.0.
- Back up HA before upgrading; rollback to published 0.1.8 if necessary
  and restore a known-good backup.

See [0.1.9 release notes](docs/releases/0.1.9.md) and
[Russian notes](docs/releases/0.1.9.ru.md).

## [0.1.8] - 2026-11-23

First stable 0.1.8 release. This section summarizes user-facing changes
accumulated since the last plain-semver stable release, `0.1.4`, including
the 0.1.5–0.1.8 release-candidate line. It does not mean these features
were all introduced after 0.1.8-rc8.

### Added
- Heating detection and a `unknown` / `not_seen` / `detected` context for
  final-spin decisions; configurable hybrid power/vibration corroboration
  and a conservative fast path for non-heated short programs.
- Cycle persistence, restoration and additional diagnostics for heating,
  electrical spin and state transitions across Home Assistant restarts.
- `cycle_started_at` timestamp for a frontend-local live duration without
  periodic Recorder updates (#19).
- Downloadable source diagnostics separating usable measurements
  (`available`) from HA entity availability (`entity_available`) (#18).

### Fixed
- Heated-cycle hybrid `final_spin` false positives: confirmation requires
  at least 45 seconds of continuous electrical spin evidence and a fresh
  vibration edge at or after that candidate started (#1).
- Reject invalid, missing or timezone-naive persisted timing when restoring
  active cycles; fail closed rather than reviving an unsafe active state (#8).
- Power/current normalization to canonical W/A with supported unit scales,
  non-finite rejection and required-power Repairs consistency (#9, #18).
- Treat repeated valid, unchanged HA power/current reports as fresh
  electrical observations without fabricating vibration rising edges (#10).
- Consistent measurement-validity semantics in Diagnostics and runtime (#18).

### Changed
- Reduce redundant entity publications/Recorder churn without reducing
  detector evaluation cadence (#19).
- `current_cycle_duration` is now a transition-only snapshot, not a live
  ticking timer; new installations disable it and high-churn diagnostic
  entities by default, while saved registry preferences are retained (#19).
- Document `error` as a monitoring/input reliability state, not a washing
  machine fault code (#11).
- Add reviewed release metadata checks, read-only Ruff validation,
  bytecode-artifact guards, and full regression suites for Core 2026.6.0,
  2026.10.4 and 2026.11.1 with matching fixture packages (#20–#26).
  The Core 2026.11.1 test tooling update (#26) is CI-only: no runtime
  behavior changed after 0.1.8-rc8.

### Compatibility and upgrade
- Minimum supported Home Assistant Core remains **2026.6.0**; automatic
  full-suite CI covers Core **2026.6.0**, **2026.10.4** and **2026.11.1**,
  not physical field tests for every version.
- No configuration migration or entity rename in this release-preparation
  PR. Existing dashboards using `current_cycle_duration` as a live timer
  should use `cycle_started_at` while `running`/`final_spin` and
  `last_cycle_duration` after completion (#19).
- External diagnostics parsers may need to accommodate the changed meaning
  of `sources[*].available` and the new `entity_available` flag (#18).
- Historical RC3–RC7 GitHub Releases were misclassified as regular releases;
  rc8 was correctly marked a prerelease. This stable release must be
  published as **0.1.8**, `prerelease=false`, on the verified `main`
  commit. Do not retag or silently alter past RC releases.
- Required HACS fresh-install, upgrade, restart/recovery and channel smoke
  checks must be recorded before publication. Real-cycle field results
  support detector readiness but do not replace the installation checks.

See [0.1.8 stable notes](docs/releases/0.1.8.md) and
[Russian notes](docs/releases/0.1.8.ru.md).

## [0.1.8-rc8] - 2026-11-12

Release candidate changes since the published `0.1.8-rc7` tag.

### Added
- A public `cycle_started_at` timestamp sensor for live elapsed-time
  calculations in a frontend without periodic Recorder writes (#19).
- Separate `entity_available` and usable-observation `available`
  indicators in downloadable source diagnostics (#18).
- Full Core 2026.6.0 / 2026.10.4 test matrix with exact fixture pins
  and an aggregate required `Tests` check (#22).
- EN/RU release checklist, changelog, metadata preflight and post-publication
  release audit (#23).

### Fixed
- Safe recovery when persisted cycle timestamps are missing, malformed or
  timezone-naive; invalid active-cycle timing fails closed (#8).
- Power/current conversion to canonical W/A, including supported HA unit
  scales, non-finite rejection and required-power Repairs consistency (#9).
- Fresh electrical evidence from repeated HA state reports with unchanged
  readings; repeated vibration reports do not create synthetic edges (#10).
- Consistent Diagnostics, runtime and Repairs behavior for unsupported
  or invalid source units (#18).

### Changed
- Suppress redundant entity state publications and reduce Recorder history
  churn without changing detector cadence (#19).
- Existing `current_cycle_duration` is now a transition-only snapshot,
  **not** a live timer. It is disabled by default for new installations;
  previously enabled registry entries remain enabled. Use
  `cycle_started_at` during active cycles and `last_cycle_duration`
  after completion (#19).
- High-churn diagnostic entities are disabled by default for new
  installations; existing registry preferences remain unchanged (#19).
- The documented `error` cycle state means **monitoring reliability
  failure**, not a fault code from the washing machine (#11).
- CI: read-only Ruff gate, removal and rejection of tracked bytecode caches
  and support for two Home Assistant Core versions (#20, #21, #22).
- Release CLI test cleanup (#24).

### Compatibility and upgrade
- Minimum supported Core remains **2026.6.0**; full test targets are
  **2026.6.0** and fixture-supported **2026.10.4** (#22). These do not
  imply field testing on every supported version or hardware profile.
- Consumers parsing downloadable Diagnostics must note that
  `sources[*].available` now means *usable measurement*, while
  `sources[*].entity_available` captures HA entity-state availability
  (#18).
- No additional sensors are required: power remains the only mandatory
  input. Optional-current errors do not generate required-source Repairs
  issues (#9, #18).
- **No configuration migration or entity renaming is introduced by the
  release-preparation PR.** The behavior changes above may require
  updating frontend templates or external diagnostics parsers.
- **HACS update-channel change:** earlier RC3–RC7 were incorrectly
  published as regular releases, but rc8 will have `prerelease=true`.
  Existing HACS users without this repository's Pre-release option enabled
  will not be offered rc8 as a normal update; opt in for the RC. Verify both
  HACS channels before publishing. Historical metadata remains unchanged.
- This is an RC: fresh/upgrade HACS smoke testing and field verification
  must be recorded before publication. To roll back, select a previously
  published known-good version (for example `0.1.8-rc7`) and restore a
  Home Assistant backup when needed.

See [0.1.8-rc8 release notes](docs/releases/0.1.8-rc8.md) for details.

See [Release checklist](docs/maintainers/RELEASE_CHECKLIST.en.md) and
[Russian checklist](docs/maintainers/RELEASE_CHECKLIST.ru.md).
