"""Constants for the Laundry Monitor integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "laundry_monitor"

# Config-entry data keys.
CONF_POWER_SENSOR: Final = "power_sensor"
CONF_DOOR_SENSOR: Final = "door_sensor"
CONF_VIBRATION_SENSOR: Final = "vibration_sensor"
CONF_LEAK_SENSOR: Final = "leak_sensor"
CONF_ENERGY_SENSOR: Final = "energy_sensor"
CONF_PLUG_SWITCH: Final = "plug_switch"
CONF_TRACK_LAUNDRY: Final = "track_laundry"

# Activity Detector option keys.
CONF_START_THRESHOLD: Final = "start_threshold"
CONF_ACTIVITY_THRESHOLD: Final = "activity_threshold"
CONF_START_CONFIRMATION: Final = "start_confirmation"

# Spin Detector option keys.
CONF_SPIN_REQUIRED_EVENTS: Final = "spin_required_events"
CONF_SPIN_WINDOW: Final = "spin_window"
CONF_SPIN_MIN_CYCLE_TIME: Final = "spin_min_cycle_time"
CONF_SPIN_ACTIVITY_MAX_AGE: Final = "spin_activity_max_age"

# Finish Detector and lifecycle option keys.
CONF_FINISH_CONFIRMATION: Final = "finish_confirmation"
CONF_RUNNING_FINISH_CONFIRMATION: Final = "running_finish_confirmation"
CONF_ARMING_TIMEOUT: Final = "arming_timeout"
CONF_FINISHED_RETENTION: Final = "finished_retention"
CONF_POWER_UNAVAILABLE_GRACE: Final = "power_unavailable_grace"
CONF_SNAPSHOT_MAX_AGE: Final = "snapshot_max_age"

DEFAULT_NAME: Final = "Washing Machine"
DEFAULT_TRACK_LAUNDRY: Final = False
DEFAULT_START_THRESHOLD: Final = 10.0
DEFAULT_ACTIVITY_THRESHOLD: Final = 5.0
DEFAULT_START_CONFIRMATION: Final = 30
DEFAULT_SPIN_REQUIRED_EVENTS: Final = 3
DEFAULT_SPIN_WINDOW: Final = 180
DEFAULT_SPIN_MIN_CYCLE_TIME: Final = 600
DEFAULT_SPIN_ACTIVITY_MAX_AGE: Final = 120
DEFAULT_FINISH_CONFIRMATION: Final = 180
DEFAULT_RUNNING_FINISH_CONFIRMATION: Final = 600
DEFAULT_ARMING_TIMEOUT: Final = 1800
DEFAULT_FINISHED_RETENTION: Final = 300
DEFAULT_POWER_UNAVAILABLE_GRACE: Final = 120
DEFAULT_SNAPSHOT_MAX_AGE: Final = 86400

CONFIG_ENTRY_VERSION: Final = 1
CONFIG_ENTRY_MINOR_VERSION: Final = 1

# Runtime platforms.
PLATFORMS: Final = ("sensor", "binary_sensor", "button")

# Dispatcher signals.
SIGNAL_RUNTIME_UPDATED: Final = f"{DOMAIN}_runtime_updated"

# Transition reasons.
REASON_INITIAL_SETUP: Final = "initial_setup"
REASON_DOOR_CLOSED: Final = "door_closed"
REASON_DOOR_OPENED_BEFORE_START: Final = "door_opened_before_start"
REASON_ARMING_TIMEOUT: Final = "arming_timeout"
REASON_POWER_ABOVE_START_THRESHOLD: Final = "power_above_start_threshold"
REASON_ACTIVITY_RESUMED_AFTER_FINAL_SPIN: Final = (
    "activity_resumed_after_final_spin"
)
REASON_FINAL_SPIN_CONFIRMED: Final = "final_spin_confirmed"
REASON_FINISH_INACTIVITY_CONFIRMED: Final = "finish_inactivity_confirmed"
REASON_FINISH_FALLBACK_CONFIRMED: Final = "finish_fallback_confirmed"
REASON_FINISHED_RETENTION_EXPIRED: Final = "finished_retention_expired"
REASON_MARKED_UNLOADED: Final = "marked_unloaded"
REASON_POWER_SENSOR_UNAVAILABLE: Final = "power_sensor_unavailable"
REASON_POWER_SENSOR_RECOVERED: Final = "power_sensor_recovered"
REASON_STATE_RESTORED: Final = "state_restored"
REASON_STATE_RECOVERY_FALLBACK: Final = "state_recovery_fallback"

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
EVENT_TRANSITION_REJECTED: Final = f"{DOMAIN}.transition_rejected"


class LaundryCycleState(StrEnum):
    """Public cycle states exposed by Laundry Monitor."""

    IDLE = "idle"
    ARMED = "armed"
    RUNNING = "running"
    FINAL_SPIN = "final_spin"
    FINISHED = "finished"
    ERROR = "error"
