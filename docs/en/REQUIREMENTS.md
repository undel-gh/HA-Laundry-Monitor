# REQUIREMENTS.md

# Laundry Monitor Requirements

Status: Draft

Version: 0.1

---

# Functional Requirements

## FR-001

The integration shall require a power sensor. It shall support optional door and vibration sensors.

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
