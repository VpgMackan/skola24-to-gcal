"""
config.py - Configuration management for Skola24-to-GCal.
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.yaml"
)

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
    },
    "users": {},
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file, with environment variable overrides."""
    if config_path is None:
        config_path = os.environ.get("SKOLA24_CONFIG", DEFAULT_CONFIG_PATH)

    config = DEFAULT_CONFIG.copy()

    for key in DEFAULT_CONFIG:
        if isinstance(DEFAULT_CONFIG[key], dict):
            config[key] = DEFAULT_CONFIG[key].copy()

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                file_config = yaml.safe_load(f) or {}
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

    env_mappings = {
        "SKOLA24_HOST": ("skola24", "host"),
        "SKOLA24_UNIT_GUID": ("skola24", "unit_guid"),
        "SKOLA24_SELECTION": ("skola24", "selection"),
        "SKOLA24_SELECTION_TYPE": ("skola24", "selection_type"),
        "SERVER_HOST": ("server", "host"),
        "SERVER_PORT": ("server", "port"),
        "CACHE_TTL": ("schedule", "cache_ttl"),
        "WEEKS_AHEAD": ("schedule", "weeks_ahead"),
        "WEEKS_BEHIND": ("schedule", "weeks_behind"),
        "CALENDAR_NAME": ("schedule", "calendar_name"),
        "COLOR_THEME": ("schedule", "color_theme"),
    }

    for env_var, (section, key) in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
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

    for name, user in config.get("users", {}).items():
        if not user.get("host"):
            errors.append(f"users.{name}.host is required")
        if not user.get("unit_guid"):
            errors.append(f"users.{name}.unit_guid is required")
        if not user.get("selection"):
            errors.append(f"users.{name}.selection is required")
        sel_type = user.get("selection_type", 0)
        valid_types = (0, 4, 5, 7)
        if sel_type not in valid_types:
            errors.append(
                f"users.{name}.selection_type must be 0 (class), 7 (teacher), 5 (room), or 4 (personal). Got: {sel_type}"
            )

    return errors


def config_from_url_params(params: Dict[str, List[str]]) -> Dict[str, Any]:
    """Build configuration from URL query parameters."""
    config = {}
    for param, config_key in [
        ("host", "host"),
        ("unit_guid", "unit_guid"),
        ("selection", "selection"),
        ("selection_type", "selection_type"),
    ]:
        values = params.get(param)
        if values:
            value = values[0]
            if config_key == "selection_type":
                value = int(value)
            config[config_key] = value

    for param, config_key in [
        ("weeks_ahead", "weeks_ahead"),
        ("weeks_behind", "weeks_behind"),
        ("cache_ttl", "cache_ttl"),
        ("calendar_name", "calendar_name"),
        ("color_theme", "color_theme"),
    ]:
        values = params.get(param)
        if values:
            value = values[0]
            if config_key in ("weeks_ahead", "weeks_behind", "cache_ttl"):
                value = int(value)
            config[config_key] = value

    return config


def generate_example_config() -> str:
    """Generate an example configuration YAML string."""
    return """users:
  marnie:
    host: "it-gymnasiet.skola24.se"
    unit_guid: "XXX"
    selection: "TE24A"
    selection_type: 0
    weeks_ahead: 4
    cache_ttl: 60
    color_theme: "purple"

server:
  host: "0.0.0.0"
  port: 8080
"""
