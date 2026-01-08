"""WebSocket data feed handler for Kalshi."""

import asyncio
import json
from typing import Callable, Awaitable

import structlog
import websockets

from prediction_mm.auth import KalshiAuth
from prediction_mm.config import Config

logger = structlog.get_logger()

# Reconnection settings
INITIAL_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 60.0
RECONNECT_MULTIPLIER = 2.0
CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 5


class FeedError(Exception):
    """Raised for feed connection errors."""
    pass


class KalshiFeed:
    """
    WebSocket data feed for Kalshi.

    Handles:
    - Authenticated WebSocket connection
    - Subscription to ticker and orderbook_delta channels
    - Automatic reconnection with exponential backoff
    - Parsing of incoming messages
    """

    def __init__(self, config: Config, auth: KalshiAuth):
        """
        Initialize the feed.

        Args:
            config: Application configuration.
            auth: Authentication handler (must have private key loaded).
        """
        self._config = config
        self._auth = auth
        self._ws = None
        self._running = False
        self._reconnect_delay = INITIAL_RECONNECT_DELAY
        self._consecutive_failures = 0
        self._command_id = 0

        # Subscriptions
        self._subscribed_tickers: set[str] = set()

        # Callbacks
        self._orderbook_callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._ticker_callbacks: list[Callable[[dict], Awaitable[None]]] = []

    @property
    def ws_url(self) -> str:
        return self._config.ws_url

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.open

    def _next_command_id(self) -> int:
        """Generate unique command ID."""
        self._command_id += 1
        return self._command_id

    async def connect(self) -> None:
        """
        Establish authenticated WebSocket connection.

        Raises:
            FeedError: If connection fails.
        """
        if self._ws is not None:
            return

        # Get auth headers for WebSocket handshake
        path = "/trade-api/ws/v2"
        headers = self._auth.get_auth_headers("GET", path)

        log = logger.bind(url=self.ws_url)
        log.info("feed_connecting")

        try:
            self._ws = await websockets.connect(
                self.ws_url,
                extra_headers=headers,
            )
            self._reconnect_delay = INITIAL_RECONNECT_DELAY
            self._consecutive_failures = 0
            log.info("feed_connected")
        except Exception as e:
            self._consecutive_failures += 1
            log.error("feed_connection_failed", error=str(e))
            raise FeedError(f"WebSocket connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("feed_disconnected")

    async def subscribe_ticker(self) -> None:
        """Subscribe to ticker channel for all markets."""
        await self._subscribe(["ticker"])

    async def subscribe_orderbook(self, ticker: str) -> None:
        """
        Subscribe to orderbook_delta channel for a specific market.

        Args:
            ticker: Market ticker to subscribe to.
        """
        self._subscribed_tickers.add(ticker)
        await self._subscribe(["orderbook_delta"], ticker)

    async def unsubscribe_orderbook(self, ticker: str) -> None:
        """Unsubscribe from orderbook updates for a market."""
        self._subscribed_tickers.discard(ticker)
        await self._unsubscribe(["orderbook_delta"], ticker)

    async def _subscribe(self, channels: list[str], market_ticker: str | None = None) -> None:
        """Send subscription command."""
        if not self.is_connected:
            raise FeedError("Not connected")

        msg: dict = {
            "id": self._next_command_id(),
            "cmd": "subscribe",
            "params": {
                "channels": channels,
            },
        }
        if market_ticker:
            msg["params"]["market_ticker"] = market_ticker

        await self._ws.send(json.dumps(msg))  # type: ignore
        logger.info("feed_subscribed", channels=channels, ticker=market_ticker)

    async def _unsubscribe(self, channels: list[str], market_ticker: str | None = None) -> None:
        """Send unsubscribe command."""
        if not self.is_connected:
            return

        msg: dict = {
            "id": self._next_command_id(),
            "cmd": "unsubscribe",
            "params": {
                "channels": channels,
            },
        }
        if market_ticker:
            msg["params"]["market_ticker"] = market_ticker

        await self._ws.send(json.dumps(msg))  # type: ignore
        logger.info("feed_unsubscribed", channels=channels, ticker=market_ticker)

    def on_orderbook(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        """Register callback for orderbook updates.

        Callback receives a dict with:
            - market_ticker: str
            - yes_bids: list of [price, quantity] pairs (descending by price)
            - no_bids: list of [price, quantity] pairs (descending by price)
        """
        self._orderbook_callbacks.append(callback)

    def on_ticker(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        """Register callback for ticker updates."""
        self._ticker_callbacks.append(callback)

    async def run(self) -> None:
        """
        Run the feed, processing messages and handling reconnection.

        Runs until disconnect() is called.
        """
        self._running = True

        while self._running:
            try:
                if not self.is_connected:
                    await self.connect()
                    # Resubscribe after reconnection
                    for ticker in list(self._subscribed_tickers):
                        await self._subscribe(["orderbook_delta"], ticker)

                await self._message_loop()

            except websockets.ConnectionClosed as e:
                logger.warning("feed_connection_closed", code=e.code, reason=e.reason)
                self._ws = None

                if self._running:
                    await self._reconnect()

            except Exception as e:
                logger.error("feed_error", error=str(e))
                self._ws = None

                if self._running:
                    await self._reconnect()

    async def _message_loop(self) -> None:
        """Process incoming messages."""
        if not self._ws:
            return

        async for raw_msg in self._ws:
            if not self._running:
                break

            try:
                msg = json.loads(raw_msg)
                await self._handle_message(msg)
            except json.JSONDecodeError:
                logger.warning("feed_invalid_json", raw=str(raw_msg)[:200])
            except Exception as e:
                logger.error("feed_message_error", error=str(e))

    async def _handle_message(self, msg: dict) -> None:
        """Handle a parsed message."""
        msg_type = msg.get("type")

        if msg_type == "orderbook_snapshot":
            await self._handle_orderbook_snapshot(msg)

        elif msg_type == "orderbook_delta":
            # Delta updates would require maintaining local state
            # For now, just log
            logger.debug("orderbook_delta", msg=msg)

        elif msg_type == "ticker":
            await self._handle_ticker(msg)

        elif msg_type == "subscribed":
            logger.info("subscription_confirmed", msg=msg)

        elif msg_type == "error":
            logger.error("feed_error_message", msg=msg)

        else:
            logger.debug("feed_unhandled_message", type=msg_type)

    async def _handle_orderbook_snapshot(self, msg: dict) -> None:
        """Handle orderbook snapshot message."""
        data = msg.get("msg", {})
        ticker = data.get("market_ticker")
        if not ticker:
            return

        # Parse YES bids (reverse to get descending order)
        yes_raw = data.get("yes", [])
        yes_bids = [
            [level[0], level[1]]
            for level in reversed(yes_raw)
            if len(level) >= 2 and level[1] > 0
        ]

        # Parse NO bids (reverse to get descending order)
        no_raw = data.get("no", [])
        no_bids = [
            [level[0], level[1]]
            for level in reversed(no_raw)
            if len(level) >= 2 and level[1] > 0
        ]

        orderbook_data = {
            "market_ticker": ticker,
            "yes_bids": yes_bids,
            "no_bids": no_bids,
        }

        for callback in self._orderbook_callbacks:
            await callback(orderbook_data)

    async def _handle_ticker(self, msg: dict) -> None:
        """Handle ticker message."""
        for callback in self._ticker_callbacks:
            await callback(msg)

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        self._consecutive_failures += 1

        if self._consecutive_failures >= CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
            logger.error(
                "feed_consecutive_failures",
                count=self._consecutive_failures,
                threshold=CONSECUTIVE_FAILURE_ALERT_THRESHOLD,
            )

        logger.info("feed_reconnecting", delay=self._reconnect_delay)
        await asyncio.sleep(self._reconnect_delay)

        # Exponential backoff
        self._reconnect_delay = min(
            self._reconnect_delay * RECONNECT_MULTIPLIER,
            MAX_RECONNECT_DELAY,
        )
