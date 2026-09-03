# Laundry Monitor

[![Validate](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml/badge.svg)](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml)
[![HACS: Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Laundry Monitor** is a Home Assistant custom integration that monitors and analyzes washing-machine cycles using external sensors. It does not communicate with or control the washing machine directly.

The only required source is a **power sensor**. Optional current, door, vibration, leak, energy, and plug-switch entities can provide additional evidence, diagnostics, and statistics.

Laundry Monitor is intended to answer questions such as:

- Is the washing machine idle, armed, running, in its terminal phase, finished, or in an error state?
- Has a real cycle started?
- Has a probable terminal spin sequence been detected?
- Has meaningful electrical activity ended?
- Is laundry still considered present?
- Why did the integration make a particular state transition?

> **Status:** development (`v0.1.4 rc1`). The state machine, activity/spin/finish detectors, persistence, statistics, diagnostics, and Home Assistant entities are implemented and covered by tests. The integration is currently being field-tested on real hardware, and detector behavior may still evolve before a stable release.

## Features

- Passive, observe-only design: Laundry Monitor does **not** control the washing machine, switch a smart plug, send notifications, or trigger alarms.
- Small public cycle-state model:
  `idle → armed → running → final_spin → finished`, plus `error`.
- Power-based cycle-start detection with a configurable confirmation period.
- Optional current-assisted meaningful-activity detection.
- Optional vibration-based detection of a probable **terminal spin sequence / terminal phase**.
- Experimental opt-in hybrid confirmation can combine reduced vibration evidence with a fresh, sustained electrical spin candidate.
- Electrical confirmation uses power as the primary signal; optional current is corroborating diagnostics only.
- Two finish paths:
  - shorter confirmation after terminal-phase detection;
  - conservative fallback when terminal spin was not detected.
- Optional door-based arming context and post-finish access diagnostics.
- Optional laundry tracking with explicit **Mark unloaded** action.
- Optional leak monitoring independent from the cycle state.
- Cycle duration and optional energy statistics.
- Home Assistant events for lifecycle transitions.
- Downloadable diagnostics and native Home Assistant debug logging.
- Repairs support for required power-source failures.
- Runtime state persistence and restart recovery.
- English and Russian translations.
- Multiple washing machines: configure one entry per machine.

## Requirements

- Home Assistant **2026.6.0** or newer.
- A **power sensor** (`sensor` with device class `power`) — required.
- Optional **current sensor** (`sensor` with device class `current`).
- Optional **door/opening sensor** (`binary_sensor` with device class `door` or `opening`).
- Optional **vibration sensor** (`binary_sensor` with device class `vibration`).
- Optional **leak sensor** (`binary_sensor` with device class `moisture`).
- Optional **energy sensor** (`sensor` with device class `energy`) for per-cycle energy statistics.
- Optional **plug switch** for diagnostics.

Only the power sensor is mandatory. Optional sources must degrade cleanly when unavailable and must not prevent basic power-only cycle detection.

## Installation

### HACS

1. Open HACS.
2. Open **Custom repositories**.
3. Add:

   ```text
   https://github.com/undel-gh/HA-Laundry-Monitor
   ```

   Category: **Integration**.
4. Find **Laundry Monitor** in HACS and install it.
5. Restart Home Assistant.

### Manual

1. Copy:

   ```text
   custom_components/laundry_monitor
   ```

   into:

   ```text
   <config>/custom_components/
   ```

2. Restart Home Assistant.

## Configuration

Configuration is performed through the Home Assistant UI. No YAML configuration is required.

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Laundry Monitor**.
3. Select the required power sensor and any optional source entities.
4. Optionally enable **Laundry Tracking**.

Source entities can later be changed with **Reconfigure**. Detector thresholds and lifecycle timeouts are available through **Configure** / the integration options flow.

## Detection options

Current implementation defaults:

| Option | Default | Purpose |
| --- | ---: | --- |
| Power activity threshold | 5 W | Power at or above this level counts as meaningful power activity. |
| Current activity threshold | 0.1 A | Optional current at or above this level counts as supplemental meaningful activity. |
| Start threshold | 10 W | Power at or above this level becomes a cycle-start candidate. |
| Start confirmation | 30 s | Start-level power must remain present for this period before the cycle is confirmed. |
| Spin required events | 3 | Required vibration events inside the rolling spin window. |
| Spin window | 180 s | Rolling window used for vibration evidence. |
| Spin minimum cycle time | 600 s | Terminal-spin detection is not considered before this cycle age. |
| Spin activity max age | 120 s | Meaningful electrical activity must be sufficiently recent to support spin evidence. |
| Electrical spin window | 30 s | Time window used for the experimental time-weighted electrical rolling statistics. |
| Electrical spin minimum coverage | 20 s | Minimum observed coverage required before an electrical candidate is valid. |
| Electrical spin maximum source age | 30 s | Maximum age for the last real source update to remain valid evidence. |
| Electrical spin power threshold | unset | Machine-specific power threshold. No universal project default is defined. |
| Electrical spin current threshold | unset | Optional machine-specific current corroboration threshold. |
| Hybrid spin enabled | false | Enables the experimental `reduced vibration + electrical candidate` confirmation path. |
| Hybrid spin required events | 2 | Vibration evidence required by the hybrid path when it is enabled. |
| Finish confirmation | 180 s | Quiet period used after `final_spin`. |
| Running-state finish confirmation | 600 s | Conservative quiet-period fallback when terminal spin was not detected. |
| Arming timeout | 1800 s | Returns `armed` to `idle` when no cycle starts. |
| Finished-state retention | 300 s | Keeps `finished` visible when Laundry Tracking is disabled. |
| Power-unavailable grace | 120 s | Delays `error` during a brief loss of the required power source. |
| Snapshot maximum age | 86400 s | Rejects stale persisted active-cycle snapshots during recovery. |

The power activity threshold must not exceed the start threshold.

Current measurements supplement activity detection but **do not independently start a cycle**. Missing or unavailable current data is not interpreted as zero current or inactivity.

## Cycle states

| State | Meaning |
| --- | --- |
| `idle` | No active cycle is known. |
| `armed` | Door context indicates that a cycle may start soon. |
| `running` | A cycle has been confirmed and ordinary cycle execution is in progress. |
| `final_spin` | A probable **terminal spin sequence / terminal phase** has been detected. |
| `finished` | Cycle completion has been confirmed. |
| `error` | A condition prevents reliable cycle evaluation, such as prolonged loss of the required power source. |

The historical identifier `final_spin` is retained as part of the public API. Conceptually it represents entry into a probable terminal phase rather than an assertion that the drum is continuously spinning.

A terminal phase may include multiple spin stages, short stops, overlapping spin and drain operation, drain-only operation after the drum stops, drum positioning, electronics activity, and end-of-program signalling. Detailed normative behavior is defined in [`docs/en/STATE_MACHINE.md`](docs/en/STATE_MACHINE.md).

## Entities

Entity IDs depend on the configured machine name.

### Primary entities

| Entity | Description |
| --- | --- |
| `sensor.<device>_cycle_state` | Public cycle state. |
| `binary_sensor.<device>_running` | On in `running` and `final_spin`. |
| `binary_sensor.<device>_finished` | On in `finished`. |
| `binary_sensor.<device>_final_spin_detected` | Latches when terminal-spin evidence was detected during the cycle. |
| `sensor.<device>_current_cycle_duration` | Elapsed duration of the current active cycle. |
| `sensor.<device>_last_cycle_duration` | Duration of the most recently completed cycle. |
| `sensor.<device>_last_cycle_energy` | Last-cycle energy when an energy source is configured. |

### Laundry Tracking

Available when Laundry Tracking is enabled:

| Entity | Description |
| --- | --- |
| `binary_sensor.<device>_laundry_present` | Whether laundry is believed to remain in the machine. |
| `button.<device>_mark_unloaded` | Explicitly marks laundry as removed. |
| `sensor.<device>_last_unloaded_at` | Timestamp of the latest explicit unload. |

Opening the door does **not** automatically mean that the laundry was removed.

### Diagnostic entities

Laundry Monitor also exposes diagnostic entities such as:

- last transition reason and timestamp;
- current power;
- optional current draw;
- combined meaningful activity;
- separate power and current activity states;
- last combined, power, and current activity timestamps;
- final-spin confidence and evidence count;
- electrical-spin candidate state and candidate timestamp;
- time-weighted rolling power and optional current medians;
- electrical source freshness and observed coverage in downloadable diagnostics;
- final-spin confirmation path (`vibration_only` or `hybrid`);
- finish quiet-since timestamp, deadline, and remaining time;
- rejected-transition counters;
- optional leak state.

These diagnostic entities are intentionally verbose during development and field testing.

## Events

Laundry Monitor fires Home Assistant events for significant lifecycle observations and transitions:

| Event | Fired when |
| --- | --- |
| `laundry_monitor.cycle_started` | A cycle start is confirmed. |
| `laundry_monitor.final_spin_detected` | Probable terminal-spin evidence is confirmed. |
| `laundry_monitor.cycle_finished` | Cycle completion is confirmed. |
| `laundry_monitor.door_opened_after_finish` | Door opens while the cycle remains `finished`. |
| `laundry_monitor.machine_unloaded` | Laundry is explicitly marked as removed. |
| `laundry_monitor.leak_detected` | Optional leak source becomes active. |
| `laundry_monitor.state_changed` | Public cycle state changes. |
| `laundry_monitor.transition_rejected` | An illegal state transition is requested. |

Event payloads include the config-entry identifier, configured machine name, timestamp, and event-specific evidence.

### Example automation

```yaml
automation:
  - alias: "Laundry finished"
    trigger:
      - platform: event
        event_type: laundry_monitor.cycle_finished
    action:
      - service: notify.mobile_app_phone
        data:
          message: "The washing machine has finished."
```

Laundry Monitor itself intentionally does not send notifications; automations consume its states and events.

## How detection works

Raw Home Assistant source states are validated and normalized before detector evaluation.

```text
Power + optional current
        │
        ▼
 Activity Detector
        │
        ├──────────────► Spin Detector + vibration
        │
        └──────────────► Finish Detector
                               │
                               ▼
                         State Machine
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
              Entities       Events      Diagnostics
```

Important design rules:

- Power remains the required and authoritative source for cycle-start confirmation.
- Optional current contributes supplemental meaningful-activity evidence.
- Optional current alone cannot confirm cycle start, terminal spin, or completion.
- The normal terminal-spin path remains vibration-only and uses the configured full vibration requirement.
- When explicitly enabled, the experimental hybrid path may confirm the same `final_spin` state from reduced vibration evidence plus a fresh, sustained electrical candidate.
- Electrical evidence alone can never confirm `final_spin`.
- Machine-specific electrical thresholds have no universal defaults and must be configured explicitly.
- Stale electrical samples must not continue supporting an electrical candidate after the configured maximum source age.
- Finish is inferred from the absence of meaningful electrical activity over time rather than from an exact standby-power value.
- Optional vibration provides terminal-spin evidence.
- Leak detection operates independently and does not change the cycle state.
- Laundry Tracking operates independently from cycle detection.
- Missing optional sources must not stop basic cycle detection.
- Missing sensor data must not be interpreted as zero or inactivity.

For detailed behavior and invariants, use the canonical English documentation.

## Project documentation

- [`PROJECT_MAP.md`](PROJECT_MAP.md) — quick navigator: task → specification → implementation → tests.
- [`docs/en/SPECIFICATION.md`](docs/en/SPECIFICATION.md) — canonical product specification and detection model.
- [`docs/en/ARCHITECTURE.md`](docs/en/ARCHITECTURE.md) — component boundaries and data flow.
- [`docs/en/REQUIREMENTS.md`](docs/en/REQUIREMENTS.md) — normative functional and non-functional requirements.
- [`docs/en/STATE_MACHINE.md`](docs/en/STATE_MACHINE.md) — detailed public/internal states, transitions, timers, recovery, edge cases, and invariants.
- [`docs/ru/`](docs/ru/) — Russian translations. English documentation remains canonical.

When looking for implementation details, start with [`PROJECT_MAP.md`](PROJECT_MAP.md) instead of scanning the repository.

## Troubleshooting

### Enable debug logging

Open the integration in Home Assistant and use **Enable debug logging**. Reproduce the issue, then stop debug logging to collect the trace.

The runtime logs start confirmation, activity decisions, state transitions, spin evidence, finish evaluation, timer scheduling, source failures, and recovery behavior.

### Download diagnostics

Use **Download diagnostics** on the integration or device to obtain a point-in-time view of:

- configured sources and their availability;
- runtime state;
- detector thresholds and evidence;
- lifecycle timers;
- cycle statistics;
- persisted runtime snapshot;
- rejected-transition information.

### Repairs

If the required power source remains unavailable, Laundry Monitor can create a Home Assistant Repairs issue. Brief outages are tolerated according to the configured grace period.

## What Laundry Monitor is not

Laundry Monitor is not:

- a washing-machine controller;
- a vendor-specific appliance integration;
- a notification service;
- an automatic smart-plug safety controller;
- a dishwasher monitor;
- a dryer monitor;
- a universal appliance monitor.

Use Home Assistant automations to build actions on top of Laundry Monitor states and events.

## Contributing

Issues and pull requests are welcome.

Install test dependencies and run the suite:

```bash
pip install -r requirements_test.txt
pytest
```

The English documentation under `docs/en/` is canonical. Translations must follow it and must not define separate behavior.

During early development, keep documentation, runtime behavior, tests, translations, and [`PROJECT_MAP.md`](PROJECT_MAP.md) synchronized when changing detector or state-machine behavior.

## License

Released under the [MIT License](LICENSE).
