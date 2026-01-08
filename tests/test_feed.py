"""Tests for WebSocket data feed."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from prediction_mm.config import Config, Environment
from prediction_mm.auth import KalshiAuth
from prediction_mm.data.feed import KalshiFeed, FeedError


class TestKalshiFeed:
    """Tests for KalshiFeed class."""

    @pytest.fixture
    def config(self, tmp_private_key: Path) -> Config:
        """Create test config."""
        return Config(
            api_key_id="test-key-id",
            private_key_path=tmp_private_key,
            environment=Environment.DEMO,
        )

    @pytest.fixture
    def auth(self, config: Config) -> KalshiAuth:
        """Create test auth."""
        auth = KalshiAuth(config.api_key_id, config.private_key_path)
        auth.load_private_key()
        return auth

    def test_init(self, config: Config, auth: KalshiAuth):
        """Feed initializes with config and auth."""
        feed = KalshiFeed(config, auth)

        assert feed.ws_url == config.ws_url
        assert not feed.is_connected

    def test_ws_url_demo(self, config: Config, auth: KalshiAuth):
        """Demo environment uses demo WebSocket URL."""
        feed = KalshiFeed(config, auth)
        assert "demo-api.kalshi.co" in feed.ws_url

    def test_ws_url_prod(self, tmp_private_key: Path):
        """Prod environment uses prod WebSocket URL."""
        config = Config(
            api_key_id="test-key-id",
            private_key_path=tmp_private_key,
            environment=Environment.PROD,
        )
        auth = KalshiAuth(config.api_key_id, config.private_key_path)
        auth.load_private_key()

        feed = KalshiFeed(config, auth)
        assert "api.elections.kalshi.com" in feed.ws_url

    def test_on_orderbook_registers_callback(self, config: Config, auth: KalshiAuth):
        """on_orderbook registers callback."""
        feed = KalshiFeed(config, auth)
        callback = AsyncMock()

        feed.on_orderbook(callback)

        assert callback in feed._orderbook_callbacks

    def test_on_ticker_registers_callback(self, config: Config, auth: KalshiAuth):
        """on_ticker registers callback."""
        feed = KalshiFeed(config, auth)
        callback = AsyncMock()

        feed.on_ticker(callback)

        assert callback in feed._ticker_callbacks


class TestFeedMessageParsing:
    """Tests for feed message parsing."""

    @pytest.fixture
    def feed(self, tmp_private_key: Path) -> KalshiFeed:
        """Create test feed."""
        config = Config(
            api_key_id="test-key-id",
            private_key_path=tmp_private_key,
            environment=Environment.DEMO,
        )
        auth = KalshiAuth(config.api_key_id, config.private_key_path)
        auth.load_private_key()
        return KalshiFeed(config, auth)

    @pytest.mark.asyncio
    async def test_handle_orderbook_snapshot(self, feed: KalshiFeed):
        """Orderbook snapshot triggers callback with parsed orderbook dict."""
        callback = AsyncMock()
        feed.on_orderbook(callback)

        msg = {
            "type": "orderbook_snapshot",
            "msg": {
                "market_ticker": "TEST-TICKER",
                "yes": [[40, 10], [45, 20]],
                "no": [[55, 15]],
            },
        }

        await feed._handle_message(msg)

        callback.assert_called_once()
        orderbook = callback.call_args[0][0]
        assert orderbook["market_ticker"] == "TEST-TICKER"
        assert len(orderbook["yes_bids"]) == 2
        assert orderbook["yes_bids"][0][0] == 45  # Best bid first (price)
        assert orderbook["yes_bids"][0][1] == 20  # quantity

    @pytest.mark.asyncio
    async def test_handle_ticker(self, feed: KalshiFeed):
        """Ticker message triggers callback."""
        callback = AsyncMock()
        feed.on_ticker(callback)

        msg = {
            "type": "ticker",
            "msg": {"market_ticker": "TEST", "price": 50},
        }

        await feed._handle_message(msg)

        callback.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_handle_unknown_type_no_error(self, feed: KalshiFeed):
        """Unknown message types are handled gracefully."""
        msg = {"type": "unknown_type", "data": "test"}

        # Should not raise
        await feed._handle_message(msg)
