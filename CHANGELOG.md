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

No additional changes recorded since the 0.1.8-rc8 release candidate was
prepared. Add subsequently merged changes here rather than silently changing
an already published tag.

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
- This is an RC: fresh/upgrade HACS smoke testing and field verification
  must be recorded before publication. To roll back, select a previously
  published known-good version (for example `0.1.8-rc7`) and restore a
  Home Assistant backup when needed.

See [0.1.8-rc8 release notes](docs/releases/0.1.8-rc8.md) for details.

See [Release checklist](docs/en/RELEASE_CHECKLIST.md) and
[Russian checklist](docs/ru/RELEASE_CHECKLIST.md).
