"""Async client utilities for the Kalshi API."""

import asyncio
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import structlog

# Apply model patches BEFORE importing SDK
from prediction_mm.models import patch_market_model
patch_market_model()

# Now import SDK
from kalshi_python_async import Configuration, KalshiClient

logger = structlog.get_logger()


class KalshiApis(NamedTuple):
    """Container for Kalshi API client."""
    client: KalshiClient


async def create_apis(host: str, api_key_id: str, private_key_path: str) -> KalshiApis:
    """Create and authenticate Kalshi API client.

    Args:
        host: API base URL (demo or production).
        api_key_id: Kalshi API key ID.
        private_key_path: Path to RSA private key PEM file.

    Returns:
        KalshiApis named tuple with the API client.
    """
    # Read the private key
    private_key_pem = Path(private_key_path).read_text()

    # Create configuration
    config = Configuration(host=host)
    config.api_key_id = api_key_id
    config.private_key_pem = private_key_pem

    # Create client with auth
    client = KalshiClient(configuration=config)

    return KalshiApis(client=client)


class RateLimiter:
    """Rate limiter for API calls. Call wait() before each request."""

    def __init__(self, requests_per_second: float = 20.0):
        self.min_interval = 1.0 / requests_per_second
        self.last_request = 0.0

    async def wait(self) -> None:
        """Block until enough time has passed since last request."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self.last_request = time.time()


def generate_request_id() -> str:
    """Generate a 12-char hex request ID for log correlation."""
    return uuid.uuid4().hex[:12]
