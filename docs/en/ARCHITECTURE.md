# ARCHITECTURE.md

# Laundry Monitor Architecture

Status: Draft

Version: 0.1

---

# 1. Overview

Laundry Monitor is built around a modular analysis pipeline.

Each module has a single responsibility and communicates with the next module using well-defined data structures.

The architecture intentionally separates:

* source normalization;
* electrical activity detection;
* spin detection;
* finish detection;
* cycle state management;
* laundry tracking;
* leak detection;
* statistics and diagnostics;
* Home Assistant entities and events.

This separation allows detector algorithms to evolve without breaking the public API.

---

# 2. High-Level Architecture

```text
Required source
┌──────────────────────┐
│ Power sensor         │
└──────────┬───────────┘
           │
Optional electrical source
┌──────────▼───────────┐
│ Current sensor       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Source normalization │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Activity Detector    │
└───────┬──────────────┘
        │ normalized electrical activity
        ├──────────────────────────┐
        ▼                          ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Spin Detector        │  │ Finish Detector      │
│ + vibration evidence │  │ + inactivity timing  │
└──────────┬───────────┘  └──────────┬───────────┘
           └─────────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │ State Machine        │
              └──────────┬───────────┘
                         │
         ┌───────────────┼────────────────┐
         ▼               ▼                ▼
      Entities         Events        Diagnostics

Door sensor ───────────────► arming context and access diagnostics
Vibration sensor ──────────► Spin Detector
Energy sensor ─────────────► cycle statistics
Plug switch state ─────────► diagnostics
Leak sensor ───────────────► independent Leak Detector
State Machine ─────────────► independent Laundry Tracking
User interaction ──────────► Laundry Tracking
 ```
 
Power remains the only required electrical source. Current is optional and supplements, but does not replace, power-based cycle-start detection.

---

# 3. Components

## 3.1 Source Normalization

Purpose:

Convert raw Home Assistant source states into validated, unit-aware observations.

Responsibilities:

* validate the required power value;
* validate the optional current value when configured;
* reject unavailable, unknown, and non-numeric source states;
* preserve source timestamps and availability;
* prevent missing data from being interpreted as zero;
* expose normalized observations to detector components.

Normalized observations may include:

```text
power_w
current_a
power_available
current_available
observed_at
```

Loss of the optional current source must degrade to power-only operation.

---


## 3.2 Activity Detector

Purpose:

Determine whether meaningful machine activity has occurred.

Responsibilities:

* evaluate required power measurements;
* evaluate optional current measurements;
* ignore standby consumption and sensor noise;
* maintain source-specific activity evidence;
* update the internal `last_activity` timestamp.

The initial current-assisted activity model is:

```text
meaningful_activity = power_activity OR current_activity
```

The power activity signal remains authoritative for cycle-start detection. Current activity may keep an active cycle alive and cancel a pending finish confirmation when low active-power motor or pump operation is observed.

The Activity Detector does **not** directly change the public cycle state.

It answers only one question:

> Was there meaningful activity since the previous evaluation?

---

## 3.3 Spin Detector

Purpose:

Detect that the washing machine has probably entered its **terminal spin sequence**, which is treated as the entry marker for the broader **terminal phase**.

Primary inputs:

* vibration events;
* normalized activity information;
* cycle age;
* power observations and derived electrical statistics;
* optional current observations and derived electrical statistics.

Current activity may increase spin confidence by supporting the conclusion that a motor is operating during a vibration window.

Current activity must not independently confirm final spin. The detector must still require the configured vibration evidence unless a future detector explicitly defines another compatible algorithm.

The currently implemented detector is vibration-event based. The architecture shall also permit a future **hybrid spin detector** that combines mechanical evidence with a sustained electrical spin candidate.

The hybrid detector may contain an electrical-corroboration stage:

```text
Power history ───────────────┐
                            ├──► Electrical spin candidate ──┐
Optional current history ───┘                                │
                                                             ├──► Spin Detector
Vibration evidence ──────────────────────────────────────────┤
Cycle age / timing gates ────────────────────────────────────┘
```

The electrical stage should use windowed or sustained statistics rather than instantaneous samples. Suitable implementations may use rolling medians, minimum sustained durations, or equivalent robust measures.

Power remains the primary electrical signal. Current is optional corroboration. When both are measured by the same smart plug or meter, the implementation should treat them as correlated observations of the same electrical load rather than as two independent votes.

A compatible hybrid algorithm may reduce the amount of vibration evidence required for confirmation only when the electrical candidate and all applicable timing gates are simultaneously satisfied. Electrical evidence alone must not produce a final-spin result.

Thresholds and window lengths for electrical spin corroboration are implementation-specific and configurable. Architecture must not encode machine-specific field values as universal defaults.

The detector must not assume that the terminal spin sequence has a fixed duration or contains one uninterrupted spin. A validated terminal spin sequence may contain multiple spin stages and short pauses, and its duration may vary with program and load. Draining may begin while the drum is still rotating and may continue after the drum has fully stopped.

A confirmed terminal-spin-sequence result is a terminal-phase marker. Subsequent meaningful activity is expected during overlapping spin-and-drain operation, drain-only operation after drum stop, drum positioning, additional terminal spinning, electronics activity, or end-of-program signalling and must not automatically invalidate the result.

+The detector should expose evidence, the confirmation path used, and a confidence level to the State Machine. When hybrid detection is implemented, diagnostics should distinguish vibration-only confirmation from hybrid vibration-plus-electrical confirmation.

---


## 3.4 Finish Detector

Purpose:

Determine whether the washing cycle has finished.

Inputs:

* last meaningful activity;
* spin detection;
* configurable timeout
* source availability.

When a current sensor is configured and available, either power activity or current activity counts as meaningful activity and resets or cancels finish confirmation.

In `final_spin`, meaningful activity after terminal-spin-sequence confirmation is treated as terminal-phase activity. The finish timer is anchored to the last such activity. The Finish Detector does not request a return to `running` merely because activity resumes after a short quiet interval.
 
The Finish Detector must:

* avoid relying on exact standby power values;
* avoid treating missing source data as inactivity;
* fall back to power-only evaluation when the optional current source is unavailable;
* never use current alone as proof that a cycle has finished.

---

## 3.5 Leak Detector

Purpose:

Monitor optional leak sensors.

Responsibilities:

* detect leak conditions;
* publish leak state;
* generate diagnostic events.

Leak detection must not modify the cycle state.

---

## 3.6 State Machine

Purpose:

Maintain the current washing cycle state.

The State Machine is the only component allowed to change the public cycle state.

Inputs:

* Activity Detector;
* Spin Detector;
* Finish Detector.

Outputs:

* public state;
* state transition reason;
* diagnostic information;
* Home Assistant events.

The addition or removal of an optional current sensor must not change the public state model.
The State Machine must distinguish normal terminal-phase activity from a confirmed continuation of the ordinary program. A `final_spin → running` transition may occur only on an explicit `cycle_continuation_confirmed` detector decision, never on raw or normalized activity alone.

---

## 3.7 Laundry Tracking

Laundry Tracking is an optional module.

Laundry Tracking is independent from cycle detection.

Responsibilities:

* determine whether laundry is believed to still be inside the machine;
* maintain laundry presence status;
* record unload timestamps.

Laundry Tracking does not influence the cycle state.

---

## 3.8 Cycle Statistics

Cycle Statistics is independent from state transitions except for lifecycle timestamps.

Responsibilities:

* track current and last cycle duration;
* calculate last-cycle energy when an energy sensor is configured;
* preserve completed-cycle statistics across restarts.

Current measurements are not an energy source and must not be integrated as energy unless a separate, explicitly defined calculation is introduced.

---

# 4. Data Flow

```text
Source update
    ↓
Validation and normalization
    ↓
Source-specific evidence
    ↓
Meaningful activity
    ├──► Spin evaluation
    └──► Finish evaluation
              ↓
         State Machine
              ↓
      Entities + Events + Diagnostics
```

Laundry Tracking receives lifecycle notifications from the State Machine but operates independently.

Leak detection operates in parallel and does not modify the cycle state.

---

# 5. Current-Assisted Evidence Model

The optional current sensor is a supplemental source.

The initial implementation should use it conservatively:

* power remains required;
* start confirmation remains power-based;
* current activity may refresh `last_activity`;
* current activity may cancel or reset finish confirmation;
* current activity may add spin evidence;
* current alone must not produce `final_spin` or `finished`;
* current unavailability must be diagnostic, not fatal.

Load-type or detailed washing-phase classification is not part of the public state model. Such classification may be introduced later as diagnostic evidence after validation across multiple machines and programs.

---

# 6. Public API

Laundry Monitor exposes only:

* Home Assistant entities;
* Home Assistant events;
* Button entities;
* Configuration options.

Internal implementation details must remain private.

Adding an optional current source must not require new public cycle states.

---

# 7. Diagnostics

Every state transition should include:

* previous state;
* new state;
* transition reason;
* confidence;
* timestamp.

When a current sensor is configured, diagnostics should also include:

* raw and normalized current;
* current source availability;
* current activity state;
* last current activity timestamp;
* whether current evidence affected activity, spin, or finish evaluation.

The confidence value is intended for diagnostics only.

Confidence calculation is implementation-specific and may change between releases without affecting the public API.

---

# 8. Design Rules

* Each component has a single responsibility.
* Components communicate only through defined interfaces.
* Internal algorithms may evolve without changing the public API.
* Power remains the only required electrical source.
* Optional current evidence must degrade cleanly to power-only operation.
* Missing current data must not be interpreted as zero or inactivity.
* Current alone must not confirm final spin or cycle completion.
* Laundry Tracking must remain independent from cycle detection.
* Leak detection must remain independent from cycle detection.
* Native Home Assistant entity types should be preferred over custom APIs whenever possible.
