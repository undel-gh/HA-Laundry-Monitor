# ARCHITECTURE.md

# Laundry Monitor Architecture

Status: Draft

Version: 0.1

---

# 1. Overview

Laundry Monitor is built around a modular analysis pipeline.

Each module has a single responsibility and communicates with the next module using well-defined data structures.

The architecture intentionally separates:

* raw sensor processing;
* cycle analysis;
* laundry tracking;
* diagnostics;
* Home Assistant entities.

This separation allows algorithms to evolve without breaking the public API.

---

# 2. High-Level Architecture

```text
Power Sensor
Door Sensor
Vibration Sensor
Leak Sensor (optional)
Temperature Sensor (optional)

        │
        ▼

+--------------------+
| Activity Detector  |
+--------------------+

        │
        ▼

+--------------------+
| Spin Detector      |
+--------------------+

        │
        ▼

+--------------------+
| Finish Detector    |
+--------------------+

        │
        ▼

+--------------------+
| Leak Detector      |
+--------------------+

        │
        ▼

+--------------------+
| State Machine      |
+--------------------+

        │
        ├──────────────► Home Assistant Sensors
        ├──────────────► Binary Sensors
        ├──────────────► Events
        └──────────────► Diagnostics

Laundry Tracking
        ▲
        │
        └────────────── User interaction
```

---

# 3. Components

## 3.1 Activity Detector

Purpose:

Determine whether meaningful machine activity has occurred.

Responsibilities:

* evaluate power measurements;
* ignore standby consumption;
* update the internal last_activity timestamp.

The Activity Detector does **not** determine whether a cycle is running.

It answers only one question:

> Was there meaningful activity since the previous evaluation?

---

## 3.2 Spin Detector

Purpose:

Detect the washing machine's final spin.

Primary inputs:

* vibration sensor;
* activity information.

The detector should expose a confidence level to the State Machine.

---

## 3.3 Finish Detector

Purpose:

Determine whether the washing cycle has finished.

Inputs:

* last meaningful activity;
* spin detection;
* configurable timeout.

The Finish Detector should avoid relying on standby power values.

---

## 3.4 Leak Detector

Purpose:

Monitor optional leak sensors.

Responsibilities:

* detect leak conditions;
* publish safety state;
* generate diagnostic events.

Leak detection must not modify the cycle state.

---

## 3.5 State Machine

Purpose:

Maintain the current washing cycle state.

The State Machine is the only component allowed to change the public cycle state.

Inputs:

* Activity Detector
* Spin Detector
* Finish Detector

Outputs:

* public state
* state transition reason
* diagnostic information
* Home Assistant events

---

## 3.6 Laundry Tracking

Laundry Tracking is an optional module.

Laundry Tracking is independent from cycle detection.

Responsibilities:

* determine whether laundry is believed to still be inside the machine;
* maintain laundry presence status;
* record unload timestamps.

Laundry Tracking does not influence the cycle state.

---

# 4. Data Flow

Sensor Updates

↓

Activity Detection

↓

Spin Detection

↓

Finish Detection

↓

State Machine

↓

Entities + Events

Laundry Tracking receives notifications from the State Machine but operates independently.

---

# 5. Public API

Laundry Monitor exposes only:

* Home Assistant entities;
* Home Assistant events;
* Button entities;
* Configuration options.

Internal implementation details must remain private.

---

# 6. Diagnostics

Every state transition should include:

* previous state;
* new state;
* transition reason;
* confidence;
* timestamp.

The confidence value is intended for diagnostics only.

Confidence calculation is implementation-specific and may change between releases without affecting the public API.

---

# 7. Design Rules

* Each component has a single responsibility.
* Components communicate only through defined interfaces.
* Internal algorithms may evolve without changing the public API.
* Laundry Tracking must remain independent from cycle detection.
* Leak detection must remain independent from cycle detection.
* Native Home Assistant entity types should be preferred over custom APIs whenever possible.
