"""
config.py - Configuration management for Skola24-to-GCal.

Loads configuration from a YAML file and environment variables.
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional

import skola24_api

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.yaml"
)

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
    },
    "skola24": {
        "host": "",  # e.g., "it-gymnasiet.skola24.se"
        "school_name": "",  # e.g., "NTI Johanneberg"
        "unit_guid": "",  # School unit GUID
        "selection": "",  # Class name, teacher ID, room name, or personnummer
        "selection_type": 0,  # 0=class, 7=teacher, 5=room, 4=personal
    },
    "schedule": {
        "weeks_ahead": 4,
        "weeks_behind": 1,
        "cache_ttl": 60,  # seconds
        "calendar_name": "",  # Display name for the calendar
        "color_theme": "purple",  # green, purple, red
    },
    "logging": {
        "level": "INFO",
    },
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file, with environment variable overrides.

    Environment variables override config file values:
        SKOLA24_HOST          -> skola24.host
        SKOLA24_UNIT_GUID     -> skola24.unit_guid
        SKOLA24_SELECTION     -> skola24.selection
        SKOLA24_SELECTION_TYPE -> skola24.selection_type
        SKOLA24_SCHOOL_NAME   -> skola24.school_name
        SERVER_HOST           -> server.host
        SERVER_PORT           -> server.port
        CACHE_TTL             -> schedule.cache_ttl
        WEEKS_AHEAD           -> schedule.weeks_ahead
        WEEKS_BEHIND          -> schedule.weeks_behind
        CALENDAR_NAME         -> schedule.calendar_name
        COLOR_THEME           -> schedule.color_theme
        LOG_LEVEL             -> logging.level
    """
    if config_path is None:
        config_path = os.environ.get("SKOLA24_CONFIG", DEFAULT_CONFIG_PATH)

    config = DEFAULT_CONFIG.copy()

    # Deep copy nested dicts
    for key in DEFAULT_CONFIG:
        if isinstance(DEFAULT_CONFIG[key], dict):
            config[key] = DEFAULT_CONFIG[key].copy()

    # Load from YAML file if it exists
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                file_config = yaml.safe_load(f) or {}
            # Merge file config into defaults
            for section in file_config:
                if section in config and isinstance(config[section], dict):
                    config[section].update(file_config[section])
                else:
                    config[section] = file_config[section]
            logger.info("Loaded config from %s", config_path)
        except Exception as e:
            logger.warning("Failed to load config from %s: %s", config_path, e)
    else:
        logger.info(
            "No config file found at %s, using defaults + env vars", config_path
        )

    # Environment variable overrides
    env_mappings = {
        "SKOLA24_HOST": ("skola24", "host"),
        "SKOLA24_UNIT_GUID": ("skola24", "unit_guid"),
        "SKOLA24_SELECTION": ("skola24", "selection"),
        "SKOLA24_SELECTION_TYPE": ("skola24", "selection_type"),
        "SKOLA24_SCHOOL_NAME": ("skola24", "school_name"),
        "SERVER_HOST": ("server", "host"),
        "SERVER_PORT": ("server", "port"),
        "CACHE_TTL": ("schedule", "cache_ttl"),
        "WEEKS_AHEAD": ("schedule", "weeks_ahead"),
        "WEEKS_BEHIND": ("schedule", "weeks_behind"),
        "CALENDAR_NAME": ("schedule", "calendar_name"),
        "COLOR_THEME": ("schedule", "color_theme"),
        "LOG_LEVEL": ("logging", "level"),
    }

    for env_var, (section, key) in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            # Type conversion
            if key in (
                "port",
                "cache_ttl",
                "weeks_ahead",
                "weeks_behind",
                "selection_type",
            ):
                value = int(value)
            config[section][key] = value

    return config


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate the configuration and return a list of errors."""
    errors = []

    if not config.get("skola24", {}).get("host"):
        errors.append("skola24.host is required (e.g., 'it-gymnasiet.skola24.se')")

    if not config.get("skola24", {}).get("unit_guid"):
        errors.append(
            "skola24.unit_guid is required. Use the 'list-schools' command to find it."
        )

    if not config.get("skola24", {}).get("selection"):
        errors.append(
            "skola24.selection is required (class name, teacher ID, room name, or personnummer)"
        )

    sel_type = config.get("skola24", {}).get("selection_type", 0)
    if sel_type not in (
        skola24_api.SELECTION_TYPE_CLASS,
        skola24_api.SELECTION_TYPE_PERSONAL,
        skola24_api.SELECTION_TYPE_ROOM,
        skola24_api.SELECTION_TYPE_TEACHER,
    ):
        errors.append(
            f"skola24.selection_type must be 0 (class), 7 (teacher), 5 (room), or 4 (personal). Got: {sel_type}"
        )

    return errors


def generate_example_config() -> str:
    """Generate an example configuration YAML string."""
    return """# Skola24-to-GCal Configuration
# ================================

# Skola24 settings
skola24:
  # Your school's Skola24 host domain
  # Find this from your school's Skola24 URL
  # Examples: "goteborg.skola24.se", "it-gymnasiet.skola24.se", "malmo.skola24.se"
  host: "it-gymnasiet.skola24.se"

  # Your school name (for display purposes)
  school_name: "My School"

  # School unit GUID - use 'python3 server.py list-schools --host <HOST>' to find this
  unit_guid: ""

  # What schedule to fetch:
  # - For a class: use the class name exactly as shown (e.g., "TE24A")
  # - For a teacher: use the teacher's abbreviation (e.g., "JW")
  # - For a room: use the room name (e.g., "318")
  # - For a student: use the personnummer (YYYYMMDDXXXX)
  selection: ""

  # Selection type:
  # 0 = class
  # 7 = teacher
  # 5 = room
  # 4 = personal (personnummer)
    selection_type: 0 # Use 0 for class, 7 for teacher, 5 for room, 4 for personal

# Schedule fetching settings
schedule:
  # How many weeks ahead to include
  weeks_ahead: 4

  # How many weeks behind to include
  weeks_behind: 1

  # Cache time-to-live in seconds
  # The schedule will be re-fetched from Skola24 after this many seconds
  # Google Calendar typically refreshes subscriptions every few hours,
  # but if you access the URL directly it will always be fresh
  cache_ttl: 60

  # Display name for the calendar
  calendar_name: "School Schedule"

    # Pastel color theme base for subject colors
    # Available values: green, purple, red
    # ("purble" is accepted as an alias for purple)
    color_theme: "purple"

# HTTP server settings
server:
  host: "0.0.0.0"
  port: 8080

# Logging settings
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
"""
