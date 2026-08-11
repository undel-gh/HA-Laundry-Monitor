# HA-Laundry-Monitor — Project Map

Short navigation map for maintainers and assistants. Use this file to jump directly to the relevant implementation, tests, or design document instead of scanning the repository.

> Canonical behavior is documented in `docs/en/`. Implementation details live in `custom_components/laundry_monitor/`. Tests mirror the implementation under `tests/components/laundry_monitor/`.

## Project purpose

Home Assistant custom integration that infers washing-machine cycle state from external sensors. Power is the required source; current, door, vibration, leak, energy, and plug-switch sources are optional. Public cycle states are `idle`, `armed`, `running`, `final_spin`, `finished`, and `error`.

## Fast lookup by topic

| Topic / question | Read first | Implementation | Tests |
|---|---|---|---|
| Overall product behavior and scope | `docs/en/SPECIFICATION.md` | — | — |
| Architecture / component responsibilities | `docs/en/ARCHITECTURE.md` | package files below | — |
| Normative functional requirements | `docs/en/REQUIREMENTS.md` | — | — |
| States, transitions, timers, recovery, edge cases | `docs/en/STATEMACHINE.md` | `runtime.py`, `state_machine.py`, `storage.py` | `test_state_machine.py`, `test_state_machine_runtime.py`, `test_storage.py` |
| Power/current meaningful activity and cycle start | `SPECIFICATION.md §7.1`, `STATEMACHINE.md §5.1/§9` | `activity.py`, `runtime.py` | `test_activity.py`, `test_activity_runtime.py` |
| Terminal spin sequence / terminal phase | `SPECIFICATION.md §7.2`, `STATEMACHINE.md §8.4` | `spin.py`, `runtime.py` | `test_spin.py`, `test_spin_runtime.py` |
| Cycle finish / quiet timers / fallback finish | `SPECIFICATION.md §7.3`, `STATEMACHINE.md §10/§14` | `finish.py`, `runtime.py` | `test_finish.py`, `test_finish_runtime.py` |
| Door arming / unload behavior | `STATEMACHINE.md §8/§10` | `runtime.py`, `button.py` | `test_state_machine_runtime.py`, `test_entities.py` |
| Persisted state / restart recovery | `STATEMACHINE.md §13` | `storage.py`, `runtime.py` | `test_storage.py`, `test_state_machine_runtime.py` |
| Config flow / reconfigure / options validation | `SPECIFICATION.md §11` | `config_flow.py`, `const.py` | `test_config_flow.py` |
| HA entities exposed to users | `SPECIFICATION.md §9` | `sensor.py`, `binary_sensor.py`, `button.py`, `entity.py` | `test_entities.py` |
| Downloadable diagnostics | `SPECIFICATION.md` diagnostics sections | `diagnostics.py` | relevant diagnostics/entity tests |
| Repairs for required-source failures | `README.md` troubleshooting | `repairs.py`, `runtime.py` | runtime/init tests |
| Integration setup/unload | — | `__init__.py` | `test_init.py` |
| Constants, defaults, event/reason IDs | — | `const.py` | many tests import these constants |
| Localization | `SPECIFICATION.md` localization section | `translations/en.json`, `translations/ru.json` | `test_translations.py` |
| HACS / HA metadata | `README.md` | `manifest.json`, `hacs.json`, `brand/` | HACS/CI validation |
| CI and test execution | `README.md` contributing section | `.github/workflows/validate.yml`, `pytest.ini`, `requirements_test.txt` | entire test suite |

## Documentation

### `README.md`
Public-facing overview: features, installation, configuration, defaults, exposed entities/events, troubleshooting, and contributing instructions. Keep it concise; detailed behavior belongs in `docs/en/`.

### `docs/en/SPECIFICATION.md`
Canonical product specification. Defines scope/non-goals, inputs, public state model, detection concepts, entities/events, configuration, diagnostics, failure handling, roadmap, and open questions. Start here when deciding **what the integration should do**.

### `docs/en/ARCHITECTURE.md`
Component boundaries and data flow: source normalization → Activity Detector / Spin Detector / Finish Detector → State Machine, with Laundry Tracking, Leak Detector, statistics, diagnostics, and HA entities separated. Start here when deciding **which component should own new logic**.

### `docs/en/REQUIREMENTS.md`
Normative `FR-*` and `NFR-*` requirements. Use this to check whether a proposed implementation violates an explicit requirement. Terminal-phase rules are currently FR-029 through FR-037.

### `docs/en/STATEMACHINE.md`
Most detailed behavioral document. Defines public/internal states, allowed transitions, detector inputs, state entry/exit semantics, timers, source failures, restart recovery, invariants, edge cases, examples, and test expectations. Start here for any state-transition question.

### `docs/ru/`
Russian translations of project documentation. English `docs/en/` remains canonical; Russian docs must not define different behavior.

## Integration implementation — `custom_components/laundry_monitor/`

### `__init__.py`
Home Assistant integration entry point. Creates shared persistence/repairs infrastructure, constructs `LaundryMonitorRuntime`, forwards platform setup, handles reload/unload.

### `const.py`
Central constants and stable identifiers: config-entry keys, option keys, default thresholds/timeouts, platform list, public cycle-state enum, event names, transition-reason IDs, config-entry version.

**Use this file first when looking for a default value or stable string identifier.**

### `config_flow.py`
UI configuration, reconfiguration, and options flow. Validates selected source entities and detector/lifecycle options. This is where new user-configurable thresholds or source selectors must be wired into Home Assistant UI.

### `activity.py`
Activity Detector. Normalizes/evaluates power and optional current activity, cycle-start candidate state, source-specific activity state/timestamps, combined meaningful activity, and activity edges.

### `spin.py`
Spin Detector. Maintains vibration-event evidence/windowing, cycle-age gate, activity recency and confidence used to detect the probable terminal spin sequence.

### `finish.py`
Finish Detector. Evaluates sustained absence of meaningful activity and exposes quiet-period/deadline/confirmation information. Runtime uses separate confirmation durations for final-spin and running fallback paths.

### `state_machine.py`
Pure public-state transition authority. Defines legal transitions and transition result/status handling. It should not inspect raw Home Assistant sensor values.

### `runtime.py`
Main orchestration layer and the first implementation file to inspect for real behavior. Subscribes to source entities, maintains current runtime state, invokes detectors, schedules/cancels timers, applies state transitions, fires events, updates statistics/laundry tracking, handles source availability, restart restoration, and persistence.

**If documentation says a transition should happen but real Home Assistant behavior differs, inspect `runtime.py` first.**

Useful symbols/search anchors include:
- `_handle_power_update`
- `_handle_current_update`
- `_handle_door_update`
- `_evaluate_spin`
- `_evaluate_finish`
- `_schedule_start_confirmation`
- arming/finish/power-unavailable timer callbacks
- `async_set_cycle_state`

### `storage.py`
Persistent runtime snapshots and recovery-state selection after Home Assistant restart/reload. Check here for snapshot schema, age validation, state reconstruction, and persistence serialization.

### `entity.py`
Shared base entity/device metadata and common runtime-update wiring used by entity platforms.

### `sensor.py`
Sensor entities: public cycle state, durations/statistics, raw/diagnostic power/current values, last-activity timestamps, transition information, spin/finish diagnostics, etc.

### `binary_sensor.py`
Binary entities such as running, finished, final-spin-detected, meaningful activity/source-specific activity, laundry presence, and optional leak status.

### `button.py`
User action entities, principally explicit **Mark unloaded** behavior when Laundry Tracking is enabled.

### `diagnostics.py`
Home Assistant downloadable diagnostics. Serializes configured sources, availability/raw states, runtime/detector values, options, transitions, statistics, and persisted-state information for troubleshooting.

### `repairs.py`
Home Assistant Repairs support for actionable integration problems, especially required-source availability failures/recovery.

### `manifest.json`
Home Assistant integration metadata: domain/name/version requirements, integration type, dependencies/requirements, documentation/issue links as applicable.

### `translations/en.json`, `translations/ru.json`
User-visible translations for config/options flows, entity names, errors, and other HA UI strings. Keep key structure synchronized between languages.

### `brand/`
Integration branding assets used by Home Assistant/HACS validation.

## Tests — `tests/components/laundry_monitor/`

### `test_activity.py`
Unit tests for Activity Detector semantics: thresholds, power/current combination, activity edges and timestamps.

### `test_activity_runtime.py`
Runtime integration tests around source updates and activity/start behavior.

### `test_spin.py`
Unit tests for Spin Detector evidence accumulation, rolling window, cycle-age/activity gates, and detection confidence.

### `test_spin_runtime.py`
Runtime state transitions and event behavior driven by spin evidence.

### `test_finish.py`
Unit tests for Finish Detector quiet-period/deadline behavior.

### `test_finish_runtime.py`
Runtime finish confirmation, fallback finish, activity reset/cancel behavior, and finish-state transitions.

### `test_state_machine.py`
Legal/illegal public transition matrix and state-machine invariants.

### `test_state_machine_runtime.py`
End-to-end runtime transition scenarios: door arming, start, final spin, finish, reset/unload, error/recovery, timers and lifecycle behavior.

### `test_storage.py`
Snapshot serialization, persistence age/validation, and restart recovery decisions.

### `test_config_flow.py`
Config/reconfigure/options UI validation, duplicate or invalid source handling, and option constraints.

### `test_entities.py`
Entity creation, availability, state/value exposure, device linkage, and Laundry Tracking entities.

### `test_init.py`
Integration setup/unload/reload and runtime lifecycle.

### `test_translations.py`
Translation file validity and EN/RU key parity/expected strings.

## Repository support files

### `.github/workflows/validate.yml`
CI validation workflow. Check here when GitHub Actions/HACS/tests fail in CI but pass locally.

### `hacs.json`
HACS repository metadata/configuration.

### `pytest.ini`
Pytest configuration.

### `requirements_test.txt`
Python dependencies needed to run the test suite locally.

### `LICENSE`
MIT license.

## Recommended lookup order

For behavioral changes, use this order:

1. `docs/en/REQUIREMENTS.md` — is there a normative rule?
2. `docs/en/STATEMACHINE.md` — what exact state/timer behavior is intended?
3. `docs/en/SPECIFICATION.md` — broader product semantics and public API.
4. `docs/en/ARCHITECTURE.md` — which component owns the behavior?
5. `runtime.py` plus the relevant detector (`activity.py`, `spin.py`, `finish.py`) — what is actually implemented?
6. matching `test_*.py` files — what behavior is regression-protected?
7. `const.py` / `config_flow.py` — defaults, option keys and UI configuration.

For a bug report from real Home Assistant history, normally start with `runtime.py`, then the detector related to the evidence, and finally the matching runtime test file.

---

Maintenance rule: update this map when adding/removing/renaming a major module, public state, detector, configuration group, or documentation file. Avoid line-number references because they become stale; prefer section headings and symbol names.
