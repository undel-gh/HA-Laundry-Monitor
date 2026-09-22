"""Test Spin Detector integration with Laundry Monitor runtime."""

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_CURRENT_ACTIVITY_THRESHOLD,
    CONF_CURRENT_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_ELECTRICAL_SPIN_CURRENT_THRESHOLD,
    CONF_ELECTRICAL_SPIN_POWER_THRESHOLD,
    CONF_HEATED_CYCLE_MIN_TIME,
    CONF_HEATING_CONFIRMATION,
    CONF_HEATING_OBSERVATION,
    CONF_HEATING_POWER_THRESHOLD,
    CONF_HYBRID_SPIN_ENABLED,
    CONF_HYBRID_SPIN_REQUIRED_EVENTS,
    CONF_POWER_SENSOR,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
    REASON_FINAL_SPIN_CONFIRMED,
)

from custom_components.laundry_monitor.heating import HeatingState
from custom_components.laundry_monitor.storage import RuntimeSnapshot


async def _setup_entry(
    hass: HomeAssistant,
    *,
    start_running: bool = True,
    with_current: bool = False,
    hybrid_enabled: bool = False,
    electrical_power_threshold: float | None = None,
    electrical_current_threshold: float | None = None,
    heating_power_threshold: float | None = None,
    heating_confirmation: int = 10,
    heating_observation: int = 20,
    heated_cycle_min_time: int = 0,
    spin_min_cycle_time: int = 0,
) -> MockConfigEntry:
    """Set up a Spin Detector test entry."""
    hass.states.async_set(
        "sensor.washing_machine_power",
        "0.25" if with_current else "45",
    )
    if with_current:
        hass.states.async_set("sensor.washing_machine_current", "0.5")
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )

    data = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR:
            "binary_sensor.washing_machine_vibration",
        CONF_TRACK_LAUNDRY: True,
    }
    if with_current:
        data[CONF_CURRENT_SENSOR] = "sensor.washing_machine_current"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
        options={
            CONF_SPIN_REQUIRED_EVENTS: 3,
            CONF_SPIN_WINDOW: 180,
            CONF_SPIN_MIN_CYCLE_TIME: spin_min_cycle_time,
            CONF_HEATING_CONFIRMATION: heating_confirmation,
            CONF_HEATING_OBSERVATION: heating_observation,
            CONF_HEATED_CYCLE_MIN_TIME: heated_cycle_min_time,
            CONF_HYBRID_SPIN_ENABLED: hybrid_enabled,
            CONF_HYBRID_SPIN_REQUIRED_EVENTS: 2,
            **(
                {CONF_ELECTRICAL_SPIN_POWER_THRESHOLD: electrical_power_threshold}
                if electrical_power_threshold is not None
                else {}
            ),
            **(
                {CONF_HEATING_POWER_THRESHOLD: heating_power_threshold}
                if heating_power_threshold is not None
                else {}
            ),
            **(
                {CONF_CURRENT_ACTIVITY_THRESHOLD: 0.1}
                if with_current
                else {}
            ),
            **(
                {
                    CONF_ELECTRICAL_SPIN_CURRENT_THRESHOLD:
                        electrical_current_threshold
                }
                if with_current and electrical_current_threshold is not None
                else {}
            ),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    if start_running:
        assert entry.runtime_data.async_set_cycle_state(
            LaundryCycleState.RUNNING,
            "test_running",
        )
        await hass.async_block_till_done()

    return entry


def _mark_heating_not_seen(runtime, now) -> None:
    """Accumulate enough fresh low-power coverage for NOT_SEEN."""
    runtime.heating_detector.reset(
        now=now - timedelta(seconds=20),
        power=45.0,
    )
    result = runtime.heating_detector.evaluate(
        power=45.0,
        power_updated=False,
        now=now,
    )
    assert result.state is HeatingState.NOT_SEEN


async def _vibration_pulse(hass: HomeAssistant) -> None:
    """Generate one binary vibration pulse."""
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_ON,
    )
    await hass.async_block_till_done()
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )
    await hass.async_block_till_done()


async def test_repeated_vibration_transitions_to_final_spin(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test running -> final_spin after repeated vibration."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    await _vibration_pulse(hass)
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 1

    await _vibration_pulse(hass)
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 2

    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.last_transition_reason == REASON_FINAL_SPIN_CONFIRMED
    assert runtime.final_spin_evidence_count == 3
    assert runtime.final_spin_confidence == 1.0
    assert runtime.final_spin_confirmation_path == "vibration_only"


async def test_vibration_is_ignored_outside_running(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that vibration cannot change idle state."""
    entry = await _setup_entry(
        hass,
        start_running=False,
    )
    runtime = entry.runtime_data

    assert runtime.cycle_state is LaundryCycleState.IDLE

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.final_spin_evidence_count == 0
    assert runtime.rejected_transition_count == 0


async def test_current_activity_can_support_spin_context(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test current supports vibration evidence when power is quiet."""
    entry = await _setup_entry(hass, with_current=True)
    runtime = entry.runtime_data

    assert runtime.power_activity_detected is False
    assert runtime.current_activity_detected is True

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.last_transition_reason == REASON_FINAL_SPIN_CONFIRMED


async def test_current_cannot_replace_unavailable_power_for_spin(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test current cannot confirm spin without the required power source."""
    entry = await _setup_entry(hass, with_current=True)
    runtime = entry.runtime_data

    hass.states.async_set(
        "sensor.washing_machine_power",
        "unavailable",
    )
    await hass.async_block_till_done()

    assert runtime.power is None
    assert runtime.current_activity_detected is True

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 0
    assert runtime.final_spin_confidence == 0.0


async def test_hybrid_path_is_disabled_by_default(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Two vibration events plus electrical evidence do nothing by default."""
    entry = await _setup_entry(
        hass,
        electrical_power_threshold=100.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=30),
        power=150.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    assert runtime.spin_electrical_candidate is True
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 2
    assert runtime.final_spin_confirmation_path is None


async def test_hybrid_path_confirms_after_two_vibration_events(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Two vibration events can confirm mature non-heated hybrid spin."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    _mark_heating_not_seen(runtime, now)
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=30),
        power=150.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    assert runtime.spin_electrical_candidate is True
    await _vibration_pulse(hass)
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_evidence_count == 2
    assert runtime.final_spin_confirmation_path == "hybrid"
    assert runtime.final_spin_confidence < 1.0


async def test_hybrid_path_requires_electrical_candidate(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Reduced vibration evidence cannot confirm spin without electricity."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    _mark_heating_not_seen(runtime, dt_util.utcnow())

    assert runtime.spin_electrical_candidate is False
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 2
    assert runtime.final_spin_confirmation_path is None


async def test_hybrid_path_reports_current_corroboration(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Current corroboration remains diagnostic while hybrid confirms."""
    entry = await _setup_entry(
        hass,
        with_current=True,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        electrical_current_threshold=0.7,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    _mark_heating_not_seen(runtime, now)
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=20),
        power=150.0,
        current=1.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    hass.states.async_set("sensor.washing_machine_current", "1.0")
    await hass.async_block_till_done()

    assert runtime.spin_electrical_candidate is True
    assert runtime.electrical_spin_detector.current_corroborated is True
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_confirmation_path == "hybrid"

async def test_legacy_hybrid_without_heating_threshold_fails_closed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Old hybrid options cannot use reduced evidence after the upgrade."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=30),
        power=150.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.spin_gate_reason == "hybrid_heating_not_configured"

    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_confirmation_path == "vibration_only"


async def test_active_heating_blocks_even_full_vibration_path(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """FR-051: current heater-level power is a hard terminal-spin gate."""
    entry = await _setup_entry(
        hass,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data

    hass.states.async_set("sensor.washing_machine_power", "1800")
    await hass.async_block_till_done()
    assert runtime.heating_detector.heating_active is True

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 3
    assert runtime.spin_gate_reason == "heating_active"

    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_confirmation_path == "vibration_only"


async def test_heated_cycle_delays_reduced_hybrid_confirmation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """FR-052: detected heating activates the stricter hybrid age gate."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
        spin_min_cycle_time=600,
        heated_cycle_min_time=900,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    runtime.heating_detector.restore_detected(now - timedelta(minutes=10))
    runtime.cycle_started_at = now - timedelta(minutes=12)
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=30),
        power=150.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.spin_gate_reason == "heated_cycle_too_young"

    runtime.cycle_started_at = dt_util.utcnow() - timedelta(minutes=16)
    assert runtime._evaluate_spin()

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_confirmation_path == "hybrid"
    assert runtime.final_spin_hybrid_variant == "reduced"


async def test_fast_non_heated_path_requires_full_vibration_evidence(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """FR-053: early no-heating confirmation still needs full vibration."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
        spin_min_cycle_time=600,
        heated_cycle_min_time=900,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    _mark_heating_not_seen(runtime, now)
    runtime.cycle_started_at = now - timedelta(minutes=2)
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=30),
        power=150.0,
    )
    hass.states.async_set("sensor.washing_machine_power", "150")
    await hass.async_block_till_done()

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.spin_gate_reason == "fast_path_requires_full_vibration"

    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.final_spin_confirmation_path == "hybrid"
    assert runtime.final_spin_hybrid_variant == "fast_non_heated"


async def test_electrical_candidate_resets_when_cycle_finishes(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Electrical history cannot leak into the next lifecycle state."""
    entry = await _setup_entry(
        hass,
        electrical_power_threshold=100.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=20),
        power=150.0,
    )
    runtime.electrical_spin_detector.evaluate(
        power=150.0,
        current=None,
        power_updated=False,
        current_updated=False,
        now=now,
    )
    assert runtime.spin_electrical_candidate is True

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )

    assert runtime.spin_electrical_candidate is False
    assert runtime.spin_power_rolling_median is None
    assert runtime.electrical_spin_detector.power_coverage_seconds == 0.0


async def test_snapshot_recovery_discards_electrical_and_confirmation_path(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Restart recovery requires fresh electrical data and loses path metadata."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    runtime.electrical_spin_detector.reset(
        now=now - timedelta(seconds=20),
        power=150.0,
    )
    runtime.electrical_spin_detector.evaluate(
        power=150.0,
        current=None,
        power_updated=False,
        current_updated=False,
        now=now,
    )
    runtime.final_spin_confirmation_path = "hybrid"
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(minutes=1),
        cycle_started_at=now - timedelta(minutes=10),
        laundry_present=True,
    )
    runtime.state_store.async_get = AsyncMock(return_value=snapshot)

    await runtime._async_restore_snapshot()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.spin_electrical_candidate is False
    assert runtime.spin_power_rolling_median is None
    assert runtime.electrical_spin_detector.power_source_fresh is False
    assert runtime.heating_state is HeatingState.UNKNOWN
    assert runtime.heating_detector.power_source_fresh is False
    assert runtime.final_spin_confirmation_path is None


async def test_snapshot_recovery_restores_latched_heating_fact(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """FR-055: reliably detected heating survives safe restart recovery."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    detected_at = now - timedelta(minutes=8)
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(minutes=1),
        cycle_started_at=now - timedelta(minutes=12),
        laundry_present=True,
        heating_detected=True,
        heating_detected_at=detected_at,
    )
    runtime.state_store.async_get = AsyncMock(return_value=snapshot)

    await runtime._async_restore_snapshot()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.heating_state is HeatingState.DETECTED
    assert runtime.heating_detector.detected_at == detected_at
    assert runtime.heating_detector.heating_active is False
    assert runtime.heating_detector.power_source_fresh is False


async def test_snapshot_recovery_restores_matching_not_seen_and_vibration_window(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Safe recovery preserves proven no-heating context and live edges."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    evidence = (
        now - timedelta(seconds=120),
        now - timedelta(seconds=60),
    )
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(seconds=5),
        cycle_started_at=now - timedelta(minutes=12),
        laundry_present=True,
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=runtime.heating_detector.power_threshold_w,
        heating_confirmation_seconds=(
            runtime.heating_detector.confirmation_seconds
        ),
        heating_observation_seconds=(
            runtime.heating_detector.observation_seconds
        ),
        heating_max_source_age_seconds=(
            runtime.heating_detector.max_source_age_seconds
        ),
        spin_evidence_timestamps=evidence,
    )
    runtime.state_store.async_get = AsyncMock(return_value=snapshot)

    await runtime._async_restore_snapshot()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.heating_state is HeatingState.NOT_SEEN
    assert runtime.heating_detector.heating_active is False
    assert runtime.heating_detector.power_source_fresh is False
    assert runtime.final_spin_evidence_count == 2
    assert runtime.spin_detector.snapshot_evidence(
        now=dt_util.utcnow()
    ) == evidence


async def test_snapshot_recovery_discards_not_seen_when_parameters_changed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Changed heating calibration invalidates persisted NOT_SEEN."""
    entry = await _setup_entry(
        hass,
        hybrid_enabled=True,
        electrical_power_threshold=100.0,
        heating_power_threshold=1000.0,
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
    snapshot = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(seconds=5),
        cycle_started_at=now - timedelta(minutes=12),
        laundry_present=True,
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=900.0,
        heating_confirmation_seconds=(
            runtime.heating_detector.confirmation_seconds
        ),
        heating_observation_seconds=(
            runtime.heating_detector.observation_seconds
        ),
        heating_max_source_age_seconds=(
            runtime.heating_detector.max_source_age_seconds
        ),
        spin_evidence_timestamps=(
            now - timedelta(seconds=181),
            now - timedelta(seconds=60),
        ),
    )
    runtime.state_store.async_get = AsyncMock(return_value=snapshot)

    await runtime._async_restore_snapshot()

    assert runtime.heating_state is HeatingState.UNKNOWN
    assert runtime.final_spin_evidence_count == 1
