"""Test Laundry Monitor diagnostics."""

from __future__ import annotations

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_OFF,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_ACTIVITY_THRESHOLD,
    CONF_CURRENT_ACTIVITY_THRESHOLD,
    CONF_CURRENT_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
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
from custom_components.laundry_monitor.repairs import required_source_issue_id


async def _async_setup_entry(
    hass: HomeAssistant,
    *,
    power_state: str = "0.25",
    power_unit: str | None = "W",
    current_state: str = "0.25",
    current_unit: str | None = "A",
    include_energy: bool = False,
) -> MockConfigEntry:
    """Set up a configured Laundry Monitor entry with selected source units."""
    power_attrs = {"device_class": "power", "state_class": "measurement"}
    if power_unit is not None:
        power_attrs[ATTR_UNIT_OF_MEASUREMENT] = power_unit
    hass.states.async_set(
        "sensor.washing_machine_power", power_state, power_attrs
    )

    current_attrs = {"device_class": "current", "state_class": "measurement"}
    if current_unit is not None:
        current_attrs[ATTR_UNIT_OF_MEASUREMENT] = current_unit
    hass.states.async_set(
        "sensor.washing_machine_current", current_state, current_attrs
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

    data = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_CURRENT_SENSOR: "sensor.washing_machine_current",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
        CONF_TRACK_LAUNDRY: True,
    }
    if include_energy:
        hass.states.async_set(
            "sensor.washing_machine_energy",
            "12",
            {ATTR_UNIT_OF_MEASUREMENT: "kWh"},
        )
        data[CONF_ENERGY_SENSOR] = "sensor.washing_machine_energy"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
        options={
            CONF_ACTIVITY_THRESHOLD: 4.5,
            CONF_CURRENT_ACTIVITY_THRESHOLD: 0.2,
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
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry"]["title"] == "Washing Machine"
    assert diagnostics["required_sources_unavailable"] == []

    power = diagnostics["sources"][CONF_POWER_SENSOR]
    assert power["configured"] is True
    assert power["required"] is True
    assert power["available"] is True
    assert power["state"] == "0.25"

    current = diagnostics["sources"][CONF_CURRENT_SENSOR]
    assert current["configured"] is True
    assert current["required"] is False
    assert current["available"] is True
    assert current["state"] == "0.25"

    assert diagnostics["sources"][CONF_DOOR_SENSOR]["required"] is False
    assert (
        diagnostics["sources"][CONF_VIBRATION_SENSOR]["required"]
        is False
    )

    assert diagnostics["runtime"]["cycle_state"] == "running"
    assert diagnostics["runtime"]["current"] == 0.25
    assert diagnostics["runtime"]["laundry_present"] is True
    assert (
        diagnostics["detectors"]["activity"]["activity_threshold"]
        == 4.5
    )
    assert (
        diagnostics["detectors"]["activity"][
            "current_activity_threshold"
        ]
        == 0.2
    )
    assert diagnostics["detectors"]["activity"][
        "current_activity_detected"
    ] is True
    assert diagnostics["detectors"]["activity"]["active_sources"] == [
        "current"
    ]
    electrical = diagnostics["detectors"]["spin"]["electrical_candidate"]
    assert electrical["max_source_age_seconds"] == 30
    assert electrical["power_source_fresh"] is True
    assert electrical["current_source_fresh"] is True

    heating = diagnostics["detectors"]["spin"]["heating"]
    assert heating["state"] == "unknown"
    assert heating["active"] is False
    assert heating["power_threshold_w"] is None
    assert heating["confirmation_seconds"] == 30
    assert heating["observation_seconds"] == 300
    assert heating["heated_cycle_min_seconds"] == 900
    assert heating["max_source_age_seconds"] == 30

    assert (
        diagnostics["detectors"]["finish"][
            "running_fallback_confirmation_seconds"
        ]
        == entry.runtime_data.running_finish_detector.confirmation_seconds
    )
    assert (
        diagnostics["detectors"]["lifecycle"][
            "arming_timeout_seconds"
        ]
        == entry.runtime_data.arming_timeout_seconds
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
    device_registry = dr.async_get(hass)
    # Core 2026.6 uses the identifiers lookup; newer Core provides this
    # dedicated method and deprecates the older async_get_device API.
    if hasattr(device_registry, "async_get_device_by_identifier"):
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, entry.entry_id),
            entry.entry_id,
        )
    else:
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
    assert device is not None

    diagnostics = await async_get_device_diagnostics(
        hass,
        entry,
        device,
    )

    assert diagnostics["device"]["name"] == "Washing Machine"
    assert diagnostics["runtime"]["cycle_state"] == "running"


async def test_optional_unavailable_source_is_reported_as_degraded(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test optional source failure is visible but not required."""
    entry = await _async_setup_entry(hass)

    hass.states.async_set(
        "sensor.washing_machine_current",
        "unavailable",
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        "unavailable",
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["required_sources_unavailable"] == []
    current = diagnostics["sources"][CONF_CURRENT_SENSOR]
    assert current["required"] is False
    assert current["available"] is False

    door = diagnostics["sources"][CONF_DOOR_SENSOR]
    assert door["required"] is False
    assert door["available"] is False


async def test_invalid_power_is_reported_as_required_unavailable(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test diagnostics agree with runtime numeric validation."""
    entry = await _async_setup_entry(hass)
    hass.states.async_set("sensor.washing_machine_power", "not-a-number")
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["required_sources_unavailable"] == [
        CONF_POWER_SENSOR
    ]
    assert (
        diagnostics["sources"][CONF_POWER_SENSOR]["available"]
        is False
    )


@pytest.mark.parametrize(
    ("raw", "unit"),
    [
        ("45", "V"),
        ("45", "VA"),
        ("45", "kw"),
        ("1e308", UnitOfPower.KILO_WATT),
        ("invalid", UnitOfPower.WATT),
    ],
)
async def test_required_power_diagnostics_match_runtime_and_repairs_at_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    raw: str,
    unit: str,
) -> None:
    """Unusable numeric power must appear unavailable in every subsystem."""
    entry = await _async_setup_entry(
        hass, power_state=raw, power_unit=unit
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_POWER_SENSOR]

    assert source["available"] is False
    assert source["entity_available"] is True
    assert source["state"] == raw
    assert source["attributes"][ATTR_UNIT_OF_MEASUREMENT] == unit
    assert source["last_changed"] is not None
    assert source["last_updated"] is not None
    assert diagnostics["required_sources_unavailable"] == [
        CONF_POWER_SENSOR
    ]
    assert entry.runtime_data.power is None
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, required_source_issue_id(entry.entry_id, CONF_POWER_SENSOR)
    ) is not None


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("0", UnitOfPower.WATT, 0.0),
        ("0", UnitOfPower.KILO_WATT, 0.0),
        ("0.045", UnitOfPower.KILO_WATT, 45.0),
        ("250", UnitOfPower.MILLIWATT, 0.25),
        ("45", None, 45.0),
    ],
)
async def test_valid_power_units_remain_available_in_diagnostics(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    raw: str,
    unit: str | None,
    expected: float,
) -> None:
    """Unitless and convertible source values follow the runtime contract."""
    entry = await _async_setup_entry(
        hass, power_state=raw, power_unit=unit
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_POWER_SENSOR]

    assert source["available"] is True
    assert source["entity_available"] is True
    assert source["state"] == raw
    assert source["attributes"].get(ATTR_UNIT_OF_MEASUREMENT) == unit
    assert entry.runtime_data.power == pytest.approx(expected)
    assert diagnostics["required_sources_unavailable"] == []
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, required_source_issue_id(entry.entry_id, CONF_POWER_SENSOR)
    ) is None


async def test_diagnostics_and_repairs_follow_power_unit_changes(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """W -> V -> W must update the export, runtime and Repairs together."""
    entry = await _async_setup_entry(
        hass, power_state="45", power_unit=UnitOfPower.WATT
    )
    issue_id = required_source_issue_id(entry.entry_id, CONF_POWER_SENSOR)
    registry = ir.async_get(hass)
    entity_id = "sensor.washing_machine_power"

    assert entry.runtime_data.power == 45.0
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    hass.states.async_set(
        entity_id, "45", {ATTR_UNIT_OF_MEASUREMENT: "V"}
    )
    await hass.async_block_till_done()

    bad = await async_get_config_entry_diagnostics(hass, entry)
    assert bad["sources"][CONF_POWER_SENSOR]["available"] is False
    assert bad["sources"][CONF_POWER_SENSOR]["entity_available"] is True
    assert bad["required_sources_unavailable"] == [CONF_POWER_SENSOR]
    assert entry.runtime_data.power is None
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    hass.states.async_set(
        entity_id,
        "45",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
    )
    await hass.async_block_till_done()

    good = await async_get_config_entry_diagnostics(hass, entry)
    assert good["sources"][CONF_POWER_SENSOR]["available"] is True
    assert good["required_sources_unavailable"] == []
    assert entry.runtime_data.power == 45.0
    assert registry.async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("500", UnitOfElectricCurrent.MILLIAMPERE, 0.5),
        ("0.25", UnitOfElectricCurrent.AMPERE, 0.25),
        ("0", UnitOfElectricCurrent.AMPERE, 0.0),
        ("0.4", None, 0.4),
    ],
)
async def test_valid_optional_current_units(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    raw: str,
    unit: str | None,
    expected: float,
) -> None:
    """Optional current uses A, mA or a legacy unitless value."""
    entry = await _async_setup_entry(
        hass, current_state=raw, current_unit=unit
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_CURRENT_SENSOR]

    assert source["available"] is True
    assert source["entity_available"] is True
    assert source["state"] == raw
    assert entry.runtime_data.current == pytest.approx(expected)
    assert diagnostics["required_sources_unavailable"] == []


async def test_invalid_optional_current_unit_is_degraded_not_required(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A numeric but incompatible current unit is not usable evidence."""
    entry = await _async_setup_entry(
        hass, current_state="500", current_unit="V"
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_CURRENT_SENSOR]

    assert source["available"] is False
    assert source["entity_available"] is True
    assert source["state"] == "500"
    assert source["attributes"][ATTR_UNIT_OF_MEASUREMENT] == "V"
    assert entry.runtime_data.current is None
    assert entry.runtime_data.power == pytest.approx(0.25)
    assert diagnostics["required_sources_unavailable"] == []


async def test_energy_keeps_independent_numeric_validation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """The optional energy source is not converted as power/current."""
    entry = await _async_setup_entry(hass, include_energy=True)
    assert entry.runtime_data.energy_unit == "kWh"

    hass.states.async_set(
        "sensor.washing_machine_energy",
        "12.5",
        {ATTR_UNIT_OF_MEASUREMENT: "V"},
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_ENERGY_SENSOR]
    assert source["available"] is True
    assert source["entity_available"] is True
    assert source["state"] == "12.5"
    assert source["attributes"][ATTR_UNIT_OF_MEASUREMENT] == "V"
    assert entry.runtime_data.energy == 12.5
    assert entry.runtime_data.energy_unit == "V"


async def test_unknown_entity_state_stays_unavailable(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Unknown is not HA-available or detector-usable."""
    entry = await _async_setup_entry(hass)
    hass.states.async_set("sensor.washing_machine_power", "unknown")
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    source = diagnostics["sources"][CONF_POWER_SENSOR]
    assert source["entity_available"] is False
    assert source["available"] is False
    assert source["state"] == "unknown"
    assert diagnostics["required_sources_unavailable"] == [CONF_POWER_SENSOR]
