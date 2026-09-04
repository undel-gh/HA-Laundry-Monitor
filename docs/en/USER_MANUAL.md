# Laundry Monitor — User Manual

> **Document status:** first user-manual version for the current Laundry Monitor implementation.
>
> The English documentation is canonical. The Russian manual is maintained as a user-facing translation.

## 1. What Laundry Monitor does

Laundry Monitor is a Home Assistant custom integration that creates a logical monitoring device for a washing machine using existing Home Assistant sensor entities.

It does **not** communicate with or control the washing machine directly. Instead, it observes electrical and optional physical signals and infers the current cycle state.

The integration can determine whether a washing machine is:

- idle;
- armed and waiting for a cycle to start;
- running;
- in a probable terminal spin sequence / terminal phase;
- finished;
- unable to be evaluated reliably because a required source is unavailable.

It can also optionally:

- use current measurements as additional activity evidence;
- use a door sensor for arming context and post-finish access detection;
- use a vibration sensor for terminal-spin detection;
- combine vibration and sustained electrical evidence with the optional hybrid spin detector;
- monitor a leak sensor independently from the cycle state;
- calculate per-cycle energy use when an energy sensor is available;
- track whether laundry is still considered present in the machine.

Laundry Monitor is passive. It does not switch a smart plug, send notifications, sound alarms, start or stop the washing machine, or modify external entities.

---

## 2. Requirements

### 2.1 Home Assistant

Home Assistant **2026.6.0 or newer** is required.

### 2.2 Required source

A Home Assistant power sensor is required:

- domain: `sensor`;
- device class: `power`;
- value: active power, normally in watts.

Example:

```text
sensor.washing_machine_power
```

The power sensor is the authoritative source for cycle-start confirmation.

### 2.3 Optional sources

Laundry Monitor can also use:

| Source | Home Assistant type | Purpose |
| --- | --- | --- |
| Current sensor | `sensor`, device class `current` | Supplemental meaningful-activity evidence and hybrid diagnostics |
| Door sensor | `binary_sensor`, `door` or `opening` | Arming context and post-finish door events |
| Vibration sensor | `binary_sensor`, `vibration` | Terminal-spin evidence |
| Leak sensor | `binary_sensor`, `moisture` | Independent leak monitoring |
| Energy sensor | `sensor`, device class `energy` | Last-cycle energy statistics |
| Smart-plug switch | `switch` | Diagnostics only |

Only the power sensor is required for basic cycle monitoring.

Optional sources are allowed to become unavailable. Their loss must degrade the corresponding feature rather than stop basic power-only monitoring.

---

## 3. Installation

### 3.1 HACS custom repository

1. Open **HACS**.
2. Open **Custom repositories**.
3. Add:

   ```text
   https://github.com/undel-gh/HA-Laundry-Monitor
   ```

4. Select **Integration** as the category.
5. Find **Laundry Monitor** in HACS and install it.
6. Restart Home Assistant.

### 3.2 Manual installation

1. Copy:

   ```text
   custom_components/laundry_monitor
   ```

   to:

   ```text
   <config>/custom_components/
   ```

2. Restart Home Assistant.

---

## 4. Adding a washing machine

Configuration is performed through the Home Assistant UI. YAML configuration is not required.

1. Open **Settings → Devices & Services**.
2. Select **Add Integration**.
3. Search for **Laundry Monitor**.
4. Enter a friendly name for the washing machine.
5. Select the required power sensor.
6. Select any optional sources that are available.
7. Enable **Laundry Tracking** if you want Laundry Monitor to remember that laundry remains in the machine until you explicitly mark it as unloaded.

Configure one Laundry Monitor entry for each washing machine.

The same power sensor cannot be used by more than one Laundry Monitor entry.

---

## 5. Recommended first setup

For a first installation, use the normal detector defaults unless you already have measured data from the washing machine.

The basic defaults are intended to provide conservative behavior:

| Setting | Default |
| --- | ---: |
| Power activity threshold | 5 W |
| Current activity threshold | 0.1 A |
| Start threshold | 10 W |
| Start confirmation | 30 s |
| Required vibration events | 3 |
| Vibration event window | 180 s |
| Minimum cycle time before final spin | 600 s |
| Maximum age of supporting activity | 120 s |
| Electrical spin window | 30 s |
| Minimum electrical coverage | 20 s |
| Maximum electrical source age | 30 s |
| Hybrid spin enabled | Off |
| Hybrid required vibration events | 2 |
| Final-spin finish confirmation | 180 s |
| Running-state finish confirmation | 600 s |
| Arming timeout | 1800 s |
| Finished-state retention | 300 s |
| Power sensor unavailable grace period | 120 s |
| Maximum snapshot age | 86400 s |

Electrical spin **power** and **current** thresholds intentionally have no universal default. They depend on the electrical profile of the individual washing machine and measuring device.

For normal power-only monitoring, no hybrid tuning is required.

---

## 6. Cycle states

Laundry Monitor exposes a public cycle-state sensor.

| State | Meaning |
| --- | --- |
| `idle` | No active cycle is being tracked. |
| `armed` | Door context indicates that a cycle may start soon. |
| `running` | A washing cycle has been confirmed. |
| `final_spin` | A probable terminal spin sequence / terminal phase has been detected. |
| `finished` | Cycle completion has been confirmed. |
| `error` | Reliable evaluation is not possible, for example after prolonged loss of the required power source. |

### 6.1 About `final_spin`

The historical state name is `final_spin`, but it should be understood as **terminal phase detected**, not as “the drum is continuously at maximum RPM”.

The terminal phase may include:

- several spin stages;
- changes of drum speed;
- short pauses;
- pumping and draining;
- drum positioning;
- short electrical activity after spinning;
- end-of-program signalling.

Once a terminal phase has been confirmed, normal terminal activity does not automatically return the integration to `running`.

---

## 7. How cycle start is detected

Power is the authoritative start source.

A start candidate is created when power reaches the configured **Start threshold**. The condition must persist for **Start confirmation** before the cycle is declared `running`.

This confirmation helps reject short power spikes.

The optional current sensor can contribute to meaningful-activity detection, but current alone cannot start a cycle.

### Important validation rule

The **Power activity threshold** must not be higher than the **Start threshold**.

---

## 8. Meaningful activity

Laundry Monitor uses meaningful electrical activity to distinguish active work from quiet periods.

Power at or above the configured **Power activity threshold** counts as power activity.

If a current sensor is configured and available, current at or above the **Current activity threshold** also counts as meaningful activity.

This is intentionally an OR relationship:

```text
power activity
OR
current activity
=
meaningful activity
```

However, current remains supplemental:

- current alone does not confirm cycle start;
- current alone does not confirm final spin;
- current alone does not confirm cycle completion.

---

## 9. Zero values versus unavailable data

A valid numeric zero is real data.

```text
0 W ≠ unavailable
0 A ≠ unavailable
```

Examples:

- A reachable smart plug that is switched off and reports `0 W` is providing valid information: no power is being delivered.
- A machine in a genuine zero-power pause may also report `0 W`.
- An `unavailable`, `unknown`, invalid, or absent power state means that Laundry Monitor does not have a reliable measurement.

Laundry Monitor must not reinterpret a valid `0 W` or `0 A` as source failure.

It must also not replace missing or unavailable data with a synthetic zero.

This distinction is particularly important during low-power pauses and communication failures.

---

## 10. Final-spin detection

Laundry Monitor can confirm the terminal phase through two paths.

### 10.1 Vibration-only path

When a vibration sensor is configured, Laundry Monitor counts vibration OFF-to-ON events in a rolling time window.

A normal vibration-only confirmation requires:

- the configured number of vibration events;
- all required events inside the configured vibration window;
- the minimum cycle age to have been reached;
- sufficiently recent meaningful electrical activity.

With the default settings this means:

```text
3 vibration events
inside 180 seconds
after at least 600 seconds of cycle time
with recent electrical activity
```

### 10.2 Hybrid vibration + electrical path

Hybrid spin confirmation is optional and disabled by default.

It is intended for vibration sensors that may miss physical spin events or remain latched ON long enough to produce too few rising edges.

A hybrid confirmation requires:

- hybrid mode enabled;
- a configured vibration sensor;
- a configured electrical spin power threshold;
- a reduced but still meaningful number of vibration events;
- a sustained electrical spin candidate;
- the minimum cycle age;
- recent meaningful activity;
- fresh electrical source data.

Electrical evidence **alone can never confirm final spin**.

### 10.3 Electrical spin candidate

The electrical detector uses a time-weighted rolling median rather than a single instantaneous sample.

The relevant settings are:

- **Electrical spin window** — rolling observation window;
- **Minimum electrical coverage** — minimum observed time required inside that window;
- **Maximum electrical source age** — how long the latest real source observation may be extrapolated;
- **Electrical spin power threshold** — machine-specific power level used for the candidate;
- **Electrical spin current threshold** — optional corroborating current level.

The freshness limit prevents an old high-power sample from supporting a hybrid decision indefinitely if the sensor stops updating while still appearing available.

### 10.4 Current corroboration

Current is corroborating evidence only.

A hybrid decision is power-authoritative. The optional current threshold helps diagnostics show whether the current profile supports the same conclusion, but failure to cross the current threshold does not by itself block hybrid confirmation.

### 10.5 Choosing hybrid thresholds

Do **not** copy power/current thresholds from another washing machine unless its electrical profile has been measured and shown to be comparable.

A practical calibration workflow is:

1. Leave hybrid mode disabled.
2. Observe several complete cycles.
3. Compare vibration events with power/current history around the physical terminal spin.
4. Choose a power threshold that is sustained during the relevant spin signature but does not commonly occur in unrelated late-cycle activity.
5. Configure the optional current threshold as corroborating diagnostic evidence.
6. Enable the disabled electrical/hybrid diagnostic entities.
7. Observe several additional cycles in shadow mode.
8. Enable hybrid confirmation only after the combination does not show false terminal-spin candidates.

Example values such as `100 W` and `0.7 A` may be appropriate for a particular measured machine, but they are **not universal recommendations**.

### 10.6 Hybrid configuration rules

Laundry Monitor rejects contradictory hybrid settings.

In particular:

- hybrid mode requires a vibration sensor;
- hybrid mode requires an electrical spin power threshold;
- the hybrid vibration-event requirement must be lower than the normal vibration-only requirement;
- minimum electrical coverage must not exceed the electrical window;
- reconfiguration must not remove the vibration source while hybrid mode remains enabled.

---

## 11. Finish detection

Laundry Monitor uses inactivity confirmation rather than trying to recognize an exact standby wattage.

### 11.1 After `final_spin`

After the terminal phase is detected, meaningful activity resets the finish timer.

When meaningful activity has remained absent for **Final-spin finish confirmation**, the cycle becomes `finished`.

Default:

```text
180 seconds
```

### 11.2 Fallback when final spin was not detected

If no terminal phase was confirmed, Laundry Monitor uses a longer conservative inactivity timer while still in `running`.

Default:

```text
600 seconds
```

This allows a cycle to finish even when no vibration sensor is configured or final-spin evidence is insufficient.

---

## 12. Door sensor behavior

The door sensor is optional.

When configured, it can provide context before and after a cycle.

Typical behavior:

- closing the door may move the integration to `armed`;
- opening the door before a cycle starts may return it to `idle`;
- opening the door after `finished` can generate a diagnostic event.

Opening the door after a cycle does **not** automatically mean the laundry was removed.

---

## 13. Laundry Tracking

Laundry Tracking is optional.

When enabled, Laundry Monitor exposes:

- `binary_sensor.<device>_laundry_present`;
- `button.<device>_mark_unloaded`;
- `sensor.<device>_last_unloaded_at`.

Laundry is considered present after a cycle starts and remains present after the cycle finishes.

To tell Laundry Monitor that the laundry has actually been removed, press **Mark unloaded**.

Door opening alone does not clear laundry presence.

When Laundry Tracking is disabled, the `finished` state is retained for the configured retention period and then returns automatically to `idle`.

---

## 14. Leak monitoring

If a leak sensor is configured, Laundry Monitor monitors it independently.

Leak detection does not change the washing-cycle state.

This separation is intentional: a leak is safety information, while `idle`, `running`, `final_spin`, and `finished` describe the cycle lifecycle.

Use normal Home Assistant automations if you want a leak event to send a notification, sound an alarm, or switch another device.

---

## 15. Main entities

Entity IDs depend on the configured washing-machine name.

Important user-facing entities include:

| Entity | Purpose |
| --- | --- |
| `sensor.<device>_cycle_state` | Current public cycle state |
| `binary_sensor.<device>_running` | On in `running` and `final_spin` |
| `binary_sensor.<device>_finished` | On when the cycle is `finished` |
| `binary_sensor.<device>_final_spin_detected` | Latches after terminal-spin evidence is confirmed |
| `sensor.<device>_current_cycle_duration` | Current cycle duration |
| `sensor.<device>_last_cycle_duration` | Most recently completed cycle duration |
| `sensor.<device>_last_cycle_energy` | Last-cycle energy, when configured |

Additional diagnostic entities expose detector internals.

Some experimental electrical/hybrid diagnostic entities are disabled by default in the entity registry. Enable them from the device/entity page when tuning or troubleshooting hybrid detection.

Useful hybrid diagnostics include:

- final-spin confirmation path;
- vibration evidence count and confidence;
- electrical spin candidate;
- electrical power rolling median;
- optional current rolling median;
- electrical candidate start time;
- activity timestamps.

The confirmation path can identify whether `final_spin` was confirmed through:

```text
vibration_only
```

or:

```text
hybrid
```

Diagnostic confirmation-path information is not authoritative persisted cycle state and may be cleared after a restart.

---

## 16. Events and automations

Laundry Monitor emits Home Assistant events for lifecycle observations.

Common events include:

- `laundry_monitor.cycle_started`;
- `laundry_monitor.final_spin_detected`;
- `laundry_monitor.cycle_finished`;
- `laundry_monitor.door_opened_after_finish`;
- `laundry_monitor.machine_unloaded`;
- `laundry_monitor.leak_detected`;
- `laundry_monitor.state_changed`;
- `laundry_monitor.transition_rejected`.

Laundry Monitor itself does not send notifications.

Example notification automation:

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

You can also use the exposed binary sensors or cycle-state sensor as normal Home Assistant automation triggers.

---

## 17. Changing sensors and settings

There are two different configuration actions.

### Reconfigure

Use **Reconfigure** to change source entities or Laundry Tracking.

Examples:

- replace the power sensor;
- add/remove the current sensor;
- add a vibration sensor;
- change the door sensor;
- add an energy or leak sensor.

Hybrid configuration invariants are checked during reconfiguration.

### Configure / Options

Use **Configure** to change detector thresholds and lifecycle timers.

Do not change several detector parameters at once when tuning a real machine. Change one logical group, collect complete-cycle data, and compare the results.

---

## 18. Restarts and recovery

Laundry Monitor stores runtime information so that Home Assistant restarts do not automatically discard an active cycle.

A stored active-cycle snapshot is restored only when it is sufficiently recent according to **Maximum snapshot age**.

Recovery is conservative: stale or unsafe runtime state must not be blindly restored.

Transient rolling electrical evidence and diagnostic confirmation-path information may be rebuilt or cleared after restart.

---

## 19. Required power source failure

The power sensor is required.

A brief `unavailable`, `unknown`, missing, or non-numeric state is tolerated for the configured **Power sensor unavailable grace period**.

If the required source remains unusable beyond the grace period, Laundry Monitor may enter `error` and create a Home Assistant Repairs issue.

Remember:

```text
valid 0 W
```

is not a source failure.

Only loss of a reliable numeric observation is treated as source unavailability.

---

## 20. Troubleshooting

### The cycle never starts

Check:

- the power sensor is available and numeric;
- the machine exceeds the **Start threshold**;
- start-level power remains present for the full **Start confirmation** period;
- the power activity threshold is not higher than the start threshold.

### The cycle starts from short spikes

Increase **Start confirmation** and review whether the **Start threshold** is too low.

### `final_spin` is never detected

If using vibration-only detection:

- confirm that the vibration entity produces OFF-to-ON transitions;
- inspect event spacing;
- check the vibration window;
- check minimum cycle time;
- check whether meaningful activity is recent enough.

If the sensor physically detects spinning but produces too few rising edges, hybrid detection may be appropriate after machine-specific calibration.

### Hybrid confirms `final_spin` too early

Disable hybrid mode first, then inspect:

- vibration evidence timing;
- power rolling median;
- electrical threshold;
- minimum cycle time;
- electrical coverage;
- source freshness;
- whether the same electrical profile occurs during heating or ordinary wash activity.

Raise or redesign the machine-specific threshold only after reviewing complete-cycle history.

### Hybrid never confirms

Check:

- hybrid mode is enabled;
- a vibration sensor is configured;
- the electrical power threshold is configured;
- enough vibration events are present;
- the rolling median reaches the configured power threshold;
- minimum electrical coverage is reached;
- the cycle has passed minimum cycle time;
- the power source remains fresh;
- meaningful activity is recent.

### `finished` is delayed

Check the last meaningful activity timestamp. Any qualifying power or current activity resets the finish confirmation timer.

If `final_spin` was not detected, the longer running-state fallback timer is used.

### Current sensor becomes unavailable

Basic monitoring should continue with power only.

Do not interpret the missing current source as `0 A`.

### Power sensor shows `0 W`

If the entity is available and the value is numeric, `0 W` is valid data. This is normal for a powered-down smart plug output, a stopped machine, or a real zero-power interval.

### Integration enters `error`

Check the required power source and Home Assistant Repairs.

A prolonged unavailable/unknown/non-numeric power source is different from a valid numeric zero.

---

## 21. Debug logging and diagnostics

For unexpected behavior:

1. Open the Laundry Monitor integration or device in Home Assistant.
2. Enable **debug logging**.
3. Reproduce a complete relevant part of the cycle.
4. Stop debug logging.
5. Download diagnostics.

Diagnostics can include:

- configured source entities and their availability;
- current runtime state;
- detector thresholds;
- vibration evidence;
- electrical/hybrid statistics;
- activity timestamps;
- finish timers;
- cycle statistics;
- persisted snapshot information;
- rejected transitions.

For hybrid issues, enable the disabled hybrid diagnostic entities before collecting cycle history when practical.

---

## 22. Updating Laundry Monitor

When updating through HACS:

1. Install the new version.
2. Restart Home Assistant if requested.
3. Open the Laundry Monitor entry.
4. Review options when release notes mention new detector settings.
5. Verify that required and optional source entities are still configured.
6. For detector changes, observe at least one complete cycle before assuming previous tuning is still optimal.

Avoid copying tuning parameters from another washing machine without validating its signal profile.

---

## 23. Multiple washing machines

Create a separate Laundry Monitor config entry for each machine.

Each entry has its own:

- required power source;
- optional sensor set;
- thresholds;
- cycle state;
- statistics;
- laundry-tracking state.

Do not share one power sensor between multiple entries.

---

## 24. Suggested production checklist

Before relying on a newly configured machine in daily automations, observe several full cycles and confirm:

- cycle start is detected reliably;
- ordinary low-power pauses do not finish the cycle;
- `final_spin` is not detected during unrelated early/mid-cycle activity;
- the cycle reaches `finished` after real completion;
- power-source outages behave differently from valid `0 W`;
- Laundry Tracking behaves as expected, if enabled;
- hybrid mode, if enabled, produces no false terminal-phase transitions;
- both normal and unusual programs have been observed where practical.

Detector settings describe the electrical and vibration behavior of a particular installation. Treat tuning as calibration, not as a universal washing-machine profile.

---

## 25. Where to find more technical information

For implementation and normative behavior, see:

- `docs/en/SPECIFICATION.md`;
- `docs/en/ARCHITECTURE.md`;
- `docs/en/REQUIREMENTS.md`;
- `docs/en/STATE_MACHINE.md`;
- `PROJECT_MAP.md`.

The user manual explains how to operate and tune the integration. The canonical technical documents define the exact architecture and required behavior.
