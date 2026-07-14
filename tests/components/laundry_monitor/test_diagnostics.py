"""Test Laundry Monitor diagnostics."""

from __future__ import annotations

from homeassistant.const import CONF_NAME, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_ACTIVITY_THRESHOLD,
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_START_THRESHOLD,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
)
from custom_components.laundry_monitor.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


async def _async_setup_entry(
    hass: HomeAssistant,
) -> MockConfigEntry:
    """Set up a configured Laundry Monitor entry."""
    hass.states.async_set(
        "sensor.washing_machine_power",
        "0.25",
        {
            "device_class": "power",
            "state_class": "measurement",
            "unit_of_measurement": "W",
        },
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
        {"device_class": "door"},
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
        {"device_class": "vibration"},
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
            CONF_VIBRATION_SENSOR: (
                "binary_sensor.washing_machine_vibration"
            ),
            CONF_TRACK_LAUNDRY: True,
        },
        options={
            CONF_ACTIVITY_THRESHOLD: 4.5,
            CONF_START_THRESHOLD: 12.5,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    await hass.async_block_till_done()

    return entry


async def test_config_entry_diagnostics(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test config-entry diagnostics data."""
    entry = await _async_setup_entry(hass)

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        entry,
    )

    assert diagnostics["config_entry"]["title"] == "Washing Machine"
    assert diagnostics["config_entry"]["options"] == {
        CONF_ACTIVITY_THRESHOLD: 4.5,
        CONF_START_THRESHOLD: 12.5,
    }

    assert diagnostics["required_sources_unavailable"] == []

    power = diagnostics["sources"][CONF_POWER_SENSOR]
    assert power["configured"] is True
    assert power["required"] is True
    assert power["available"] is True
    assert power["state"] == "0.25"
    assert power["attributes"] == {
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "W",
    }

    assert diagnostics["runtime"]["cycle_state"] == "running"
    assert (
        diagnostics["runtime"]["state_machine_state"]
        == "running"
    )
    assert diagnostics["runtime"]["laundry_present"] is True

    assert (
        diagnostics["detectors"]["activity"]["activity_threshold"]
        == 4.5
    )
    assert (
        diagnostics["detectors"]["activity"]["start_threshold"]
        == 12.5
    )

    snapshot = diagnostics["storage_snapshot"]
    assert snapshot is not None
    assert snapshot["cycle_state"] == "running"


async def test_device_diagnostics(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test diagnostics from the logical device page."""
    entry = await _async_setup_entry(hass)

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert device is not None

    diagnostics = await async_get_device_diagnostics(
        hass,
        entry,
        device,
    )

    assert diagnostics["device"] == {
        "name": "Washing Machine",
        "name_by_user": None,
        "manufacturer": "Laundry Monitor",
        "model": "Washing Machine Monitor",
    }
    assert diagnostics["runtime"]["cycle_state"] == "running"


async def test_unavailable_source_is_reported(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test diagnostics mark unavailable required sources."""
    entry = await _async_setup_entry(hass)

    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        "unavailable",
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        entry,
    )

    assert diagnostics["required_sources_unavailable"] == [
        CONF_DOOR_SENSOR
    ]
    assert (
        diagnostics["sources"][CONF_DOOR_SENSOR]["available"]
        is False
    )
