"""Tests for configuration management."""

import os
import pytest
from pathlib import Path

from prediction_mm.config import (
    Config,
    ConfigError,
    Environment,
    discover_credentials,
    load_config,
    load_config_for_env,
)


class TestConfig:
    """Tests for Config dataclass."""

    def test_demo_base_url(self, tmp_private_key: Path):
        """Demo environment uses demo API URL."""
        config = Config(
            api_key_id="test-key",
            private_key_path=tmp_private_key,
            environment=Environment.DEMO,
        )

        assert "demo-api.kalshi.co" in config.base_url
        assert "trade-api/v2" in config.base_url

    def test_prod_base_url(self, tmp_private_key: Path):
        """Prod environment uses prod API URL."""
        config = Config(
            api_key_id="test-key",
            private_key_path=tmp_private_key,
            environment=Environment.PROD,
        )

        assert "api.elections.kalshi.com" in config.base_url
        assert "trade-api/v2" in config.base_url

    def test_demo_ws_url(self, tmp_private_key: Path):
        """Demo WebSocket URL is correct."""
        config = Config(
            api_key_id="test-key",
            private_key_path=tmp_private_key,
            environment=Environment.DEMO,
        )

        assert "wss://demo-api.kalshi.co" in config.ws_url
        assert "/trade-api/ws/v2" in config.ws_url

    def test_prod_ws_url(self, tmp_private_key: Path):
        """Prod WebSocket URL is correct."""
        config = Config(
            api_key_id="test-key",
            private_key_path=tmp_private_key,
            environment=Environment.PROD,
        )

        assert "wss://api.elections.kalshi.com" in config.ws_url
        assert "/trade-api/ws/v2" in config.ws_url

    def test_config_is_frozen(self, tmp_private_key: Path):
        """Config is immutable (frozen dataclass)."""
        config = Config(
            api_key_id="test-key",
            private_key_path=tmp_private_key,
            environment=Environment.DEMO,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            config.api_key_id = "new-key"


class TestDiscoverCredentials:
    """Tests for discover_credentials function."""

    def test_discovers_credentials(self, tmp_path: Path, tmp_private_key: Path):
        """Successfully discovers credentials from directory."""
        # Create credential directory
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()

        # Create api-key-id.txt
        key_file = cred_dir / "api-key-id.txt"
        key_file.write_text("test-key-id-12345")

        # Copy key to cred_dir
        pem_dest = cred_dir / "private_key.pem"
        pem_dest.write_bytes(tmp_private_key.read_bytes())

        api_key_id, private_key_path = discover_credentials(
            Environment.DEMO,
            project_root=tmp_path,
        )

        assert api_key_id == "test-key-id-12345"
        assert private_key_path == pem_dest

    def test_missing_directory_raises(self, tmp_path: Path):
        """Missing credential directory raises ConfigError."""
        with pytest.raises(ConfigError, match="Credential directory not found"):
            discover_credentials(Environment.DEMO, project_root=tmp_path)

    def test_missing_api_key_file_raises(self, tmp_path: Path, tmp_private_key: Path):
        """Missing api-key-id.txt raises ConfigError."""
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()

        # Add pem but no api-key-id.txt
        pem_dest = cred_dir / "private_key.pem"
        pem_dest.write_bytes(tmp_private_key.read_bytes())

        with pytest.raises(ConfigError, match="API key ID file not found"):
            discover_credentials(Environment.DEMO, project_root=tmp_path)

    def test_empty_api_key_raises(self, tmp_path: Path, tmp_private_key: Path):
        """Empty api-key-id.txt raises ConfigError."""
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()

        key_file = cred_dir / "api-key-id.txt"
        key_file.write_text("   \n  ")  # Whitespace only

        pem_dest = cred_dir / "private_key.pem"
        pem_dest.write_bytes(tmp_private_key.read_bytes())

        with pytest.raises(ConfigError, match="API key ID file is empty"):
            discover_credentials(Environment.DEMO, project_root=tmp_path)

    def test_no_pem_file_raises(self, tmp_path: Path):
        """No .pem file raises ConfigError."""
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()

        key_file = cred_dir / "api-key-id.txt"
        key_file.write_text("test-key-id")

        with pytest.raises(ConfigError, match="No private key file found"):
            discover_credentials(Environment.DEMO, project_root=tmp_path)

    def test_multiple_pem_files_raises(self, tmp_path: Path, tmp_private_key: Path):
        """Multiple .pem files raises ConfigError."""
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()

        key_file = cred_dir / "api-key-id.txt"
        key_file.write_text("test-key-id")

        # Create two pem files
        (cred_dir / "key1.pem").write_bytes(tmp_private_key.read_bytes())
        (cred_dir / "key2.pem").write_bytes(tmp_private_key.read_bytes())

        with pytest.raises(ConfigError, match="Multiple private key files found"):
            discover_credentials(Environment.DEMO, project_root=tmp_path)

    def test_prod_uses_prod_directory(self, tmp_path: Path, tmp_private_key: Path):
        """Prod environment uses api-prod-key directory."""
        cred_dir = tmp_path / "api-prod-key"
        cred_dir.mkdir()

        key_file = cred_dir / "api-key-id.txt"
        key_file.write_text("prod-key-id")

        pem_dest = cred_dir / "private_key.pem"
        pem_dest.write_bytes(tmp_private_key.read_bytes())

        api_key_id, private_key_path = discover_credentials(
            Environment.PROD,
            project_root=tmp_path,
        )

        assert api_key_id == "prod-key-id"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_from_env_vars(self, tmp_private_key: Path, monkeypatch):
        """Config loads from environment variables."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "env-key-id")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_private_key))
        monkeypatch.setenv("KALSHI_ENV", "demo")

        config = load_config()

        assert config.api_key_id == "env-key-id"
        assert config.private_key_path == tmp_private_key
        assert config.environment == Environment.DEMO

    def test_prod_environment(self, tmp_private_key: Path, monkeypatch):
        """KALSHI_ENV=prod sets prod environment."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_private_key))
        monkeypatch.setenv("KALSHI_ENV", "prod")

        config = load_config()

        assert config.environment == Environment.PROD

    def test_env_override_takes_precedence(self, tmp_private_key: Path, monkeypatch):
        """env_override parameter takes precedence over KALSHI_ENV."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_private_key))
        monkeypatch.setenv("KALSHI_ENV", "demo")

        config = load_config(env_override="prod")

        assert config.environment == Environment.PROD

    def test_invalid_env_raises(self, tmp_private_key: Path, monkeypatch):
        """Invalid KALSHI_ENV raises ConfigError."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_private_key))
        monkeypatch.setenv("KALSHI_ENV", "invalid")

        with pytest.raises(ConfigError, match="Invalid KALSHI_ENV"):
            load_config()

    def test_missing_key_file_raises(self, monkeypatch):
        """Missing private key file raises ConfigError."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/nonexistent/path.pem")
        monkeypatch.setenv("KALSHI_ENV", "demo")

        with pytest.raises(ConfigError, match="Private key file not found"):
            load_config()

    def test_defaults_to_demo(self, tmp_private_key: Path, monkeypatch):
        """Default environment is demo when KALSHI_ENV not set."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_private_key))
        monkeypatch.delenv("KALSHI_ENV", raising=False)

        config = load_config()

        assert config.environment == Environment.DEMO


class TestLoadConfigForEnv:
    """Tests for load_config_for_env function."""

    def test_loads_demo_credentials(self, tmp_path: Path, tmp_private_key: Path, monkeypatch):
        """load_config_for_env loads credentials for specified environment."""
        # Set up demo credentials
        cred_dir = tmp_path / "api-demo-key"
        cred_dir.mkdir()
        (cred_dir / "api-key-id.txt").write_text("demo-key")
        (cred_dir / "key.pem").write_bytes(tmp_private_key.read_bytes())

        # Mock _find_project_root to return our tmp_path
        monkeypatch.setattr(
            "prediction_mm.config._find_project_root",
            lambda: tmp_path,
        )

        config = load_config_for_env(Environment.DEMO)

        assert config.api_key_id == "demo-key"
        assert config.environment == Environment.DEMO

    def test_loads_prod_credentials(self, tmp_path: Path, tmp_private_key: Path, monkeypatch):
        """load_config_for_env loads prod credentials."""
        cred_dir = tmp_path / "api-prod-key"
        cred_dir.mkdir()
        (cred_dir / "api-key-id.txt").write_text("prod-key")
        (cred_dir / "key.pem").write_bytes(tmp_private_key.read_bytes())

        monkeypatch.setattr(
            "prediction_mm.config._find_project_root",
            lambda: tmp_path,
        )

        config = load_config_for_env(Environment.PROD)

        assert config.api_key_id == "prod-key"
        assert config.environment == Environment.PROD
