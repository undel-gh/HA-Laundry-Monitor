"""Test Laundry Monitor Repairs issues."""

from __future__ import annotations

from homeassistant.const import (
    CONF_NAME,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
)
from custom_components.laundry_monitor.repairs import (
    ISSUE_TRANSLATION_KEY,
    required_source_issue_id,
)


def _create_entry() -> MockConfigEntry:
    """Create an entry with recommended optional sources."""
    return MockConfigEntry(
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
    )


def _set_sources_available(hass: HomeAssistant) -> None:
    """Create the required and recommended source states."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )


async def test_power_issue_is_created_and_cleared(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the only required source creates a Repairs warning."""
    _set_sources_available(hass)
    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue_id = required_source_issue_id(
        entry.entry_id,
        CONF_POWER_SENSOR,
    )
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    hass.states.async_set(
        "sensor.washing_machine_power",
        STATE_UNAVAILABLE,
    )
    await hass.async_block_till_done()

    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.is_persistent is False
    assert issue.translation_key == ISSUE_TRANSLATION_KEY
    assert issue.translation_placeholders == {
        "name": "Washing Machine",
        "entity_id": "sensor.washing_machine_power",
    }

    hass.states.async_set("sensor.washing_machine_power", "0.25")
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_missing_power_creates_issue_on_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a missing required entity is detected during setup."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(
        DOMAIN,
        required_source_issue_id(
            entry.entry_id,
            CONF_POWER_SENSOR,
        ),
    ) is not None


async def test_optional_door_and_vibration_do_not_create_issues(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test degraded optional sources stay diagnostic only."""
    _set_sources_available(hass)
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_UNAVAILABLE,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_UNAVAILABLE,
    )

    entry = _create_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(
        DOMAIN,
        required_source_issue_id(entry.entry_id, CONF_DOOR_SENSOR),
    ) is None
    assert registry.async_get_issue(
        DOMAIN,
        required_source_issue_id(
            entry.entry_id,
            CONF_VIBRATION_SENSOR,
        ),
    ) is None


async def test_power_issue_is_removed_on_unload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test stale required-source issues are removed on unload."""
    _set_sources_available(hass)
    hass.states.async_set(
        "sensor.washing_machine_power",
        STATE_UNAVAILABLE,
    )

    entry = _create_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue_id = required_source_issue_id(
        entry.entry_id,
        CONF_POWER_SENSOR,
    )
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_invalid_power_value_creates_issue(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a non-numeric power state is treated as unavailable."""
    _set_sources_available(hass)
    hass.states.async_set("sensor.washing_machine_power", "not-a-number")

    entry = _create_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(
        DOMAIN,
        required_source_issue_id(
            entry.entry_id,
            CONF_POWER_SENSOR,
        ),
    ) is not None
