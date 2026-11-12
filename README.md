**[English](#Laundry-Monitor) | [Русский](#Мониторинг-стирки)**

# Laundry Monitor

[![Validate](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml/badge.svg)](https://github.com/undel-gh/HA-Laundry-Monitor/actions/workflows/validate.yml)
[![HACS: Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Laundry Monitor** is a Home Assistant custom integration that creates a logical monitoring device for a washing machine using existing Home Assistant sensor entities. It monitors and analyzes washing-machine cycles using external sensors. It does not communicate with or control the washing machine directly.

The only required source is a **power sensor**. Optional current, door, vibration, leak, energy, and plug-switch entities can provide additional evidence, diagnostics, and statistics.

**Laundry Monitor** is intended to answer questions such as:

- Is the washing machine idle, armed, running, in its terminal phase, or finished?
- Is Laundry Monitor still receiving reliable data from the required power sensor?
- Has a real cycle started?
- Has a probable terminal spin sequence been detected?
- Has meaningful electrical activity ended?
- Is laundry still considered present?
- Why did the integration make a particular state transition?

> **Status:** release candidate / field validation. The state machine, activity/spin/finish detectors, heating-aware hybrid logic, persistence, statistics, diagnostics, and Home Assistant entities are implemented and covered by tests. Current work focuses on field validation, restart/recovery hardening, and documentation/diagnostic consistency before the first stable release."        

## Features

- Passive, observe-only design: Laundry Monitor does **not** control the washing machine, switch a smart plug, send notifications, or trigger alarms.
- Small public cycle-state model:
  `idle → armed → running → final_spin → finished`, plus `error` when reliable cycle monitoring is not possible (not an appliance fault code).
- Power-based cycle-start detection with a configurable confirmation period.
- Optional current-assisted meaningful-activity detection.
- Optional vibration-based detection of a probable **terminal spin sequence / terminal phase**.
- Experimental opt-in hybrid confirmation can combine vibration evidence with a fresh, sustained electrical spin candidate.
- Heating-aware cycle context can suppress false terminal-spin decisions during sustained heater operation, delay reduced-evidence hybrid confirmation for heated wash programs, and permit a conservative faster path for programs where no heating is observed.
- When hybrid confirmation is enabled and heating has been detected, full vibration evidence still requires fresh electrical corroboration before `final_spin`; hybrid-disabled configurations retain the vibration-only path.     
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

Power and current readings are converted using Home Assistant unit converters to **W** and **A** before evaluation, including sensors reporting kW, mW, mA, or μA. When a source has no `unit_of_measurement` attribute, the existing assumption of W (power) or A (current) is retained for backward compatibility. An explicitly unsupported unit is treated as unavailable; it is never interpreted as a raw W/A value. Unit labels must match Home Assistant's canonical, case-sensitive strings exactly (for example `kW`, not `kw`; `μA` uses Greek μ, not the similar-looking micro sign `µ`). An invalid required power source also triggers an existing Repairs warning. Invalid or unsupported units on the optional current sensor only degrade current-based evidence and diagnostics; they do not create a Repairs issue or block power-only detection. Optional energy-sensor statistics retain their own source-unit handling.

Valid repeated power/current reports count as fresh observations even when the numeric values stay unchanged (Home Assistant `state_changed` and `state_reported` events). This refreshes heating and electrical-spin evidence without creating vibration edges or broadcasting every identical sample to all diagnostic entities. A Home Assistant re-report does not by itself guarantee that the upstream device actually took a new physical measurement.

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
| Spin minimum cycle time | 600 s | Minimum age for ordinary vibration-only and reduced-evidence hybrid confirmation. The stricter fast non-heated hybrid path may confirm earlier. |
| Spin activity max age | 120 s | Meaningful electrical activity must be sufficiently recent to support spin evidence. |
| Electrical spin window | 30 s | Time window used for the experimental time-weighted electrical rolling statistics. |
| Electrical spin minimum coverage | 20 s | Minimum observed coverage required before an electrical candidate is valid. |
| Electrical spin maximum source age | 30 s | Maximum age for the last real source update to remain valid evidence. |
| Electrical spin power threshold | unset | Machine-specific power threshold. No universal project default is defined. |
| Electrical spin current threshold | unset | Optional machine-specific current corroboration threshold. |
| Heating power threshold | unset | Machine-specific sustained-power threshold used to recognize heater operation. Required for active hybrid confirmation. |
| Heating confirmation | 30 s | Heater-level power must remain supported for this observed duration before heating is latched for the cycle. |
| Heating observation | 300 s | Required valid power-observation coverage before the cycle may be classified as `not_seen` for heating. |
| Heated-cycle minimum spin time | 900 s | Minimum cycle age for hybrid confirmation after heating has been detected. |
| Hybrid spin enabled  | false  | Enables the experimental heating-aware hybrid confirmation paths. In a heated cycle, full vibration evidence still requires fresh electrical corroboration. |
| Hybrid spin required events  | 2  | Reduced vibration evidence used by the normal hybrid path after the applicable heating-aware timing gate. |
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
| `error` | Laundry Monitor cannot reliably evaluate the cycle, for example because required power readings remain unusable beyond the configured grace period. This does **not** indicate a diagnosed washing-machine fault. |

The `error` state belongs to **Laundry Monitor's monitoring logic**, not to the washing machine's own diagnostic system. The integration does not read appliance error codes or determine whether the appliance is mechanically or electronically defective. A configured leak sensor is monitored separately and does not cause the cycle state to become `error`.

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
| `sensor.<device>_cycle_started_at` | Start timestamp of the active cycle; calculate elapsed time in the dashboard without publishing a new state every minute. |
| `sensor.<device>_current_cycle_duration` | Legacy duration snapshot (disabled by default for new setups; not a live timer). |
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

To limit Recorder history, high-churn debug entities are disabled by default
for new installations (previous entity-registry choices are preserved).
Enable detailed power/current mirrors, activity timestamps, spin evidence,
and finish timers only when investigating a problem. Unchanged states do not
trigger HA writes even when the runtime notifies its entities. The public
`cycle_started_at` is published when an active cycle starts and cleared when
it ends; an interface can calculate live elapsed time locally using its own
clock. The legacy `current_cycle_duration` is disabled by default and, when
enabled, changes only on lifecycle/phase transitions, not as time passes.
Internal detector timing and downloadable diagnostics are not throttled.

**Laundry Monitor** also exposes diagnostic entities such as:

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

**Laundry Monitor** itself intentionally does not send notifications; automations consume its states and events.

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
- Outside a heated cycle with hybrid confirmation enabled, the full-evidence vibration-only path remains available and uses the configured full vibration requirement.
- When explicitly enabled, the experimental hybrid detector also observes heater-level power as cycle context.
- Confirmed active heating blocks `final_spin` confirmation while the heater signature is present.
- Once heating has been detected, reduced-evidence hybrid confirmation is not permitted until the configured heated-cycle minimum age has been reached.
- When hybrid confirmation is enabled and heating has been latched as `detected`, full vibration evidence is no longer an independent confirmation path: after active heating ends it still requires a fresh sustained electrical spin candidate and the heated-cycle timing gate.
- If sufficient valid early-cycle power coverage is observed without any heater signature, a fast non-heated hybrid path may bypass the normal minimum cycle age, but only with the full vibration requirement plus a fresh sustained electrical spin candidate.
- Missing or stale early-cycle power data must not be interpreted as evidence that heating did not occur.
- Electrical evidence alone can never confirm `final_spin`.
- In a heated hybrid cycle, the electrical spin candidate must mature for 45 seconds and at least one vibration edge must occur at or after the start of that candidate before it may confirm `final_spin`.
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
- [`docs/en/USER_MANUAL.md`](docs/en/USER_MANUAL.md) — English user-facing manual.
- [`docs/ru/USER_MANUAL.md`](docs/ru/USER_MANUAL.md) — Russian user-facing manual.

When looking for implementation details, start with [`PROJECT_MAP.md`](PROJECT_MAP.md) instead of scanning the repository. English documentation always remains canonical.

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

In downloaded `sources`, `available` means the reading is usable by Laundry Monitor; `entity_available` means HA exposes an entity state other than `unknown`/`unavailable`. A numeric power reading with an unsupported unit can have `entity_available=true` and `available=false`; it then appears in `required_sources_unavailable`. Raw states, units and timestamps remain visible.

### Repairs

If the required power source remains unavailable, Laundry Monitor can create a Home Assistant Repairs issue. Brief outages are tolerated according to the configured grace period.

## What Laundry Monitor is not

**Laundry Monitor** is not:

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

Before submitting a pull request, run the pinned read-only Ruff check and
the test suite:

```bash
python -m pip install ruff==0.16.8
python -m pip install -r requirements_test.txt
ruff check custom_components tests --select E,W,F
python -m pytest
```

The full suite tests against **Home Assistant Core 2026.10.4** with
`pytest-homeassistant-custom-component==0.13.375` (Python 3.14).
The minimum supported **Core 2026.6.0** has a separate API smoke suite,
paired with `pytest-homeassistant-custom-component==0.13.336`. These
fixture packages **pin exact Core versions** and must not be mixed.
CI prints and checks both installed and imported Home Assistant versions;
it fails if the imported Core differs from the declared matrix target.

To reproduce the minimum-version smoke suite, create a **separate Python
3.14 virtual environment** and run:

```bash
python -m pip install -r requirements_test_min.txt
python -m pip check
python -m pytest -vv \
  tests/components/laundry_monitor/test_source_freshness_runtime.py \
  tests/components/laundry_monitor/test_measurement_units.py \
  tests/components/laundry_monitor/test_config_flow.py \
  tests/components/laundry_monitor/test_storage_integration.py
```

The minimum smoke set exercises identical electrical `state_reported`
observations, W/A normalization and invalid-unit handling, configuration,
and snapshot recovery. The current-target job runs the **full suite**.
Both jobs run on pull requests (including docs-only PRs), `main` pushes
and scheduled validation, alongside Ruff, Hassfest and HACS.

**Upgrade cadence:** at least monthly after the Home Assistant stable
release, review both the latest stable Core and the newest fixture package.
Advance the current target only when a matching fixture/Core pair is
published, pin both versions together, run CI, and update this README.
A newer Core release without a corresponding fixture is **not yet
verified**, and must not be labelled as covered. Keep the minimum target
at 2026.6.0 until the published HACS support floor changes.

Ruff runs on **every pull request**, including documentation-only changes, and
on pushes to `main` through the read-only `Validate / Ruff check` CI job.
To apply *safe* fixes, run `ruff check custom_components tests --select E,W,F
--fix` locally on a working branch, inspect the diff, then commit the changes
in the PR for review. Do **not** use unattended `--unsafe-fixes` or push
autofixes directly to `main`. All automated validation has read-only
repository permissions.

For maintainers: configure branch protection/rulesets for `main` to require
the `Ruff check` status (alongside `Tests`, `Hassfest` and `HACS`, where
applicable), prevent bypasses and enforce changes through reviewed PRs.
The CI workflow does not itself enforce branch protection; this repository
setting must be enabled separately.

The English documentation under `docs/en/` is canonical. Translations must follow it and must not define separate behavior.

During early development, keep documentation, runtime behavior, tests, translations, and [`PROJECT_MAP.md`](PROJECT_MAP.md) synchronized when changing detector or state-machine behavior.

## License

Released under the [MIT License](LICENSE).

**[English](#Laundry-Monitor) | [Русский](#Мониторинг-стирки)**

# Мониторинг стирки

**Мониторинг стирки** — пользовательская интеграция Home Assistant, которая создаёт логическое устройство для мониторинга стиральной машины на основе существующих сущностей-датчиков Home Assistant. Она отслеживает и анализирует циклы стирки с помощью внешних датчиков, но не взаимодействует со стиральной машиной напрямую и не управляет ею.

Единственный обязательный источник данных — **датчик мощности**. Опциональные сущности тока, дверцы, вибрации, протечки, энергии и выключателя умной розетки могут предоставлять дополнительные сведения, диагностику и статистику.

**Мониторинг стирки** помогает ответить на следующие вопросы:

- Стиральная машина простаивает, готова к запуску, работает, находится в завершающей фазе или завершила цикл?
- Продолжает ли Laundry Monitor получать достоверные данные от обязательного датчика мощности?
- Действительно ли начался цикл стирки?
- Обнаружена ли вероятная завершающая последовательность отжима?
- Завершилась ли значимая электрическая активность?
- Считается ли бельё всё ещё находящимся в машине?
- Почему интеграция выполнила конкретный переход между состояниями?

> **Статус:** кандидат в релизы / проверка в реальных условиях. Конечный автомат, детекторы активности, отжима и завершения, гибридная логика с учётом нагрева, сохранение состояния, статистика, диагностика и сущности Home Assistant реализованы и покрыты тестами. Текущая работа сосредоточена на проверке в реальных условиях, повышении надёжности восстановления после перезапуска и согласованности документации и диагностики перед первым стабильным релизом.

### Возможности

- Пассивная работа только в режиме наблюдения: Laundry Monitor **не** управляет стиральной машиной, не переключает умную розетку, не отправляет уведомления и не включает сигнализацию.
- Небольшая публичная модель состояний цикла:
  `idle → armed → running → final_spin → finished`, а также `error`, если достоверный мониторинг цикла невозможен (это не код неисправности машины).
- Обнаружение начала цикла по мощности с настраиваемым периодом подтверждения.
- Опциональное обнаружение значимой активности с использованием данных о токе.
- Опциональное обнаружение вероятной **завершающей последовательности отжима / завершающей фазы** по вибрации.
- Экспериментальное гибридное подтверждение, включаемое вручную, может объединять данные о вибрации с новым устойчивым кандидатом на электрический отжим.
- Контекст цикла с учётом нагрева может подавлять ложные решения о завершающем отжиме во время продолжительной работы нагревателя, задерживать гибридное подтверждение с уменьшенным объёмом данных для программ стирки с нагревом и допускать консервативный ускоренный путь для программ, в которых нагрев не наблюдался.
- Если гибридное подтверждение включено и нагрев обнаружен, полный набор данных о вибрации всё равно требует нового электрического подтверждения перед переходом в `final_spin`; в конфигурациях с отключённым гибридным режимом сохраняется путь подтверждения только по вибрации.
- Электрическое подтверждение использует мощность как основной сигнал; опциональный ток служит только вспомогательным диагностическим источником.
- Два пути определения завершения:
  - более короткое подтверждение после обнаружения завершающей фазы;
  - консервативный резервный путь, если завершающий отжим не был обнаружен.
- Опциональный контекст перевода в состояние `armed` по датчику дверцы и диагностика открытия после завершения.
- Опциональное отслеживание белья с явным действием **Mark unloaded** («Отметить как выгруженное»).
- Опциональный мониторинг протечек, не зависящий от состояния цикла.
- Статистика длительности цикла и, опционально, энергопотребления.
- События Home Assistant для переходов жизненного цикла.
- Загружаемая диагностика и встроенный журнал отладки Home Assistant.
- Поддержка Repairs при сбоях обязательного источника мощности.
- Сохранение состояния во время работы и восстановление после перезапуска.
- Английский и русский переводы.
- Несколько стиральных машин: настройте отдельную запись конфигурации для каждой машины.

### Требования

- Home Assistant **2026.6.0** или новее.
- **Датчик мощности** (`sensor` с классом устройства `power`) — обязательно.
- Опциональный **датчик тока** (`sensor` с классом устройства `current`).
- Опциональный **датчик дверцы/открытия** (`binary_sensor` с классом устройства `door` или `opening`).
- Опциональный **датчик вибрации** (`binary_sensor` с классом устройства `vibration`).
- Опциональный **датчик протечки** (`binary_sensor` с классом устройства `moisture`).
- Опциональный **датчик энергии** (`sensor` с классом устройства `energy`) для статистики энергопотребления за цикл.
- Опциональный **выключатель розетки** для диагностики.

Обязателен только датчик мощности. При недоступности опциональных источников интеграция должна корректно продолжать работу с ограниченной функциональностью; их отсутствие не должно мешать базовому обнаружению цикла только по мощности.

### Установка

#### HACS

1. Откройте HACS.
2. Откройте **Custom repositories** («Пользовательские репозитории»).
3. Добавьте:

   ```text
   https://github.com/undel-gh/HA-Laundry-Monitor
   ```

   Категория: **Integration** («Интеграция»).
4. Найдите **Мониторинг стирки** в HACS и установите интеграцию.
5. Перезапустите Home Assistant.

#### Вручную

1. Скопируйте:

   ```text
   custom_components/laundry_monitor
   ```

   в:

   ```text
   <config>/custom_components/
   ```

2. Перезапустите Home Assistant.

### Настройка

Настройка выполняется через интерфейс Home Assistant. Конфигурация YAML не требуется.

1. Перейдите в **Настройки → Устройства и службы → Добавить интеграцию**.
2. Найдите **Мониторинг стирки**.
3. Выберите обязательный датчик мощности и любые опциональные сущности-источники.
4. При необходимости включите **Отслеживание белья**.

Позднее сущности-источники можно изменить с помощью **Reconfigure** («Изменить конфигурацию»). Пороги детекторов и тайм-ауты жизненного цикла доступны через **Configure** («Настроить») / поток параметров интеграции.

### Параметры обнаружения

Значения по умолчанию в текущей реализации:

| Параметр | По умолчанию | Назначение |
| --- | ---: | --- |
| Порог активности по мощности | 5 Вт | Мощность на этом уровне или выше считается значимой активностью по мощности. |
| Порог активности по току | 0,1 А | Опциональный ток на этом уровне или выше считается дополнительной значимой активностью. |
| Порог запуска | 10 Вт | Мощность на этом уровне или выше становится кандидатом на начало цикла. |
| Подтверждение запуска | 30 с | Мощность на уровне запуска должна сохраняться в течение этого периода, прежде чем цикл будет подтверждён. |
| Необходимое число событий отжима | 3 | Необходимое число событий вибрации в скользящем окне отжима. |
| Окно отжима | 180 с | Скользящее окно, используемое для данных о вибрации. |
| Минимальное время цикла до отжима | 600 с | Минимальный возраст цикла для обычного подтверждения только по вибрации и гибридного подтверждения с уменьшенным объёмом данных. Более строгий ускоренный гибридный путь без нагрева может подтвердить отжим раньше. |
| Максимальный возраст активности для отжима | 120 с | Значимая электрическая активность должна быть достаточно недавней, чтобы поддерживать данные об отжиме. |
| Окно электрического отжима | 30 с | Временное окно, используемое для экспериментальной взвешенной по времени скользящей электрической статистики. |
| Минимальное покрытие электрического отжима | 20 с | Минимальное наблюдаемое покрытие, необходимое для признания электрического кандидата действительным. |
| Максимальный возраст источника электрического отжима | 30 с | Максимальный возраст последнего реального обновления источника, при котором оно остаётся действительным свидетельством. |
| Порог мощности электрического отжима | не задан | Порог мощности для конкретной машины. Универсальное значение по умолчанию для проекта не определено. |
| Порог тока электрического отжима | не задан | Опциональный порог подтверждения по току для конкретной машины. |
| Порог мощности нагрева | не задан | Порог устойчивой мощности для конкретной машины, используемый для распознавания работы нагревателя. Требуется для активного гибридного подтверждения. |
| Подтверждение нагрева | 30 с | Мощность на уровне нагрева должна подтверждаться в течение этой наблюдаемой длительности, прежде чем нагрев будет зафиксирован для цикла. |
| Наблюдение за нагревом | 300 с | Необходимое покрытие действительными наблюдениями мощности, прежде чем цикл может быть классифицирован как `not_seen` для нагрева. |
| Минимальное время до отжима в цикле с нагревом | 900 с | Минимальный возраст цикла для гибридного подтверждения после обнаружения нагрева. |
| Гибридный отжим включён | false | Включает экспериментальные пути гибридного подтверждения с учётом нагрева. В цикле с нагревом полный набор данных о вибрации всё равно требует нового электрического подтверждения. |
| Необходимое число событий гибридного отжима | 2 | Уменьшенный объём данных о вибрации, используемый обычным гибридным путём после применимого временного ограничения с учётом нагрева. |
| Подтверждение завершения | 180 с | Период отсутствия активности, используемый после `final_spin`. |
| Подтверждение завершения из состояния running | 600 с | Консервативный резервный период отсутствия активности, когда завершающий отжим не был обнаружен. |
| Тайм-аут состояния armed | 1800 с | Возвращает из `armed` в `idle`, если цикл не начался. |
| Удержание состояния finished | 300 с | Сохраняет видимым состояние `finished`, если отслеживание белья отключено. |
| Допустимая задержка при недоступности мощности | 120 с | Задерживает переход в `error` при кратковременной потере обязательного источника мощности. |
| Максимальный возраст снимка состояния | 86400 с | Отклоняет устаревшие сохранённые снимки активного цикла во время восстановления. |

Порог активности по мощности не должен превышать порог запуска.

Измерения тока дополняют обнаружение активности, но **не запускают цикл самостоятельно**. Отсутствующие или недоступные данные о токе не интерпретируются как нулевой ток или отсутствие активности.

### Состояния цикла

| Состояние | Значение |
| --- | --- |
| `idle` | Активный цикл неизвестен. |
| `armed` | Контекст дверцы указывает, что цикл может скоро начаться. |
| `running` | Цикл подтверждён, выполняется его обычная стадия. |
| `final_spin` | Обнаружена вероятная **завершающая последовательность отжима / завершающая фаза**. |
| `finished` | Завершение цикла подтверждено. |
| `error` | Laundry Monitor не может достоверно оценивать цикл, например если обязательный датчик мощности остаётся непригодным дольше допустимого времени. Это **не** означает, что диагностирована неисправность стиральной машины. |

Состояние `error` относится к **логике мониторинга Laundry Monitor**, а не к системе самодиагностики стиральной машины. Интеграция не читает коды ошибок устройства и не определяет механические или электронные неисправности машины. Настроенный датчик протечки контролируется отдельно и не переводит состояние цикла в `error`.

Исторический идентификатор `final_spin` сохранён как часть публичного API. Концептуально он обозначает вход в вероятную завершающую фазу, а не утверждение о непрерывном вращении барабана.

Завершающая фаза может включать несколько стадий отжима, короткие остановки, одновременную работу отжима и слива, только слив после остановки барабана, позиционирование барабана, активность электроники и сигнал об окончании программы. Подробное нормативное поведение определено в [`docs/en/STATE_MACHINE.md`](docs/en/STATE_MACHINE.md).

### Сущности

Идентификаторы сущностей зависят от настроенного имени машины.

#### Основные сущности

| Сущность | Описание |
| --- | --- |
| `sensor.<device>_cycle_state` | Публичное состояние цикла. |
| `binary_sensor.<device>_running` | Включён в состояниях `running` и `final_spin`. |
| `binary_sensor.<device>_finished` | Включён в состоянии `finished`. |
| `binary_sensor.<device>_final_spin_detected` | Фиксируется при обнаружении данных о завершающем отжиме во время цикла. |
| `sensor.<device>_cycle_started_at` | Время начала активного цикла; интерфейс может вычислять длительность локально без периодической записи состояний. |
| `sensor.<device>_current_cycle_duration` | Устаревающий снимок длительности (по умолчанию отключён для новых установок, не является онлайн-таймером). |
| `sensor.<device>_last_cycle_duration` | Длительность последнего завершённого цикла. |
| `sensor.<device>_last_cycle_energy` | Энергопотребление последнего цикла при настроенном источнике энергии. |

#### Отслеживание белья

Доступно при включённом отслеживании белья:

| Сущность | Описание |
| --- | --- |
| `binary_sensor.<device>_laundry_present` | Считается ли, что бельё всё ещё находится в машине. |
| `button.<device>_mark_unloaded` | Явно отмечает бельё как извлечённое. |
| `sensor.<device>_last_unloaded_at` | Метка времени последнего явного извлечения белья. |

Открытие дверцы **не** означает автоматически, что бельё было извлечено.

#### Диагностические сущности

Для уменьшения нагрузки на Recorder часто меняющиеся отладочные сущности
по умолчанию отключены в новых установках (существующие настройки реестра
сохраняются). Подробную мощность/ток, метки активности, свидетельства отжима
и таймеры завершения включайте только при необходимости. Неизменившиеся
состояния не публикуются повторно. `cycle_started_at` публикуется при
начале цикла и очищается после его завершения, а интерфейс может вычислять
прошедшее время локально. Старая `current_cycle_duration` отключена
по умолчанию; даже при включении она обновляется только при смене
состояния/фазы, а не по таймеру. Внутренние детекторы и скачиваемая
диагностика работают с прежней точностью.

Laundry Monitor также предоставляет диагностические сущности, в частности:

- причину и метку времени последнего перехода;
- текущую мощность;
- опциональный потребляемый ток;
- объединённую значимую активность;
- отдельные состояния активности по мощности и току;
- метки времени последней объединённой активности, активности по мощности и по току;
- уверенность в завершающем отжиме и количество свидетельств;
- состояние кандидата на электрический отжим и метку времени кандидата;
- взвешенные по времени скользящие медианы мощности и, опционально, тока;
- свежесть электрического источника и наблюдаемое покрытие в загружаемой диагностике;
- путь подтверждения завершающего отжима (`vibration_only` или `hybrid`);
- метку времени начала отсутствия активности перед завершением, крайний срок и оставшееся время;
- счётчики отклонённых переходов;
- опциональное состояние протечки.

Эти диагностические сущности намеренно подробны на этапе разработки и полевых испытаний.

### События

**Мониторинг стирки** генерирует события Home Assistant для значимых наблюдений и переходов жизненного цикла:

| Событие | Когда генерируется |
| --- | --- |
| `laundry_monitor.cycle_started` | Начало цикла подтверждено. |
| `laundry_monitor.final_spin_detected` | Подтверждены данные о вероятном завершающем отжиме. |
| `laundry_monitor.cycle_finished` | Завершение цикла подтверждено. |
| `laundry_monitor.door_opened_after_finish` | Дверца открыта, пока цикл остаётся в состоянии `finished`. |
| `laundry_monitor.machine_unloaded` | Бельё явно отмечено как извлечённое. |
| `laundry_monitor.leak_detected` | Опциональный источник протечки стал активным. |
| `laundry_monitor.state_changed` | Изменилось публичное состояние цикла. |
| `laundry_monitor.transition_rejected` | Запрошен недопустимый переход между состояниями. |

Полезные данные событий включают идентификатор записи конфигурации, настроенное имя машины, метку времени и свидетельства, относящиеся к конкретному событию.

#### Пример автоматизации

```yaml
automation:
  - alias: "Стирка завершена"
    trigger:
      - platform: event
        event_type: laundry_monitor.cycle_finished
    action:
      - service: notify.mobile_app_phone
        data:
          message: "Стиральная машина завершила работу."
```

Сам **Мониторинг стирки** намеренно не отправляет уведомления; автоматизации используют его состояния и события.

### Как работает обнаружение

Исходные состояния источников Home Assistant проверяются и нормализуются перед оценкой детекторами.

```text
Мощность + опциональный ток
        │
        ▼
 Детектор активности
        │
        ├──────────────► Детектор отжима + вибрация
        │
        └──────────────► Детектор завершения
                               │
                               ▼
                         Конечный автомат
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
              Сущности      События      Диагностика
```

Важные правила проектирования:

- Мощность остаётся обязательным и авторитетным источником для подтверждения начала цикла.
- Опциональный ток предоставляет дополнительные свидетельства значимой активности.
- Опциональный ток сам по себе не может подтвердить начало цикла, завершающий отжим или завершение.
- Вне цикла с нагревом и включённым гибридным подтверждением остаётся доступным путь только по вибрации с полным набором данных; он использует настроенное требование к полному объёму данных о вибрации.
- При явном включении экспериментальный гибридный детектор также наблюдает за мощностью на уровне нагрева как контекстом цикла.
- Подтверждённый активный нагрев блокирует подтверждение `final_spin`, пока присутствует характерный профиль нагревателя.
- После обнаружения нагрева гибридное подтверждение с уменьшенным объёмом данных не разрешается, пока не достигнут настроенный минимальный возраст цикла с нагревом.
- Если гибридное подтверждение включено и нагрев зафиксирован как `detected`, полный набор данных о вибрации больше не является независимым путём подтверждения: после окончания активного нагрева он всё равно требует нового устойчивого кандидата на электрический отжим и соблюдения временного ограничения для цикла с нагревом.
- Если в начале цикла наблюдается достаточное покрытие действительными данными мощности без какого-либо профиля нагрева, ускоренный гибридный путь без нагрева может обойти обычное требование к минимальному возрасту цикла, но только при полном объёме данных о вибрации и наличии нового устойчивого кандидата на электрический отжим.
- Отсутствующие или устаревшие данные мощности в начале цикла не должны интерпретироваться как свидетельство отсутствия нагрева.
- Одни только электрические данные никогда не могут подтвердить `final_spin`.
- В гибридном цикле с нагревом кандидат на электрический отжим должен созревать в течение 45 секунд, и по крайней мере один фронт вибрации должен произойти в момент начала этого кандидата или позже, прежде чем он сможет подтвердить `final_spin`.
- Устаревшие электрические выборки не должны продолжать поддерживать электрического кандидата после настроенного максимального возраста источника.
- Завершение определяется по отсутствию значимой электрической активности с течением времени, а не по точному значению мощности в режиме ожидания.
- Опциональная вибрация предоставляет свидетельства завершающего отжима.
- Обнаружение протечки работает независимо и не изменяет состояние цикла.
- Отслеживание белья работает независимо от обнаружения цикла.
- Отсутствие опциональных источников не должно останавливать базовое обнаружение цикла.
- Отсутствующие данные датчиков не должны интерпретироваться как нулевые значения или отсутствие активности.

Подробное поведение и инварианты приведены в канонической английской документации.

### Документация проекта

- [`PROJECT_MAP.md`](PROJECT_MAP.md) — краткий навигатор: задача → спецификация → реализация → тесты.
- [`docs/en/SPECIFICATION.md`](docs/en/SPECIFICATION.md) — каноническая спецификация продукта и модель обнаружения.
- [`docs/en/ARCHITECTURE.md`](docs/en/ARCHITECTURE.md) — границы компонентов и поток данных.
- [`docs/en/REQUIREMENTS.md`](docs/en/REQUIREMENTS.md) — нормативные функциональные и нефункциональные требования.
- [`docs/en/STATE_MACHINE.md`](docs/en/STATE_MACHINE.md) — подробные публичные и внутренние состояния, переходы, таймеры, восстановление, пограничные случаи и инварианты.
- [`docs/en/USER_MANUAL.md`](docs/en/USER_MANUAL.md) — руководство пользователя на английском языке.
- [`docs/ru/USER_MANUAL.md`](docs/ru/USER_MANUAL.md) — руководство пользователя на русском языке.

При поиске сведений о реализации начните с [`PROJECT_MAP.md`](PROJECT_MAP.md), а не с просмотра всего репозитория. Канонической всегда остаётся английская документация.

### Устранение неполадок

#### Включение журнала отладки

Откройте интеграцию в Home Assistant и используйте **Enable debug logging** («Включить журнал отладки»). Воспроизведите проблему, затем остановите запись журнала отладки, чтобы получить трассировку.

В журнал работы записываются подтверждение запуска, решения об активности, переходы между состояниями, свидетельства отжима, оценка завершения, планирование таймеров, сбои источников и поведение при восстановлении.

#### Загрузка диагностики

Используйте **Download diagnostics** («Загрузить диагностику») для интеграции или устройства, чтобы получить моментальный снимок:

- настроенных источников и их доступности;
- состояния во время работы;
- порогов и свидетельств детекторов;
- таймеров жизненного цикла;
- статистики циклов;
- сохранённого снимка состояния;
- информации об отклонённых переходах.

В скачиваемом разделе `sources` поле `available` означает пригодность измерения для Laundry Monitor, а `entity_available` — наличие состояния сущности HA, отличного от `unknown`/`unavailable`. Числовое значение мощности с неподдерживаемой единицей может иметь `entity_available=true` и `available=false`; тогда обязательный источник попадает в `required_sources_unavailable`. Исходные значения, единицы и временные метки сохраняются.

#### Repairs

Если обязательный источник мощности остаётся недоступным, Laundry Monitor может создать проблему в Home Assistant Repairs. Кратковременные перебои допускаются в соответствии с настроенным периодом задержки.

### Чем Мониторинг стирки не является

**Мониторинг стирки** не является:

- контроллером стиральной машины;
- интеграцией для бытовой техники конкретного производителя;
- службой уведомлений;
- автоматическим контроллером безопасности умной розетки;
- монитором посудомоечной машины;
- монитором сушильной машины;
- универсальным монитором бытовой техники.

Используйте автоматизации Home Assistant, чтобы создавать действия на основе состояний и событий Laundry Monitor.

### Участие в разработке

Сообщения о проблемах и pull request приветствуются.

Перед созданием pull request запустите закреплённую версию Ruff
в режиме проверки (без исправлений), а затем тесты:

```bash
python -m pip install ruff==0.16.8
python -m pip install -r requirements_test.txt
ruff check custom_components tests --select E,W,F
python -m pytest
```

Полный набор тестов запускается на **Home Assistant Core 2026.10.4**
с `pytest-homeassistant-custom-component==0.13.375` (Python 3.14).
Для минимально поддерживаемой версии **Core 2026.6.0** предусмотрен
отдельный smoke-набор с `pytest-homeassistant-custom-component==0.13.336`.
Тестовые пакеты привязаны к **точным версиям Core**: смешивать их нельзя.
CI выводит и сверяет установленную и импортированную версии Home Assistant;
при несовпадении с заданной версией матрицы задача завершается ошибкой.

Для локальной проверки минимальной версии создайте **отдельное виртуальное
окружение Python 3.14** и выполните:

```bash
python -m pip install -r requirements_test_min.txt
python -m pip check
python -m pytest -vv \
  tests/components/laundry_monitor/test_source_freshness_runtime.py \
  tests/components/laundry_monitor/test_measurement_units.py \
  tests/components/laundry_monitor/test_config_flow.py \
  tests/components/laundry_monitor/test_storage_integration.py
```

Минимальный smoke-набор проверяет повторные электрические отчёты
`state_reported`, нормализацию Вт/А и некорректные единицы, настройку
интеграции и восстановление snapshot. Для актуальной проверяемой версии
запускается **полный набор тестов**. Обе задачи выполняются для каждого
PR (включая изменения только документации), при push в `main` и по
расписанию вместе с Ruff, Hassfest и HACS.

**Порядок обновления:** минимум раз в месяц после стабильного релиза
Home Assistant проверяйте последнюю версию Core и доступный тестовый
пакет. Продвигайте актуальную проверяемую версию только после выпуска
совместимой пары Core/fixture, закрепляя обе версии вместе, запуская CI
и обновляя README. Новейший Core **не считается проверенным**, пока
для него нет подтверждённой совместимой тестовой среды. Минимальный
Core 2026.6.0 сохраняется до официального изменения порога HACS.

Задача `Validate / Ruff check` запускается для **каждого PR**, включая
изменения только документации, и при push в `main`. Безопасные исправления
можно выполнять локально в рабочей ветке через
`ruff check custom_components tests --select E,W,F --fix`, после чего
нужно проверить diff и отправить его на ревью в PR. Не запускайте
автоматически `--unsafe-fixes` и не публикуйте исправления напрямую в
`main`. Проверяющий workflow не имеет прав на запись в репозиторий.

Для владельца репозитория: настройте protection/rulesets для `main`,
сделайте статус `Ruff check` обязательным (при необходимости вместе с
`Tests`, `Hassfest` и `HACS`), запретите обход правил и прямые изменения
`main` без проверенного PR. Сам workflow не включает защиту ветки — это
отдельная настройка GitHub.

Английская документация в `docs/en/` является канонической. Переводы должны следовать ей и не должны определять отдельное поведение.

На раннем этапе разработки при изменении поведения детекторов или конечного автомата поддерживайте синхронность документации, поведения во время работы, тестов, переводов и [`PROJECT_MAP.md`](PROJECT_MAP.md).

### Лицензия

Выпущено под [лицензией MIT](LICENSE).

**[English](#Laundry-Monitor) | [Русский](#Мониторинг-стирки)**
