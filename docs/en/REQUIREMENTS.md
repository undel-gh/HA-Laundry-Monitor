# REQUIREMENTS.md

# Laundry Monitor Requirements

Status: Draft

Version: 0.1

---

# Functional Requirements

## FR-001

The integration shall require a power sensor. It shall support optional current, door and vibration sensors.

---

## FR-002

The integration shall operate without a leak sensor.

---

## FR-003

The integration shall expose a stable public cycle state model.

---

## FR-004

The integration shall never control external devices.

---

## FR-005

The integration shall explain every state transition.

---

## FR-006

The integration shall expose diagnostic information.

---

## FR-007

Every threshold shall be configurable.

---

## FR-008

Activity detection shall be independent from spin detection.

---

## FR-009

Spin detection shall be independent from finish detection.

---

## FR-010

Leak detection shall be independent from cycle detection.

---

## FR-011

Laundry Tracking shall be independent from cycle detection.

---

## FR-012

Laundry Tracking shall be optional.

---

## FR-013

Opening the washing machine door shall not imply that laundry has been removed.

---

## FR-014

Laundry shall be marked as removed only by explicit user action.

---

## FR-015

The integration shall support multiple washing machines.

---

## FR-016

The integration shall support localization.

---

## FR-017

English translations shall be provided.

---

## FR-018

All user-visible strings shall be localizable.

---

## FR-019

The integration shall expose Home Assistant events for major state transitions.

---

## FR-020

Public entity identifiers shall remain stable between compatible releases.

---

## FR-021

The integration shall operate correctly without a current sensor.

---

## FR-022

When a current sensor is configured, the Activity Detector may treat current above a configurable threshold as supplemental meaningful activity.

---

## FR-023

Cycle-start confirmation shall remain based on the required power sensor. Current activity may corroborate diagnostics but shall not independently start a cycle.

---

## FR-024

Current activity may reset or cancel finish confirmation and may contribute supporting evidence to spin detection.

---

## FR-025

Current activity alone shall not confirm final spin or cycle completion.

---

## FR-026

Unavailable, unknown, or invalid current data shall not be interpreted as zero current or inactivity.

---

## FR-027

Loss of the optional current sensor shall degrade the integration to power-only operation without changing the public cycle state.

---

## FR-028

Diagnostics shall identify whether power activity, current activity, or both contributed to a detector decision.

---

# Non-Functional Requirements

## NFR-001

The integration shall follow Home Assistant Integration Quality Scale recommendations where applicable.

---

## NFR-002

The public API shall remain backward compatible within the same major version.

---

## NFR-003

Internal implementation details may change without affecting public entities.

---

## NFR-004

Debug mode shall not affect cycle detection behaviour.

---

## NFR-005

Optional sensors shall not be required for basic operation.

---

## NFR-006

Loss of an optional sensor shall not stop cycle detection.

---

## NFR-007

The integration should continue operating after Home Assistant restart without requiring manual recovery whenever sufficient state can be restored.

---

## NFR-008

Configuration shall be performed through Config Flow.

---

## NFR-009

The integration should use native Home Assistant entity types whenever possible.

---

## NFR-010

The architecture should support future detector implementations without requiring changes to the public API.

---

## NFR-011

Adding or removing an optional current source shall not introduce new public cycle states.

---

## NFR-012

Current-assisted detection shall remain deterministic for a given ordered sequence of source observations and timestamps.
