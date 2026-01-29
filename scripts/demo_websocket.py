#!/usr/bin/env python3
"""Demo WebSocket data feed with live orderbook updates.

This script demonstrates:
1. Connecting to Kalshi WebSocket API
2. Subscribing to orderbook updates for a market
3. Handling live orderbook snapshots
4. Graceful shutdown

The script will run for 30 seconds or until Ctrl+C.
"""

import asyncio
import sys
import signal
import structlog
from datetime import datetime

from prediction_mm.config import load_config
from prediction_mm.auth import create_auth
from prediction_mm.data import KalshiFeed
from prediction_mm.client import create_apis, RateLimiter

logger = structlog.get_logger()


class WebSocketDemo:
    """Demo handler for WebSocket feed."""

    def __init__(self):
        self.orderbook_count = 0
        self.ticker_count = 0
        self.running = True

    async def handle_orderbook(self, data: dict) -> None:
        """Handle orderbook snapshot updates."""
        self.orderbook_count += 1
        ticker = data["market_ticker"]
        yes_bids = data["yes_bids"]
        no_bids = data["no_bids"]

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] Orderbook Update #{self.orderbook_count} - {ticker}")

        if yes_bids:
            print(f"  YES bids: {len(yes_bids)} levels")
            for i, (price, qty) in enumerate(yes_bids[:3], 1):
                print(f"    {i}. {price}¢ x {qty}")
            if len(yes_bids) > 3:
                print(f"    ... {len(yes_bids) - 3} more levels")
        else:
            print("  YES bids: (empty)")

        if no_bids:
            print(f"  NO bids: {len(no_bids)} levels")
            for i, (price, qty) in enumerate(no_bids[:3], 1):
                print(f"    {i}. {price}¢ x {qty}")
            if len(no_bids) > 3:
                print(f"    ... {len(no_bids) - 3} more levels")
        else:
            print("  NO bids: (empty)")

    async def handle_ticker(self, msg: dict) -> None:
        """Handle ticker updates."""
        self.ticker_count += 1
        logger.debug("ticker_update", count=self.ticker_count)


async def find_active_market(apis, rate_limiter):
    """Find an active market with orderbook activity."""
    logger.info("finding_active_market")

    await rate_limiter.wait()
    markets_response = await apis.client.get_markets(status="open", limit=100)
    markets = markets_response.markets or []

    # Filter for markets with active pricing
    active_markets = [
        m for m in markets
        if m.yes_bid and m.yes_ask and m.yes_bid > 0 and m.yes_ask < 100
    ]

    if not active_markets:
        return None

    # Sort by liquidity to find most active
    active_markets.sort(key=lambda m: m.liquidity or 0, reverse=True)
    return active_markets[0]


async def main_async() -> int:
    """Main async entry point."""
    config = load_config()

    if "demo" not in config.host:
        logger.error("refusing_production", host=config.host)
        print("ERROR: This demo only runs against demo environment.")
        return 1

    # Find an active market
    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    try:
        market = await find_active_market(apis, rate_limiter)
        if not market:
            print("ERROR: No active markets found with pricing")
            return 1

        ticker = market.ticker
        print(f"\n{'=' * 80}")
        print(f"WebSocket Feed Demo")
        print(f"{'=' * 80}\n")
        print(f"Market: {ticker}")
        print(f"Title: {market.title}")
        print(f"Current spread: {market.yes_bid}¢ / {market.yes_ask}¢")
        print(f"\nConnecting to WebSocket feed...")
        print("(Press Ctrl+C to stop)\n")

    finally:
        await apis.client.close()

    # Create WebSocket feed
    auth = create_auth(config.api_key_id, config.private_key_path)
    feed = KalshiFeed(config, auth)
    demo = WebSocketDemo()

    # Register callbacks
    feed.on_orderbook(demo.handle_orderbook)
    feed.on_ticker(demo.handle_ticker)

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        print("\n\nShutting down gracefully...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)

    # Connect and subscribe
    try:
        await feed.connect()
        logger.info("websocket_connected")

        await feed.subscribe_orderbook(ticker)
        logger.info("subscribed_to_orderbook", ticker=ticker)

        print("Connected! Waiting for orderbook updates...\n")
        print("(If no updates appear, the market may have no active trading)")
        print("(The connection is working - updates will appear when orders are placed)\n")

        # Run feed in background
        feed_task = asyncio.create_task(feed.run())

        # Wait for shutdown signal or timeout (30 seconds)
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            print("\n\nDemo timeout (30 seconds) - shutting down...")

        # Disconnect
        await feed.disconnect()
        feed_task.cancel()

        try:
            await feed_task
        except asyncio.CancelledError:
            pass

        print(f"\n{'=' * 80}")
        print(f"Demo Complete")
        print(f"{'=' * 80}")
        print(f"Orderbook updates received: {demo.orderbook_count}")
        print(f"Ticker updates received: {demo.ticker_count}")
        print(f"{'=' * 80}\n")

        return 0

    except Exception as e:
        logger.error("websocket_error", error=str(e))
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    """Synchronous entry point that runs the async main."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
