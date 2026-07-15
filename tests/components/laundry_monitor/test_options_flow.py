"""Test Laundry Monitor Options Flow."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_ACTIVITY_THRESHOLD,
    CONF_ARMING_TIMEOUT,
    CONF_FINISHED_RETENTION,
    CONF_FINISH_CONFIRMATION,
    CONF_POWER_SENSOR,
    CONF_POWER_UNAVAILABLE_GRACE,
    CONF_RUNNING_FINISH_CONFIRMATION,
    CONF_SNAPSHOT_MAX_AGE,
    CONF_SPIN_ACTIVITY_MAX_AGE,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_START_CONFIRMATION,
    CONF_START_THRESHOLD,
    CONF_TRACK_LAUNDRY,
    DEFAULT_ACTIVITY_THRESHOLD,
    DEFAULT_ARMING_TIMEOUT,
    DEFAULT_FINISHED_RETENTION,
    DEFAULT_FINISH_CONFIRMATION,
    DEFAULT_POWER_UNAVAILABLE_GRACE,
    DEFAULT_RUNNING_FINISH_CONFIRMATION,
    DEFAULT_SNAPSHOT_MAX_AGE,
    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
    DEFAULT_SPIN_MIN_CYCLE_TIME,
    DEFAULT_SPIN_REQUIRED_EVENTS,
    DEFAULT_SPIN_WINDOW,
    DEFAULT_START_CONFIRMATION,
    DEFAULT_START_THRESHOLD,
    DOMAIN,
)

DEFAULT_OPTIONS = {
    CONF_ACTIVITY_THRESHOLD: DEFAULT_ACTIVITY_THRESHOLD,
    CONF_START_THRESHOLD: DEFAULT_START_THRESHOLD,
    CONF_START_CONFIRMATION: DEFAULT_START_CONFIRMATION,
    CONF_SPIN_REQUIRED_EVENTS: DEFAULT_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW: DEFAULT_SPIN_WINDOW,
    CONF_SPIN_MIN_CYCLE_TIME: DEFAULT_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_ACTIVITY_MAX_AGE: DEFAULT_SPIN_ACTIVITY_MAX_AGE,
    CONF_FINISH_CONFIRMATION: DEFAULT_FINISH_CONFIRMATION,
    CONF_RUNNING_FINISH_CONFIRMATION: (
        DEFAULT_RUNNING_FINISH_CONFIRMATION
    ),
    CONF_ARMING_TIMEOUT: DEFAULT_ARMING_TIMEOUT,
    CONF_FINISHED_RETENTION: DEFAULT_FINISHED_RETENTION,
    CONF_POWER_UNAVAILABLE_GRACE: DEFAULT_POWER_UNAVAILABLE_GRACE,
    CONF_SNAPSHOT_MAX_AGE: DEFAULT_SNAPSHOT_MAX_AGE,
}

CUSTOM_OPTIONS = {
    CONF_ACTIVITY_THRESHOLD: 4.5,
    CONF_START_THRESHOLD: 12.5,
    CONF_START_CONFIRMATION: 45,
    CONF_SPIN_REQUIRED_EVENTS: 4,
    CONF_SPIN_WINDOW: 240,
    CONF_SPIN_MIN_CYCLE_TIME: 900,
    CONF_SPIN_ACTIVITY_MAX_AGE: 150,
    CONF_FINISH_CONFIRMATION: 240,
    CONF_RUNNING_FINISH_CONFIRMATION: 900,
    CONF_ARMING_TIMEOUT: 1200,
    CONF_FINISHED_RETENTION: 420,
    CONF_POWER_UNAVAILABLE_GRACE: 90,
    CONF_SNAPSHOT_MAX_AGE: 43200,
}


def _create_entry(
    *,
    options: dict[str, int | float] | None = None,
) -> MockConfigEntry:
    """Create a power-only Laundry Monitor test entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_TRACK_LAUNDRY: False,
        },
        options=options or {},
    )


async def test_options_flow_shows_defaults(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test all detector and lifecycle defaults."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {}
    assert result["data_schema"]({}) == DEFAULT_OPTIONS


async def test_options_flow_shows_saved_values(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test existing options are used as form defaults."""
    entry = _create_entry(options=CUSTOM_OPTIONS)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({}) == CUSTOM_OPTIONS


async def test_activity_threshold_cannot_exceed_start_threshold(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test validation of the two power thresholds."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **DEFAULT_OPTIONS,
            CONF_ACTIVITY_THRESHOLD: 20.0,
            CONF_START_THRESHOLD: 10.0,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_ACTIVITY_THRESHOLD: "activity_threshold_above_start"
    }
    assert entry.options == {}


async def test_options_are_saved_and_entry_is_reloaded(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test saved lifecycle settings recreate runtime modules."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    original_runtime = entry.runtime_data

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        CUSTOM_OPTIONS,
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CUSTOM_OPTIONS
    assert entry.options == CUSTOM_OPTIONS
    assert entry.state is ConfigEntryState.LOADED

    runtime = entry.runtime_data
    assert runtime is not original_runtime
    assert runtime.activity_detector.activity_threshold == 4.5
    assert runtime.activity_detector.start_threshold == 12.5
    assert runtime.start_confirmation_seconds == 45
    assert runtime.spin_detector.required_events == 4
    assert runtime.spin_detector.window_seconds == 240
    assert runtime.spin_detector.min_cycle_seconds == 900
    assert runtime.spin_detector.activity_max_age_seconds == 150
    assert runtime.finish_detector.confirmation_seconds == 240
    assert runtime.running_finish_detector.confirmation_seconds == 900
    assert runtime.arming_timeout_seconds == 1200
    assert runtime.finished_retention_seconds == 420
    assert runtime.power_unavailable_grace_seconds == 90
    assert runtime.snapshot_max_age_seconds == 43200
