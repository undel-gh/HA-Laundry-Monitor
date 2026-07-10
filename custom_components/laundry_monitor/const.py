"""Constants for the Laundry Monitor integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "laundry_monitor"

# Config entry data keys.
CONF_POWER_SENSOR: Final = "power_sensor"
CONF_DOOR_SENSOR: Final = "door_sensor"
CONF_VIBRATION_SENSOR: Final = "vibration_sensor"
CONF_LEAK_SENSOR: Final = "leak_sensor"
CONF_ENERGY_SENSOR: Final = "energy_sensor"
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"
CONF_PLUG_SWITCH: Final = "plug_switch"
CONF_TRACK_LAUNDRY: Final = "track_laundry"

DEFAULT_NAME: Final = "Washing Machine"
DEFAULT_TRACK_LAUNDRY: Final = False

CONFIG_ENTRY_VERSION: Final = 1
CONFIG_ENTRY_MINOR_VERSION: Final = 1

# Event names.
EVENT_CYCLE_STARTED: Final = f"{DOMAIN}.cycle_started"
EVENT_FINAL_SPIN_DETECTED: Final = f"{DOMAIN}.final_spin_detected"
EVENT_CYCLE_FINISHED: Final = f"{DOMAIN}.cycle_finished"
EVENT_DOOR_OPENED_AFTER_FINISH: Final = (
    f"{DOMAIN}.door_opened_after_finish"
)
EVENT_MACHINE_UNLOADED: Final = f"{DOMAIN}.machine_unloaded"
EVENT_LEAK_DETECTED: Final = f"{DOMAIN}.leak_detected"
EVENT_STATE_CHANGED: Final = f"{DOMAIN}.state_changed"


class LaundryCycleState(StrEnum):
    """Public cycle states exposed by Laundry Monitor."""

    IDLE = "idle"
    ARMED = "armed"
    RUNNING = "running"
    FINAL_SPIN = "final_spin"
    FINISHED = "finished"
    ERROR = "error"
