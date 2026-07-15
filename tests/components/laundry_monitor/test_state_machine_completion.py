"""Test completed Laundry Monitor state-machine lifecycle."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import (
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.laundry_monitor.const import (
    CONF_ARMING_TIMEOUT,
    CONF_DOOR_SENSOR,
    CONF_FINISHED_RETENTION,
    CONF_POWER_SENSOR,
    CONF_POWER_UNAVAILABLE_GRACE,
    CONF_RUNNING_FINISH_CONFIRMATION,
    CONF_START_CONFIRMATION,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    EVENT_CYCLE_STARTED,
    EVENT_DOOR_OPENED_AFTER_FINISH,
    LaundryCycleState,
    REASON_ACTIVITY_RESUMED_AFTER_FINAL_SPIN,
    REASON_ARMING_TIMEOUT,
    REASON_FINISHED_RETENTION_EXPIRED,
    REASON_FINISH_FALLBACK_CONFIRMED,
    REASON_POWER_ABOVE_START_THRESHOLD,
    REASON_POWER_SENSOR_RECOVERED,
    REASON_POWER_SENSOR_UNAVAILABLE,
)


async def _async_setup_entry(
    hass: HomeAssistant,
    *,
    tracking: bool = False,
    include_door: bool = False,
    include_vibration: bool = False,
    door_state: str = STATE_OFF,
    power: str = "0.25",
    options: dict[str, int | float] | None = None,
) -> MockConfigEntry:
    """Set up one configurable test entry."""
    hass.states.async_set("sensor.washing_machine_power", power)

    data: dict[str, object] = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_TRACK_LAUNDRY: tracking,
    }

    if include_door:
        hass.states.async_set(
            "binary_sensor.washing_machine_door",
            door_state,
        )
        data[CONF_DOOR_SENSOR] = "binary_sensor.washing_machine_door"

    if include_vibration:
        hass.states.async_set(
            "binary_sensor.washing_machine_vibration",
            STATE_OFF,
        )
        data[CONF_VIBRATION_SENSOR] = (
            "binary_sensor.washing_machine_vibration"
        )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
        options=options or {},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_finished_auto_resets_when_tracking_disabled(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test finished is observable but cannot become a trap."""
    entry = await _async_setup_entry(
        hass,
        tracking=False,
        options={CONF_FINISHED_RETENTION: 5},
    )
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_start",
    )
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finish",
    )
    await hass.async_block_till_done()

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=6))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert (
        runtime.last_transition_reason
        == REASON_FINISHED_RETENTION_EXPIRED
    )
    assert runtime.laundry_present is False


async def test_tracking_enabled_keeps_finished_until_explicit_action(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test completed-state retention does not override tracking."""
    entry = await _async_setup_entry(
        hass,
        tracking=True,
        options={CONF_FINISHED_RETENTION: 1},
    )
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_start",
    )
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finish",
    )

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=10))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.FINISHED
    assert runtime.laundry_present is True


async def test_new_cycle_is_detected_from_finished(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a forgotten unload cannot block the next cycle."""
    entry = await _async_setup_entry(
        hass,
        tracking=True,
        options={
            CONF_START_CONFIRMATION: 2,
            CONF_FINISHED_RETENTION: 3600,
        },
    )
    runtime = entry.runtime_data

    events = []

    @callback
    def _capture_cycle_started(event) -> None:
        events.append(event)

    hass.bus.async_listen(
        EVENT_CYCLE_STARTED,
        _capture_cycle_started,
    )

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "first_cycle",
    )
    first_started_at = runtime.cycle_started_at
    assert first_started_at is not None
    runtime.cycle_started_at = first_started_at - timedelta(days=1)
    sentinel_started_at = runtime.cycle_started_at
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "first_cycle_finished",
    )

    hass.states.async_set("sensor.washing_machine_power", "45")
    await hass.async_block_till_done()
    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.cycle_started_at is not None
    assert runtime.cycle_started_at != sentinel_started_at
    assert len(events) == 1
    assert events[0].data["old_state"] == "finished"
    assert events[0].data["new_state"] == "running"


async def test_activity_resumes_after_final_spin(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test renewed meaningful activity returns final_spin to running."""
    entry = await _async_setup_entry(
        hass,
        include_vibration=True,
        power="45",
    )
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_running",
    )
    started_at = runtime.cycle_started_at
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "test_final_spin",
    )

    hass.states.async_set("sensor.washing_machine_power", "0.25")
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN

    hass.states.async_set("sensor.washing_machine_power", "45")
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert (
        runtime.last_transition_reason
        == REASON_ACTIVITY_RESUMED_AFTER_FINAL_SPIN
    )
    assert runtime.cycle_started_at == started_at


async def test_running_finishes_without_vibration_sensor(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test conservative power-only finish fallback."""
    entry = await _async_setup_entry(
        hass,
        power="45",
        options={CONF_RUNNING_FINISH_CONFIRMATION: 60},
    )
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_running",
    )

    hass.states.async_set("sensor.washing_machine_power", "0.25")
    await hass.async_block_till_done()
    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=61))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.FINISHED
    assert (
        runtime.last_transition_reason
        == REASON_FINISH_FALLBACK_CONFIRMED
    )


async def test_arming_timeout_returns_to_idle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test an ordinary door close cannot leave armed indefinitely."""
    entry = await _async_setup_entry(
        hass,
        include_door=True,
        door_state=STATE_ON,
        options={CONF_ARMING_TIMEOUT: 5},
    )
    runtime = entry.runtime_data

    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.ARMED

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=6))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.last_transition_reason == REASON_ARMING_TIMEOUT


async def test_power_unavailable_enters_error_and_recovers(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test minimal required-power error lifecycle."""
    entry = await _async_setup_entry(
        hass,
        power="45",
        options={CONF_POWER_UNAVAILABLE_GRACE: 5},
    )
    runtime = entry.runtime_data
    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_running",
    )

    hass.states.async_set(
        "sensor.washing_machine_power",
        STATE_UNAVAILABLE,
    )
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.RUNNING

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=6))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.ERROR
    assert (
        runtime.last_transition_reason
        == REASON_POWER_SENSOR_UNAVAILABLE
    )

    hass.states.async_set("sensor.washing_machine_power", "0.25")
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.last_transition_reason == REASON_POWER_SENSOR_RECOVERED


async def test_door_opened_after_finish_event_is_emitted(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the declared post-finish door event is reachable."""
    entry = await _async_setup_entry(
        hass,
        tracking=True,
        include_door=True,
        door_state=STATE_OFF,
    )
    runtime = entry.runtime_data
    events = []

    @callback
    def _capture_door_event(event) -> None:
        events.append(event)
        
    hass.bus.async_listen(
        EVENT_DOOR_OPENED_AFTER_FINISH,
        _capture_door_event,
    )

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_running",
    )
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )

    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_ON,
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["config_entry_id"] == entry.entry_id
    assert "timestamp" in events[0].data


async def test_existing_high_power_is_evaluated_on_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test setup detects an already-running machine without a new event."""
    entry = await _async_setup_entry(
        hass,
        power="45",
        options={CONF_START_CONFIRMATION: 2},
    )
    runtime = entry.runtime_data

    assert runtime.cycle_state is LaundryCycleState.IDLE

    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert (
        runtime.last_transition_reason
        == REASON_POWER_ABOVE_START_THRESHOLD
    )
