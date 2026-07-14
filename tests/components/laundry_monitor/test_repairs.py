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
    CONF_LEAK_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
)
from custom_components.laundry_monitor.repairs import (
    ISSUE_TRANSLATION_KEY,
    required_source_issue_id,
)


def _create_entry(
    *,
    include_optional_leak: bool = False,
) -> MockConfigEntry:
    """Create a Laundry Monitor config entry."""
    data = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR: (
            "binary_sensor.washing_machine_vibration"
        ),
        CONF_TRACK_LAUNDRY: True,
    }

    if include_optional_leak:
        data[CONF_LEAK_SENSOR] = (
            "binary_sensor.washing_machine_leak"
        )

    return MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
    )


def _set_required_sources_available(
    hass: HomeAssistant,
) -> None:
    """Create all mandatory source states."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )


async def test_issue_is_created_and_cleared(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test an unavailable source creates and clears a warning."""
    _set_required_sources_available(hass)

    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    issue_id = required_source_issue_id(
        entry.entry_id,
        CONF_DOOR_SENSOR,
    )

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None

    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_UNAVAILABLE,
    )
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.is_persistent is False
    assert issue.translation_key == ISSUE_TRANSLATION_KEY
    assert issue.translation_placeholders == {
        "name": "Washing Machine",
        "entity_id": "binary_sensor.washing_machine_door",
    }

    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_missing_required_source_creates_issue_on_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a missing entity is detected during integration setup."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )

    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN,
        required_source_issue_id(
            entry.entry_id,
            CONF_DOOR_SENSOR,
        ),
    )
    assert issue is not None


async def test_optional_source_does_not_create_issue(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test unavailable optional sensors are diagnostic only."""
    _set_required_sources_available(hass)
    hass.states.async_set(
        "binary_sensor.washing_machine_leak",
        STATE_UNAVAILABLE,
    )

    entry = _create_entry(include_optional_leak=True)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert all(
        issue.domain != DOMAIN
        or entry.entry_id not in issue.issue_id
        for issue in registry.issues.values()
    )


async def test_issues_are_removed_when_entry_is_unloaded(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test stale Repairs issues are removed on unload."""
    _set_required_sources_available(hass)
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_UNAVAILABLE,
    )

    entry = _create_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue_id = required_source_issue_id(
        entry.entry_id,
        CONF_DOOR_SENSOR,
    )
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_issue(DOMAIN, issue_id) is None
