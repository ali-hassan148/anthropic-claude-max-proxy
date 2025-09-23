"""Configuration loader for Anthropic Claude Max Proxy

Loads configuration from multiple sources with the following priority:
1. Environment variables (highest priority)
2. config.json file
3. Hardcoded defaults (lowest priority)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Set up logger for config loader
logger = logging.getLogger(__name__)


class ConfigLoader:
    """Handles loading configuration from various sources"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the config loader

        Args:
            config_path: Optional path to config.json file.
                        Defaults to 'config.json' in the current directory.
        """
        self.config_path = Path(config_path) if config_path else Path("config.json")
        self.config_data = self._load_config_file()

    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file if it exists"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load {self.config_path}: {e}")
                return {}
        return {}

    def get(self, env_var: str, config_path: str, default: Any) -> Any:
        """Get a configuration value with priority: env > config.json > default

        Args:
            env_var: Environment variable name to check
            config_path: Dot-separated path in config.json (e.g., "server.port")
            default: Default value if not found elsewhere

        Returns:
            The configuration value from the highest priority source
        """
        # 1. Check environment variable
        env_value = os.getenv(env_var)
        if env_value is not None:
            # Try to parse as appropriate type
            if isinstance(default, bool):
                return env_value.lower() in ('true', '1', 'yes')
            elif isinstance(default, int):
                try:
                    return int(env_value)
                except ValueError:
                    pass
            elif isinstance(default, float):
                try:
                    return float(env_value)
                except ValueError:
                    pass
            return env_value

        # 2. Check config.json
        if self.config_data:
            value = self._get_nested_value(self.config_data, config_path)
            if value is not None:
                # Expand home directory if it's a path
                if isinstance(value, str) and value.startswith("~/"):
                    return str(Path(value).expanduser())
                return value

        # 3. Return default
        # Expand home directory if it's a path
        if isinstance(default, str) and default.startswith("~/"):
            return str(Path(default).expanduser())
        return default

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a value from nested dictionary using dot notation

        Args:
            data: The dictionary to search
            path: Dot-separated path (e.g., "server.port")

        Returns:
            The value if found, None otherwise
        """
        keys = path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def get_all_config(self) -> Dict[str, Any]:
        """Get the entire loaded configuration"""
        return self.config_data.copy()


# Create a global instance
_config_loader = None

def get_config_loader() -> ConfigLoader:
    """Get or create the global ConfigLoader instance"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader