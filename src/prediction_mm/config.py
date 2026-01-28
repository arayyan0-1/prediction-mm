"""Configuration management for Kalshi API client.

This module handles loading configuration from environment variables,
including API credentials and environment selection (demo vs production).

Credentials can be auto-discovered from api-demo-key/ and api-prod-key/
directories, or explicitly set via environment variables.
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


def _find_project_root() -> Path:
    """Find the project root by walking up from this file looking for .git."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback to cwd
    return Path.cwd()


def discover_credentials(
    environment: Environment, project_root: Path | None = None
) -> tuple[str, Path]:
    """Auto-discover API key ID and private key path from credential directories.

    Convention:
        api-demo-key/ for DEMO environment
        api-prod-key/ for PROD environment

    Each directory contains:
        - api-key-id.txt: contains the API key ID
        - *.pem: the RSA private key file

    Args:
        environment: Which environment's credentials to discover.
        project_root: Root directory containing api-*-key/ dirs.
            Defaults to the git repo root.

    Returns:
        Tuple of (api_key_id, private_key_path).

    Raises:
        ConfigError: If credential directory or required files are missing.
    """
    if project_root is None:
        project_root = _find_project_root()

    dir_name = f"api-{environment.value}-key"
    cred_dir = project_root / dir_name

    if not cred_dir.exists():
        raise ConfigError(
            f"Credential directory not found: {cred_dir}\n"
            f"Create {dir_name}/ with api-key-id.txt and a .pem private key file."
        )

    # Read API key ID
    key_id_file = cred_dir / "api-key-id.txt"
    if not key_id_file.exists():
        raise ConfigError(f"API key ID file not found: {key_id_file}")
    api_key_id = key_id_file.read_text().strip()

    if not api_key_id:
        raise ConfigError(f"API key ID file is empty: {key_id_file}")

    # Find private key file (.pem)
    pem_files = [
        f for f in cred_dir.iterdir()
        if f.suffix == ".pem"
    ]

    if len(pem_files) == 0:
        raise ConfigError(
            f"No private key file found in {cred_dir}\n"
            "Expected a .pem file containing the RSA private key."
        )
    if len(pem_files) > 1:
        raise ConfigError(
            f"Multiple private key files found in {cred_dir}: "
            f"{[f.name for f in pem_files]}\n"
            "Expected exactly one .pem file."
        )

    private_key_path = pem_files[0]
    return api_key_id, private_key_path


def load_config_for_env(environment: Environment) -> Config:
    """Load config for a specific environment using auto-discovery.

    Used for runtime environment switching where we want fresh
    credentials for the target environment.

    Args:
        environment: The target environment.

    Returns:
        Config for the specified environment.

    Raises:
        ConfigError: If credentials cannot be discovered.
    """
    api_key_id, private_key_path = discover_credentials(environment)
    return Config(
        api_key_id=api_key_id,
        private_key_path=private_key_path,
        environment=environment,
    )


def load_config(
    env_file: Path | None = None, env_override: str | None = None
) -> Config:
    """Load configuration from environment variables.

    Loads from .env file if present, then validates all required variables.
    Credentials are auto-discovered from api-{env}-key/ directories unless
    explicitly set via KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH.

    Args:
        env_file: Optional path to .env file. If None, searches default locations.
        env_override: Optional environment override (e.g. from CLI --env flag).
            Takes precedence over KALSHI_ENV environment variable.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If required variables are missing, invalid, or files don't exist.
    """
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    # Determine environment (CLI override > env var > default)
    env_str = (env_override or os.getenv("KALSHI_ENV", "demo")).lower()
    if env_str == "demo":
        environment = Environment.DEMO
    elif env_str == "prod":
        environment = Environment.PROD
    else:
        raise ConfigError(
            f"Invalid KALSHI_ENV: {env_str!r}\n"
            "Must be 'demo' or 'prod'."
        )

    # Determine credentials (explicit env vars > auto-discovery)
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key_path_str = os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if api_key_id and private_key_path_str:
        # Explicit credentials take precedence (backward compat)
        private_key_path = Path(private_key_path_str)
        if not private_key_path.exists():
            raise ConfigError(
                f"Private key file not found: {private_key_path}\n"
                "Download your private key from Kalshi and update KALSHI_PRIVATE_KEY_PATH."
            )
    else:
        # Auto-discover from credential directories
        api_key_id, private_key_path = discover_credentials(environment)

    return Config(
        api_key_id=api_key_id,
        private_key_path=private_key_path,
        environment=environment,
    )
