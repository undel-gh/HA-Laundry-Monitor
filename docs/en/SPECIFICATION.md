# Laundry Monitor Specification

Status: Draft  
Version: 0.1  
Language: English  
Project: HA-Laundry-Monitor

## 1. Purpose

Laundry Monitor is a Home Assistant custom integration for monitoring washing machine cycles using external sensors.

The integration does not communicate with the washing machine directly. Instead, it analyzes signals from sensors such as:

- power meter / smart plug;
- optional current sensor;
- door sensor;
- vibration sensor;
- optional leak sensor;
- optional energy sensor for diagnostics and cycle statistics.

Laundry Monitor is designed to answer:

- Is the washing machine idle?
- Has a cycle started?
- Is the machine currently running?
- Was final spin detected?
- Has the cycle finished?
- Has the laundry been removed?
- Why did the integration decide that?

## 2. Project Scope

### 2.1 In scope

Laundry Monitor shall support:

- washing machines;
- power-based activity and cycle-start detection;
- optional current-assisted electrical activity detection;
- door-based cycle context and access detection;
- vibration-based spin detection;
- optional leak detection;
- diagnostic entities;
- Home Assistant events;
- downloadable diagnostics;
- native Home Assistant debug logging;
- localization;
- multiple configured washing machines.

### 2.2 Out of scope

Laundry Monitor shall not provide:

- vendor-specific washing machine integration;
- direct control of washing machines;
- automatic plug shutdown;
- notifications;
- siren control;
- dishwasher support;
- dryer support;
- robot vacuum support.

These actions can be implemented by the user through standard Home Assistant automations.

## 3. Design Principles

### 3.1 Passive integration

Laundry Monitor must not control devices.

It may expose sensors, binary sensors, events, diagnostics, and statistics, but it must not:

- turn off smart plugs;
- send notifications;
- trigger alarms;
- start or stop washing machines;
- modify external entities.

### 3.2 Observability

Every major internal decision should be observable.

The user should be able to understand:

- current state;
- last transition;
- transition reason;
- confidence;
- last activity time;
- last vibration time;
- last power activity time;
- last current activity time, when a current sensor is configured;
- the source evidence used to classify meaningful activity.

### 3.3 Explainability

Laundry Monitor should explain its conclusions.

Example:

```text
State: Finished
Reason: No activity for 10 minutes after final spin
Confidence: 96%
```
The confidence value is intended as a diagnostic indicator only. Confidence calculation is implementation-specific and may change between releases without affecting the public API.

Evidence:
- final spin detected
- power below activity threshold
- current below activity threshold, when configured
- no vibration
- door still closed


### 3.4 Modular algorithms

Cycle detection should be split into replaceable components:

- activity detector;
- spin detector;
- finish detector;
- leak detector;
- state machine;
- laundry tracking.

This allows future algorithm changes without breaking public entities or events.

### 3.5 Stable public API

Public entity states and event names must remain stable.

Localized strings may change, but internal state identifiers must not.

### 3.6 Use native Home Assistant entity types whenever possible.

Laundry Monitor should prefer standard Home Assistant entities (such as button, sensor, binary_sensor, number, and select) over custom services or proprietary APIs. Custom services should only be introduced when no suitable native entity exists.

## 4. Data Sources
### 4.1 Required sources

The following sources are required:

- power sensor.

Power sensor is required for detection of running state

Example:

```text
sensor.washing_machine_power
```

### 4.2 Optional sources

Optional sensors:

- current sensor;
- door sensor;
- vibration sensor;
- leak sensor;
- energy sensor;
- plug switch state.

Examples:

```text
sensor.washing_machine_current
binary_sensor.washing_machine_door
binary_sensor.washing_machine_vibration
```

The optional sources have the following roles:

- the current sensor may provide additional electrical-activity evidence, especially during motor or pump operation;
- the door sensor may provide arming context and post-finish access diagnostics;
- the vibration sensor may provide evidence for final-spin detection;
- the leak sensor belongs to the independent leak layer;
- the energy sensor is used for cycle statistics;
- the plug switch state is diagnostic only.

The power sensor remains the required and authoritative source for basic cycle-start detection. A current sensor must not be used as the only basis for declaring a cycle started, a final spin detected, or a cycle finished.

### 4.3 Optional source degradation

Loss or unavailability of an optional source must not stop basic cycle detection.

An unavailable current sensor must:

- disable current-assisted evidence;
- preserve power-only activity detection;
- not be interpreted as zero current or inactivity;
- be reported in diagnostics.

### 4.4 Zero-value and availability semantics

Source availability and source value are distinct concepts.

- A valid numeric `0 W` power reading is an observed zero-power measurement.
- A valid numeric `0 A` current reading is an observed zero-current measurement.
- A valid zero value must not be interpreted as source loss merely because it represents no electrical consumption.
- `unavailable`, `unknown`, invalid, or absent source data represents a loss of reliable telemetry and must not be converted to numeric zero.

This distinction is intentional. For example, a smart plug that is reachable and reports `0 W` after its output has been switched off is providing valid information: no power is being delivered to the washing machine. A source that is `unavailable` provides no equivalent evidence about the machine's actual electrical state.

## 5. State Model
### 5.1 Public states

The integration should expose a user-facing state sensor.

| State | Description |
|---|---|
| `idle` | Machine is idle and ready for a new cycle. |
| `armed` | Door has been closed and the integration is waiting for the cycle to start. |
| `running` | Washing cycle is active. |
| `final_spin` | A probable terminal spin sequence has been detected; the machine may still perform final spinning, draining, positioning, or end-of-program activity. |
| `finished` | Washing cycle has finished. Laundry may still be inside the machine. |
| `error` | Abnormal condition detected. |

The `finished` state remains active until the laundry is explicitly marked as removed by the user (if Laundry Tracking is enabled) or until a new cycle starts.

### 5.2 Internal states

The implementation may use additional internal states that are not exposed to the user.

| Internal state | Public state |
|---|---|
| `IDLE` | `idle` |
| `ARMED` | `armed` |
| `RUNNING` | `running` |
| `LOW_POWER_CONFIRMATION` | `running` |
| `SPIN_CANDIDATE` | `running` |
| `FINAL_SPIN_CONFIRMED` | `final_spin` |
| `FINISH_CONFIRMATION` | `final_spin` |
| `FINISHED` | `finished` |
| `ERROR` | `error` |

Internal states may evolve between releases without affecting the public API.


## 6. State Transitions
### 6.1 Basic transition model
```text
    [*] --> Idle

    idle
     ├─ door closed ─────────────→ armed
     ├─ confirmed start ─────────→ running
     └─ required source failure ─→ error

    armed
     ├─ door opened ─────────────→ idle
     ├─ arming timeout ──────────→ idle
     ├─ confirmed start ─────────→ running
     └─ required source failure ─→ error

    running
     ├─ final spin confirmed ────→ final_spin
     ├─ long inactivity fallback → finished
     └─ required source failure ─→ error

    final_spin
     ├─ normal terminal activity ─→ final_spin
     ├─ cycle continuation confirmed → running
     ├─ inactivity confirmed ─────→ finished
     └─ required source failure ──→ error

    finished
     ├─ new cycle confirmed ─────→ running
     ├─ mark unloaded ───────────→ idle
     ├─ retention elapsed
     │   when tracking disabled ─→ idle
     └─ required source failure ─→ error

    error
     └─ source recovered
         and machine quiet ──────→ idle
```

## 6.2 Transition table

| Current state | Event | Next state | Notes |
|---|---|---|---|
| `idle` | Door closed | `armed` | Optional when door sensor exists |
| `idle` | Power above start threshold | `running` | fallback when door evidence is unavailable |
| `armed` | Power above start threshold | `running` | Cycle started |
| `armed` | Door opened | `idle` | Start cancelled |
| `running` | Final spin detected | `final_spin` | Based on vibration pattern |
| `running` | No activity timeout | `finished` | Fallback if spin is not detected |
| `final_spin` | Meaningful activity | `final_spin` | Normal terminal activity; reset or cancel finish confirmation |
| `final_spin` | Cycle continuation confirmed | `running` | Strong evidence that the detected spin was not terminal |
| `final_spin` | No activity timeout | `finished` | Cycle finished |
| `finished` | Door opened | `finished` | Door opening is diagnostic only; it must not imply laundry removal |
| `finished` | Mark unloaded | `idle` | Explicit user action via button or service |
| Any | Leak detected | Same cycle state + leak alert | Leak engine is separate |

### 6.3 Laundry Tracking

Laundry Tracking is an optional module independent of the cycle state machine.

The cycle state machine determines the current state of the washing machine cycle.

Laundry Tracking determines whether laundry is believed to still be inside the machine.

Laundry Monitor must not assume that opening the door means the laundry has been removed. Laundry removal is an explicit user action.

If Laundry Tracking is enabled, the integration shall expose:

- `button.<device>_mark_unloaded`
- `binary_sensor.<device>_laundry_present`
- `sensor.<device>_last_unloaded_at`

The module shall behave as follows:

| Event | Laundry Present |
|---|---|
| Cycle started | `on` |
| Cycle finished | `on` |
| Door opened after finish | unchanged |
| User presses **Mark Unloaded** | `off` |

Opening the door after the cycle has finished may fire the `laundry_monitor.door_opened_after_finish` event for diagnostic or automation purposes, but it must not change the laundry tracking state.

Laundry is marked as removed only when the user presses `button.<device>_mark_unloaded` or invokes the corresponding service.

## 7. Detection Logic
### 7.1 Activity detection

Activity is detected primarily from power. When a current sensor is configured, current may provide supplemental electrical-activity evidence.

The Activity Detector should normalize source-specific observations:

```text
power_activity
current_activity
meaningful_activity
```

The initial current-assisted model is:

```text
meaningful_activity = power_activity OR current_activity
```

This model is intended to prevent low active-power motor or pump operation from being misclassified as inactivity.

Rules:

- cycle-start confirmation remains power-based;
- current activity may reset or cancel a pending finish confirmation;
- current activity may support spin confidence;
- current alone must not confirm final spin;
- current alone must not declare a cycle finished;
- unavailable current data must not be treated as inactivity.

Example defaults:

|Parameter	|Default|
|--- | ---:|
|Start threshold	|10 W|
| Power activity threshold | 5 W |
| Current activity threshold | 0.1 A |
| Start confirmation | 30 s |
| Running-state finish timeout | 10 min |

All active thresholds and timing values must be configurable.

## 7.2 Terminal spin sequence and terminal-phase detection

Terminal-spin-sequence detection should use vibration data when available. The detector is not required to identify one exact mechanical instant at which the final high-speed rotation starts or stops. Its purpose is to recognize that the cycle has entered a probable **terminal spin sequence** and therefore a probable **terminal phase** of the program.

A terminal spin sequence may:

- contain one spin or several spin stages;
- contain short pauses between spin stages;
- vary substantially in duration with program, load size, load distribution, and machine behavior;
- overlap with draining: the drain pump may start while the drum is still spinning;
- continue into draining after drum rotation has fully stopped;
- include pump activity, drum positioning, electronics activity, or an end-of-program chime after the mechanical spin portion has ended.

Consequently, the public `final_spin` state means **terminal spin sequence / terminal phase detected**, not **the drum is currently spinning** and not **the cycle has already finished**. The historical state identifier `final_spin` is retained as part of the public API even though the semantic meaning is broader than continuous drum rotation.

A possible detector implementation may use:

- an already confirmed `running` cycle;
- vibration-event frequency and timing;
- cycle age;
- recent meaningful electrical activity;
- sustained power characteristics that are consistent with high-speed motor operation;
- optional current characteristics as corroborating electrical evidence;
- other implementation-specific evidence that improves discrimination between ordinary intermediate spins and the terminal sequence.

Current activity is supporting evidence only. It must not independently produce a final-spin transition.


#### Experimental hybrid electrical corroboration

The implemented detector retains the vibration-only confirmation path and also provides an experimental, opt-in hybrid path. The hybrid path derives an internal **electrical spin candidate** from sustained power behavior and, when available, current behavior.

The electrical candidate corroborates mechanical evidence; it never replaces it. The runtime supports two confirmation paths:

```text
vibration-only path:
    configured vibration evidence
    + activity-recency gate
    + minimum cycle age
    -> final_spin

hybrid path:
    reduced but still meaningful vibration evidence
    + fresh sustained electrical spin candidate
    + activity-recency gate
    + minimum cycle age
    -> final_spin
```

The current defaults require three vibration events for the vibration-only path. The experimental hybrid path is disabled by default; when enabled, its default vibration requirement is two events and must remain lower than the configured vibration-only requirement.

Electrical spin evidence is based on time-weighted rolling medians over piecewise-constant source observations. Candidate evaluation also requires minimum observed coverage. A single power or current spike is insufficient.

The final observed power/current value is not extrapolated indefinitely. Each source observation is valid only up to the configured electrical source maximum age. Once the last real source update becomes stale, it stops contributing coverage and cannot keep the electrical candidate active.
 
Power is the primary electrical input. Current, when configured, may corroborate the electrical candidate but should not be treated as a fully independent vote when power and current originate from the same smart plug or measurement device.

No universal high-speed-spin power or current threshold is defined by this specification. Motor design, program, load, supply voltage, and measurement hardware can substantially change the observed values. Power and current thresholds are therefore unset by default and must be configured explicitly for field testing.

Electrical evidence alone must never confirm `final_spin`. If vibration evidence is unavailable or insufficient and no compatible hybrid rule is satisfied, the integration must remain in `running` and retain the conservative running-state finish fallback.

Experimental diagnostics include `spin_electrical_candidate`, `spin_power_rolling_median`, `spin_current_rolling_median`, `spin_electrical_candidate_since`, source freshness/coverage information, and the final-spin confirmation path. These remain diagnostic implementation details rather than stable public state identifiers.

When `final_spin` is confirmed, diagnostics identify whether the runtime used `vibration_only` or `hybrid`. The confirmation-path value is diagnostic runtime metadata and is not authoritative persisted cycle state; it may be unavailable after restart recovery.

After `final_spin` has been confirmed, ordinary meaningful electrical activity or further vibration does not by itself invalidate that state. Such observations are expected during the terminal sequence and must keep the state at `final_spin` while refreshing activity timestamps and resetting or cancelling finish confirmation.

A return from `final_spin` to `running` requires a distinct **cycle continuation confirmed** decision. This decision must use stronger evidence than a single inactivity-to-activity edge. The exact continuation-confirmation algorithm remains implementation-specific until validated across more machines, programs, and loads.

Example defaults:

| Parameter | Default | Purpose |
|---|---:|---|
| Spin required events | 3 | Number of vibration events required inside the rolling spin window |
| Spin window | 180 s | Rolling time window used to accumulate vibration evidence |
| Spin minimum cycle time | 600 s | Minimum confirmed cycle age before terminal-spin detection is allowed |
| Spin activity max age | 120 s | Maximum age of meaningful electrical activity that may support spin evidence |
| Electrical spin window | 30 s | Window for time-weighted electrical rolling statistics |
| Electrical spin minimum coverage | 20 s | Minimum observed coverage before a power candidate may become valid |
| Electrical spin maximum source age | 30 s | Maximum age of a real source update before it becomes stale |
| Electrical spin power threshold | unset | Machine-specific power threshold for the electrical candidate |
| Electrical spin current threshold | unset | Optional machine-specific current corroboration threshold |
| Hybrid spin enabled | false | Experimental hybrid confirmation is opt-in |
| Hybrid spin required events | 2 | Reduced vibration requirement used only by the hybrid path |
Confidence is diagnostic and implementation-specific; it is not a replacement for the configured evidence gates above.

The detector must not assume a fixed mechanical spin duration. A terminal spin sequence may be much shorter or longer depending on program, load size, load distribution, and machine behavior.

## 7.3 Finish detection

Finish detection should not rely on standby power level.

The integration should avoid trying to distinguish:

- plug idle consumption;
- washing machine standby;
- low-power pauses during cycle.

Instead, finish should be inferred from absence of meaningful activity over time.

When a current sensor is configured and available, meaningful electrical activity remains present while either the power or current activity condition is true. A pending finish confirmation must be cancelled or reset when either source reports meaningful activity.
 
For a cycle already in `final_spin`, the drain pump may start before the drum has fully stopped and may continue after drum rotation ends. Final draining, pump operation, drum positioning, short spin restarts, electronics activity, and an end-of-program chime may all occur before electrical activity finally becomes quiet. These observations must delay completion rather than return the cycle to `running`. The shorter final-spin finish timeout starts from the **last meaningful terminal activity**, not from the final-spin detection timestamp.

Loss of the optional current sensor must fall back to power-only evaluation. Missing current data must not be interpreted as proof of inactivity.

## 7.4 State machine options and defaults

| Option | Default | Purpose |
|---|---:|---|
| `current_activity_threshold` | 0.1 A | Current at or above this value counts as supplemental activity |
| `running_finish_confirmation` | 600 s | Conservative `running → finished` fallback |
| `arming_timeout` | 1800 s | Prevents an indefinite `armed` state |
| `finished_retention` | 300 s | Keeps `finished` observable when tracking is off |
| `power_unavailable_grace` | 120 s | Delays `error` during brief telemetry loss |
| `snapshot_max_age` | 86400 s | Rejects stale active-cycle recovery |

The existing `finish_confirmation` remains the shorter timeout used after a
confirmed final spin. The new running fallback deliberately defaults to the
10-minute value documented in the specification.

## 8. Leak Model

Leak detection belongs to a separate leak layer.

Laundry Monitor may expose:

- binary_sensor.<device>_leak_alarm;
- sensor.<device>_leak_state;
- laundry_monitor.leak_detected event.

Laundry Monitor must not turn off the plug automatically.

Users may create their own automations based on the leak event.

## 9. Home Assistant Entities
### 9.1 Main sensors

|Entity	|Example state|
|--- | --- |
|sensor.<device>_state	|running|
|sensor.<device>_last_transition_reason	|Power above start threshold|
|sensor.<device>_confidence	|94|
|sensor.<device>_current_power	|38.2 W|
|sensor.<device>_current_cycle_duration	|01:24:12|
|sensor.<device>_last_activity	|timestamp|
|sensor.<device>_last_cycle_duration	|02:11:34|
|sensor.<device>_last_cycle_energy	|0.82 kWh|

### 9.2 Binary sensors
|Entity	|Meaning|
|--- | --- |
|binary_sensor.<device>_running	|Current cycle is running|
|binary_sensor.<device>_finished	|Cycle finished|
|binary_sensor.<device>_final_spin_detected	|Final spin was detected|
|binary_sensor.<device>_activity_detected	|Meaningful power or current activity detected|
|binary_sensor.<device>_leak_alarm	|Leak sensor active|

### 9.3 Diagnostic entities

Diagnostic entities may include:

- power threshold;
- activity threshold;
- finish timeout;
- spin detection status;
- last vibration event;
- last power activity;
- last current activity, when configured;
- power activity state;
- current activity state, when configured;
- current evidence list;
- raw sensor availability.

## 10. Events

Laundry Monitor should fire Home Assistant events.

### 10.1 Event names
- laundry_monitor.cycle_started
- laundry_monitor.final_spin_detected
- laundry_monitor.cycle_finished
- laundry_monitor.machine_unloaded
- laundry_monitor.leak_detected
- laundry_monitor.state_changed

### 10.2 Event payload

```text
Example:

{
  "device_id": "washer",
  "entry_id": "abc123",
  "old_state": "running",
  "new_state": "finished",
  "reason": "No activity for 10 minutes after final spin",
  "confidence": 96,
  "timestamp": "2026-07-09T14:30:00+03:00"
}
```

## 11. Configuration
### 11.1 Config Flow

The integration shall be configured through Home Assistant UI.

Required fields:

- power sensor.

Optional fields:

- current sensor;
- door sensor;
- vibration sensor;
- leak sensor;
- energy sensor;
- plug switch.

### 11.2 Options Flow

User-configurable options:

- start threshold;
- power activity threshold;
- current activity threshold, when a current sensor is configured;
- start confirmation;
- spin required events;
- spin rolling window;
- spin minimum cycle time;
- spin activity maximum age;
- electrical spin rolling window;
- electrical spin minimum coverage;
- electrical spin maximum source age;
- machine-specific electrical spin power threshold;
- optional machine-specific electrical spin current threshold;
- experimental hybrid-spin enable/disable;
- hybrid vibration-event requirement;
- final-spin finish confirmation;
- running → finished fallback;
- arming timeout;
- finished state retention;
- power-unavailable grace period;
- snapshot maximum age.

Hybrid confirmation requires a configured vibration sensor and an explicit electrical power threshold. Its vibration-event requirement must be lower than the vibration-only requirement. Electrical minimum coverage must not exceed the electrical rolling window. Reconfigure must preserve the same hybrid/vibration invariant: an enabled hybrid configuration may not remove its vibration source.

## 12. Recovery policy

- expired `armed` snapshots recover as `idle`;
- stale `running`/`final_spin` snapshots recover as `idle`;
- `final_spin` without current vibration context recovers as `running`;
- expired `finished` snapshots recover as `idle` when Laundry Tracking is off;
- `finished` remains restorable when Laundry Tracking is on;
- `error` recovers as `idle` when valid power data is already available.

Restoration does not emit cycle-start, final-spin, cycle-finished, or unload
events.

## 13. Localization

Laundry Monitor must support localization from the first version.

### 13.1 Requirements
- All user-visible strings must be localizable.
- English is the default language.
- Additional languages may be added by contributors.
- Internal state identifiers must not be localized.
- Entity states used for automations must remain stable.
- UI labels, descriptions, config flow text, options text, and diagnostics must use Home Assistant translation files.

### 13.2 Suggested structure
```text
custom_components/laundry_monitor/
  strings.json
  translations/
    en.json
    ru.json
```

Documentation may be organized as:

```text
docs/
  en/
    SPECIFICATION.md
    ARCHITECTURE.md
    STATE_MACHINE.md
  ru/
    SPECIFICATION.md
    ARCHITECTURE.md
    STATE_MACHINE.md
```

The English documentation is canonical.

Translated documentation should follow the English version and must not define separate behavior.

## 14. Debugging and Diagnostics

Laundry Monitor shall provide native Home Assistant mechanisms for troubleshooting and explaining its decisions.

### 14.1 Downloadable diagnostics

The integration shall provide downloadable diagnostics for each configured appliance.

Diagnostics should include:

* the current public and internal state;
* the last transition reason and timestamp;
* current confidence and evidence counters;
* current source entity states and availability;
* raw current, power, door, vibration, leak, and energy values when configured;
* activity, vibration-spin, electrical-spin, and finish detector state;
* electrical rolling medians, observed coverage, and source freshness;
* electrical candidate state and timestamp;
* final-spin confirmation path and supporting evidence when available;
* configured algorithm parameters;
* laundry tracking state and `last_unloaded_at`;
* cycle statistics;
* the persisted runtime snapshot;
* rejected transition information.

Diagnostics must not expose credentials, tokens, unrelated Home Assistant configuration, or arbitrary source-entity attributes.

### 14.2 Debug logging

Laundry Monitor shall support Home Assistant's native per-integration debug logging.

Debug messages should describe meaningful algorithm decisions, including:

* source availability changes;
* start confirmation scheduling and cancellation;
* accepted and rejected state transitions;
* spin evidence evaluation;
* finish confirmation scheduling and cancellation;
* snapshot recovery decisions;
* lifecycle timeout handling.

Routine unchanged sensor values should not be logged to avoid excessive log volume.

### 14.3 Debug configuration

A custom `debug_mode` integration option is not required.

Users should use Home Assistant's native **Enable debug logging** action when a temporal execution trace is needed and **Download diagnostics** when a point-in-time state snapshot is needed.

Future versions may add cycle playback or a bounded in-memory decision history without changing the public state-machine API.

## 15. Non-goals

Laundry Monitor is not:

- a notification system;
- a washing machine controller;
- a vendor integration;
- a dishwasher monitor;
- a universal appliance monitor;
- a replacement for Home Assistant automations.

## 16. Roadmap
### v0.1
- project skeleton;
- config flow;
- basic power-based state machine;
- diagnostic entities;
- localization foundation.

### v0.2
- door sensor support;
- Laundry Tracking module;
- Home Assistant events.

### v0.3
- vibration-based final spin detection;
- confidence calculation;
- debug diagnostics.

### v0.4
- leak sensor support;
- leak state;
- optional current sensor support;
- current-assisted activity evidence;
- current-assisted spin evidence;
- event payload improvements.

### v1.0
- stable public API;
- documented state machine;
- HACS-ready release;
- English documentation;
- localization support.

## 17. Open Questions
- Should confidence be a percentage or diagnostic enum?
- Should final spin / terminal-sequence detection be enabled by default?
- What evidence and timing should be required for `cycle_continuation_confirmed` after `final_spin`?
- What default current activity threshold is reliable across smart plugs and washing machines?
- Should current ever corroborate cycle-start confirmation, or remain finish/spin evidence only?
- Should load-type or phase classification remain diagnostic-only in the stable public API?
