"""Kalshi REST API client for fetching orderbook snapshots."""

import httpx
import structlog

from prediction_mm.auth import KalshiAuth
from prediction_mm.config import Config

logger = structlog.get_logger()


class KalshiRestClient:
    """REST client for Kalshi API.

    Handles authenticated requests to fetch orderbook snapshots.
    """

    def __init__(self, config: Config, auth: KalshiAuth):
        """Initialize REST client.

        Args:
            config: Application configuration.
            auth: Authentication handler with loaded private key.
        """
        self._config = config
        self._auth = auth
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def get_orderbook(self, ticker: str) -> dict:
        """Fetch full orderbook snapshot for a market.

        Args:
            ticker: Market ticker (e.g., "INFLATION-2026-JAN").

        Returns:
            Dict with 'yes' and 'no' lists of [price, size] pairs.

        Raises:
            httpx.HTTPStatusError: If request fails.
        """
        path = f"/markets/{ticker}/orderbook"
        url = f"{self._config.base_url}{path}"

        # Get auth headers
        headers = self._auth.get_auth_headers("GET", f"/trade-api/v2{path}")

        log = logger.bind(ticker=ticker, url=url)
        log.info("fetching_orderbook_snapshot")

        response = await self._client.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        orderbook = data.get("orderbook", {})

        # Parse response into standardized format
        # Kalshi returns: {"yes": [[price, size], ...], "no": [[price, size], ...]}
        # Handle None values (empty orderbook)
        yes_levels = orderbook.get("yes") or []
        no_levels = orderbook.get("no") or []

        log.info(
            "orderbook_snapshot_received",
            yes_levels=len(yes_levels),
            no_levels=len(no_levels),
        )

        return {
            "yes": yes_levels,
            "no": no_levels,
        }
