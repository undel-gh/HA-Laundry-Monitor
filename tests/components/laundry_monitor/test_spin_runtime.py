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

from custom_components.laundry_monitor.storage import RuntimeSnapshot

async def _setup_entry(
    hass: HomeAssistant,
    *,
    start_running: bool = True,
    with_current: bool = False,
    hybrid_enabled: bool = False,
    electrical_power_threshold: float | None = None,
    electrical_current_threshold: float | None = None,
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
            CONF_SPIN_MIN_CYCLE_TIME: 0,
            CONF_HYBRID_SPIN_ENABLED: hybrid_enabled,
            CONF_HYBRID_SPIN_REQUIRED_EVENTS: 2,
            **(
                {CONF_ELECTRICAL_SPIN_POWER_THRESHOLD: electrical_power_threshold}
                if electrical_power_threshold is not None
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
    """Two vibration events can confirm spin with sustained electrical evidence."""
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
    )
    runtime = entry.runtime_data

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
    )
    runtime = entry.runtime_data
    now = dt_util.utcnow()
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
    assert runtime.final_spin_confirmation_path is None
