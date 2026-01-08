"""Configuration management for Kalshi API client.

This module handles loading configuration from environment variables,
including API credentials and environment selection (demo vs production).
"""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class Environment(Enum):
    """Kalshi environment selection."""

    DEMO = "demo"
    PROD = "prod"


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables.

    Attributes:
        api_key_id: Kalshi API key ID for authentication.
        private_key_path: Path to RSA private key PEM file.
        environment: Environment selection (DEMO or PROD).
    """

    api_key_id: str
    private_key_path: Path
    environment: Environment

    @property
    def base_url(self) -> str:
        """Get REST API base URL for the selected environment.

        Returns:
            Base URL string for the Kalshi REST API.
        """
        if self.environment == Environment.DEMO:
            return "https://demo-api.kalshi.co/trade-api/v2"
        return "https://api.elections.kalshi.com/trade-api/v2"

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL for the selected environment.

        Returns:
            WebSocket URL string for the Kalshi WebSocket API.
        """
        if self.environment == Environment.DEMO:
            return "wss://demo-api.kalshi.co/trade-api/ws/v2"
        return "wss://api.elections.kalshi.com/trade-api/ws/v2"

    @property
    def host(self) -> str:
        """Get host URL for SDK configuration.

        Returns:
            Host URL for the Kalshi SDK.
        """
        if self.environment == Environment.DEMO:
            return "https://demo-api.kalshi.co/trade-api/v2"
        return "https://api.elections.kalshi.com/trade-api/v2"


def load_config(env_file: Path | None = None) -> Config:
    """Load configuration from environment variables.

    Loads from .env file if present, then validates all required variables.

    Args:
        env_file: Optional path to .env file. If None, searches default locations
            (.env in current directory or parent directories).

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If required variables are missing, invalid, or files don't exist.

    Example:
        ```python
        # Load from default .env location
        config = load_config()

        # Load from specific .env file
        config = load_config(Path("/path/to/.env"))

        # Use configuration
        print(f"Environment: {config.environment.value}")
        print(f"API URL: {config.base_url}")
        ```

    Required Environment Variables:
        KALSHI_API_KEY_ID: Your API key ID from Kalshi.
        KALSHI_PRIVATE_KEY_PATH: Absolute path to your RSA private key PEM file.
        KALSHI_ENV: Environment selection - "demo" or "prod" (default: "demo").
    """
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    # API Key ID
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    if not api_key_id:
        raise ConfigError(
            "KALSHI_API_KEY_ID environment variable is required.\n"
            "Set it in .env or export it in your shell."
        )

    # Private key path
    private_key_path_str = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not private_key_path_str:
        raise ConfigError(
            "KALSHI_PRIVATE_KEY_PATH environment variable is required.\n"
            "Set it to the path of your RSA private key file."
        )

    private_key_path = Path(private_key_path_str)
    if not private_key_path.exists():
        raise ConfigError(
            f"Private key file not found: {private_key_path}\n"
            "Download your private key from Kalshi and update KALSHI_PRIVATE_KEY_PATH."
        )

    # Environment
    env_str = os.getenv("KALSHI_ENV", "demo").lower()
    if env_str == "demo":
        environment = Environment.DEMO
    elif env_str == "prod":
        environment = Environment.PROD
    else:
        raise ConfigError(
            f"Invalid KALSHI_ENV: {env_str!r}\n"
            "Must be 'demo' or 'prod'."
        )

    return Config(
        api_key_id=api_key_id,
        private_key_path=private_key_path,
        environment=environment,
    )
