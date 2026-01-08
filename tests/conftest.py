"""Pytest fixtures for prediction-mm tests."""

import pytest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


@pytest.fixture
def tmp_private_key(tmp_path: Path) -> Path:
    """Generate a temporary RSA private key for testing."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(pem)
    return key_path


@pytest.fixture
def fake_env_file(tmp_path: Path, tmp_private_key: Path) -> Path:
    """Create a fake .env file for testing."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"""
KALSHI_API_KEY_ID=test-key-id
KALSHI_PRIVATE_KEY_PATH={tmp_private_key}
KALSHI_ENV=demo
""")
    return env_file
