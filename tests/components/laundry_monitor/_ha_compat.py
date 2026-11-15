"""Test-only helpers for legacy and official Home Assistant pytest packages.

Core through 2026.10.4 uses pytest-homeassistant-custom-component.
Core 2026.11+ uses the official pytest-homeassistant package instead.
Do not install both packages in the same test environment.
"""

from importlib.util import find_spec

if find_spec("pytest_homeassistant") is not None:
    from pytest_homeassistant import common as _common
else:
    from pytest_homeassistant_custom_component import common as _common

MockConfigEntry = _common.MockConfigEntry
async_fire_time_changed = _common.async_fire_time_changed
