# Laundry Monitor

[![Validate](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml/badge.svg)](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml)
[![HACS: Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [Home Assistant](https://www.home-assistant.io/) custom integration that monitors and analyzes a washing machine cycle using **external sensors** — a power meter, and optionally a door and vibration sensor. It does not talk to the washing machine directly, so it works with any machine plugged into a monitored smart plug.

Laundry Monitor answers questions like: *Is the machine idle? Has a cycle started? Is it running? Was the final spin detected? Has the cycle finished? Is the laundry still inside? And — why did the integration decide that?*

> **Status:** early development (v0.1.0). The state machine, detectors, statistics, and diagnostics are implemented and covered by tests, but the integration has not yet been widely validated on real hardware. Feedback and issues are welcome.

## Features

- Passive, observe-only design — it **never** controls devices, sends notifications, or switches plugs. You build automations on top of its state and events.
- A small, stable public cycle state model: `idle → armed → running → final_spin → finished`, plus `error`.
- Power-based activity and cycle-start detection, with a confirmation delay to reject brief spikes.
- Optional vibration-based final-spin detection with a diagnostic confidence value.
- Finish detection from the *absence of meaningful activity*, with a separate fallback path when no final spin is detected.
- Optional laundry tracking: the machine reaching `finished` does **not** assume the laundry was removed — that is an explicit user action.
- Cycle statistics: live and last-cycle duration, and last-cycle energy (when an energy sensor is configured).
- Home Assistant events for every major transition, so automations can react to cycle start, final spin, finish, and unload.
- Full diagnostics download, native per-integration debug logging, and Repairs issues when a required sensor goes missing.
- Survives Home Assistant restarts by restoring a persisted snapshot, without emitting false lifecycle events.
- Localization support (English and Russian included).
- Multiple washing machines — add one config entry per machine.

## Requirements

- Home Assistant **2026.6.0** or newer.
- A **power sensor** (`sensor` with device class `power`, reporting watts) — required.
- Optionally a **door sensor** (`binary_sensor`, device class `door`/`opening`) and a **vibration sensor** (`binary_sensor`, device class `vibration`).
- Optionally a **leak sensor**, an **energy sensor** (device class `energy`, for per-cycle energy), and a **plug switch** (used for diagnostics only).

A typical setup is a smart plug that exposes power and energy, plus an inexpensive door and vibration sensor. The more sensors you provide, the more the integration can tell you — but only the power sensor is mandatory.

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/undel-gh/HA-Laundry-Monitor` with category **Integration**.
3. Search for **Laundry Monitor**, install it, and restart Home Assistant.

### Manual

1. Copy `custom_components/laundry_monitor` into your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant.

## Configuration

Everything is configured through the UI — there is no YAML.

1. Go to **Settings → Devices & Services → Add Integration** and search for **Laundry Monitor**.
2. Select the source entities. The power sensor is required; the door, vibration, leak, energy, and plug entities are optional.
3. Optionally enable **laundry tracking** to expose the *Mark unloaded* button and the *Laundry present* sensor.

You can adjust the entities later with **Reconfigure**, and tune the detection parameters under the integration's **Configure** (Options) menu.

### Options

All thresholds and timeouts are configurable. Defaults:

| Option | Default | Purpose |
| --- | ---: | --- |
| Activity threshold | 5 W | Power at or above this counts as meaningful activity. |
| Start threshold | 10 W | Power at or above this is a cycle-start candidate. |
| Start confirmation | 30 s | Power must stay above the start threshold this long to start a cycle. |
| Spin required events | 3 | Vibration pulses needed within the window to consider a spin. |
| Spin window | 180 s | Rolling window over which spin pulses are counted. |
| Spin minimum cycle time | 600 s | A spin is only considered after the cycle has run this long. |
| Spin activity max age | 120 s | Power activity must be this recent to support a spin. |
| Finish confirmation | 180 s | Quiet period after a final spin before declaring the cycle finished. |
| Running-state finish confirmation | 600 s | Quiet period used as the fallback finish when no final spin was detected. |
| Arming timeout | 1800 s | Return to `idle` if a cycle never starts after the door closes. |
| Finished-state retention | 300 s | How long `finished` is kept when laundry tracking is off, before returning to `idle`. |
| Power-unavailable grace | 120 s | How long the power sensor may be missing before entering `error`. |
| Snapshot maximum age | 86400 s | Active-cycle snapshots older than this are discarded on restart. |

The activity threshold must not exceed the start threshold.

## Entities

Names below use `<device>` as the configured machine name.

### Primary

| Entity | Description |
| --- | --- |
| `sensor.<device>_cycle_state` | Public cycle state (`idle`, `armed`, `running`, `final_spin`, `finished`, `error`). |
| `binary_sensor.<device>_running` | On while the cycle is running or in final spin. |
| `binary_sensor.<device>_finished` | On when the cycle has finished. |
| `binary_sensor.<device>_final_spin_detected` | On once a final spin was detected in the current cycle. |
| `sensor.<device>_current_cycle_duration` | Live elapsed time of the active cycle. |
| `sensor.<device>_last_cycle_duration` | Duration of the most recently completed cycle. |
| `sensor.<device>_last_cycle_energy` | Energy used by the last cycle (requires an energy sensor). |

### Laundry tracking (when enabled)

| Entity | Description |
| --- | --- |
| `binary_sensor.<device>_laundry_present` | Whether laundry is believed to still be inside. |
| `button.<device>_mark_unloaded` | Press to mark the laundry removed and reset the cycle. |
| `sensor.<device>_last_unloaded_at` | Timestamp of the last explicit unload. |

### Diagnostic

Additional diagnostic entities are exposed and categorized as diagnostics by default, including current power, last activity, last transition reason and time, final-spin confidence and evidence count, finish-timer details, a leak binary sensor (when a leak sensor is configured), and rejected-transition counters.

## Events

Laundry Monitor fires the following events on the Home Assistant event bus:

| Event | Fired when |
| --- | --- |
| `laundry_monitor.cycle_started` | A cycle start is confirmed. |
| `laundry_monitor.final_spin_detected` | A probable final spin is detected. |
| `laundry_monitor.cycle_finished` | The cycle is confirmed finished. |
| `laundry_monitor.door_opened_after_finish` | The door is opened while `finished` (diagnostic only). |
| `laundry_monitor.machine_unloaded` | The user marks the laundry as removed. |
| `laundry_monitor.leak_detected` | The optional leak sensor becomes active. |
| `laundry_monitor.state_changed` | Any public state change. |
| `laundry_monitor.transition_rejected` | An illegal state transition was requested (diagnostic). |

Each payload includes the `config_entry_id`, the machine `name`, and a `timestamp`; state events additionally carry `old_state`, `new_state`, and `reason`.

### Example automation

Notify when a cycle finishes:

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

## How it works

Raw sensor readings flow through a pipeline of single-responsibility detectors — activity, spin, and finish — whose normalized results feed a state machine. Only the state machine changes the public cycle state, and every transition records a human-readable reason. Laundry tracking and leak detection run independently and never influence the cycle state.

A few deliberate design choices:

- Opening the door does **not** imply the laundry was removed. `finished` stays until you press *Mark unloaded* (with tracking on) or the retention period expires (with tracking off).
- Finish is inferred from a lack of meaningful activity over time, not from trying to distinguish standby power levels.
- A brief power-sensor outage does not immediately end a cycle; only a prolonged outage beyond the grace period leads to `error`.

For the full design, see the documentation under [`docs/en`](docs/en): [`SPECIFICATION.md`](docs/en/SPECIFICATION.md), [`ARCHITECTURE.md`](docs/en/ARCHITECTURE.md), [`STATEMACHINE.md`](docs/en/STATEMACHINE.md), and [`REQUIREMENTS.md`](docs/en/REQUIREMENTS.md).

## Troubleshooting

- **Enable debug logging:** open the integration and choose *Enable debug logging* to capture a trace of detection decisions (start confirmation, transitions, spin evidence, finish timing, recovery). Turn it off to stop.
- **Download diagnostics:** use *Download diagnostics* for a point-in-time snapshot of state, detectors, sources, and the persisted snapshot.
- **Repairs:** if the required power sensor becomes unavailable, a Repairs issue is raised until it recovers.

## What it is not

Laundry Monitor is not a notification system, a washing-machine controller, a vendor integration, or a dishwasher/dryer monitor. Those behaviors belong in your own Home Assistant automations, built on the states and events above.

## Contributing

Issues and pull requests are welcome. The test suite runs against a recent Home Assistant on Python 3.14:

```bash
pip install -r requirements_test.txt
pytest
```

The English documentation in `docs/en` is canonical; translated docs should follow it and must not define separate behavior.

## License

Released under the [MIT License](LICENSE).
