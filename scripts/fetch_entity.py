#!/usr/bin/env python3
"""Classify and fetch information for series, events, or markets.

This script intelligently determines whether a given identifier is a series,
event, or market ticker, then fetches all available information for that entity.

Classification Rules:
- Series: No hyphens (e.g., "INX", "KXNCAAFGAME")
- Event: 1 hyphen (e.g., "INXM-20250101", "KXNCAAFGAME-26JAN08MIAMISS")
- Market: 2 hyphens (e.g., "INXM-20250101-Y", "KXNCAAFGAME-26JAN08MIAMISS-MIA")

Usage:
    python scripts/fetch_entity.py <ticker>

Examples:
    python scripts/fetch_entity.py INX                    # Fetch series
    python scripts/fetch_entity.py INXM-20250101          # Fetch event
    python scripts/fetch_entity.py INXM-20250101-Y        # Fetch market
"""

import asyncio
import sys
import structlog

from prediction_mm.config import load_config
from prediction_mm.client import create_apis, RateLimiter
from prediction_mm.pagination import paginate_all

logger = structlog.get_logger()


class EntityClassifier:
    """Classify ticker strings as series, event, or market identifiers."""

    @staticmethod
    def classify(ticker: str) -> str:
        """Classify a ticker string based on hyphen count.

        Args:
            ticker: The identifier to classify

        Returns:
            One of: "series", "event", "market"

        Rules:
            - Series: 0 hyphens (e.g., "INX", "KXNCAAFGAME")
            - Event: 1 hyphen (e.g., "INXM-20250101", "KXNCAAFGAME-26JAN08MIAMISS")
            - Market: 2 hyphens (e.g., "INXM-20250101-Y", "KXNCAAFGAME-26JAN08MIAMISS-MIA")
        """
        hyphen_count = ticker.count("-")

        if hyphen_count == 0:
            return "series"
        elif hyphen_count == 1:
            return "event"
        elif hyphen_count == 2:
            return "market"
        else:
            # More than 2 hyphens - unusual, but default to market
            return "market"


async def fetch_series_info(client, ticker: str, rate_limiter: RateLimiter) -> None:
    """Fetch and display information about a series."""
    print(f"\n{'=' * 80}")
    print(f"SERIES: {ticker}")
    print(f"{'=' * 80}\n")

    # Fetch all events in this series
    print(f"Fetching events for series '{ticker}'...")
    try:
        events = await paginate_all(
            client.get_events,
            "events",
            rate_limiter=rate_limiter,
            series_ticker=ticker,
            limit=100
        )
    except Exception as e:
        print(f"⚠️  Error fetching events: {e}")
        events = []

    print(f"\n📋 Found {len(events)} event(s) in series '{ticker}'")

    if events:
        print()
        for i, event in enumerate(events, 1):
            print(f"{i}. Event: {event.event_ticker}")
            print(f"   Title: {event.title}")
            if hasattr(event, 'status') and event.status:
                print(f"   Status: {event.status}")
            if hasattr(event, 'subtitle') and event.subtitle:
                print(f"   Subtitle: {event.subtitle}")
            print()
    else:
        print("   (No events found for this series)")
        print()

    # Fetch all markets in this series
    print(f"Fetching markets for series '{ticker}'...")
    try:
        markets = await paginate_all(
            client.get_markets,
            "markets",
            rate_limiter=rate_limiter,
            series_ticker=ticker,
            limit=100
        )
    except Exception as e:
        print(f"⚠️  Error fetching markets: {e}")
        markets = []

    print(f"\n📊 Found {len(markets)} market(s) in series '{ticker}'")

    if not markets:
        print("   (No markets found for this series)")
        print()
        if not events:
            print(f"⚠️  Series '{ticker}' may not exist or has no active events/markets.")
        return

    # Group markets by event
    event_markets = {}
    for market in markets:
        event_ticker = market.event_ticker
        if event_ticker not in event_markets:
            event_markets[event_ticker] = []
        event_markets[event_ticker].append(market)

    print()
    for event_ticker, event_markets_list in event_markets.items():
        print(f"  Event: {event_ticker} ({len(event_markets_list)} markets)")
        for market in event_markets_list:
            print(f"    - {market.ticker}")
            print(f"      Title: {market.title}")
            print(f"      Status: {market.status}")
            if market.yes_bid and market.yes_ask:
                print(f"      YES: {market.yes_bid}¢ / {market.yes_ask}¢")
            if market.volume:
                print(f"      Volume: {market.volume:,}")
        print()


async def fetch_event_info(client, ticker: str, rate_limiter: RateLimiter) -> None:
    """Fetch and display information about an event."""
    print(f"\n{'=' * 80}")
    print(f"EVENT: {ticker}")
    print(f"{'=' * 80}\n")

    # Fetch markets for this event
    print(f"Fetching markets for event '{ticker}'...")
    try:
        markets = await paginate_all(
            client.get_markets,
            "markets",
            rate_limiter=rate_limiter,
            event_ticker=ticker,
            limit=100
        )
    except Exception as e:
        print(f"⚠️  Error fetching markets: {e}")
        markets = []

    if not markets:
        print(f"⚠️  No markets found for event '{ticker}'")
        print("   This event may not exist or may have no associated markets.")
        return

    # Display event information (derived from first market)
    first_market = markets[0]
    print(f"Event Ticker: {first_market.event_ticker}")
    print()

    print(f"📊 Found {len(markets)} market(s) in this event:\n")

    for i, market in enumerate(markets, 1):
        print(f"{i}. Market: {market.ticker}")
        print(f"   Title: {market.title}")
        if market.subtitle:
            print(f"   Subtitle: {market.subtitle}")
        print(f"   Status: {market.status}")
        print(f"   Open: {market.open_time}")
        print(f"   Close: {market.close_time}")

        if market.yes_bid and market.yes_ask:
            print(f"   YES: {market.yes_bid}¢ bid / {market.yes_ask}¢ ask")
            print(f"   NO:  {market.no_bid}¢ bid / {market.no_ask}¢ ask")

        if market.last_price:
            print(f"   Last Price: {market.last_price}¢")

        if market.volume:
            print(f"   Volume: {market.volume:,}")
        if market.volume_24h:
            print(f"   Volume (24h): {market.volume_24h:,}")

        if market.result:
            print(f"   Result: {market.result.upper()}")

        print()


async def fetch_market_info(client, ticker: str, rate_limiter: RateLimiter) -> None:
    """Fetch and display information about a specific market."""
    print(f"\n{'=' * 80}")
    print(f"MARKET: {ticker}")
    print(f"{'=' * 80}\n")

    # Fetch the specific market by ticker
    print(f"Fetching market '{ticker}'...")

    # Use the markets API with ticker filter
    try:
        response = await client.get_markets(tickers=ticker, limit=1)
    except Exception as e:
        print(f"⚠️  Error fetching market: {e}")
        return

    if not response.markets or len(response.markets) == 0:
        print(f"⚠️  Market '{ticker}' not found.")
        print("   This market may not exist or the ticker may be incorrect.")
        return

    market = response.markets[0]

    # Display comprehensive market information
    print(f"Market Ticker: {market.ticker}")
    print(f"Event: {market.event_ticker}")
    print()

    print(f"📝 Market Details:")
    print(f"   Title: {market.title}")
    if market.subtitle:
        print(f"   Subtitle: {market.subtitle}")
    print(f"   Status: {market.status}")
    print(f"   Market Type: {market.market_type}")
    print()

    print(f"⏰ Timing:")
    print(f"   Created: {market.created_time}")
    print(f"   Open Time: {market.open_time}")
    print(f"   Close Time: {market.close_time}")
    print(f"   Expiration: {market.expiration_time}")
    print(f"   Can Close Early: {market.can_close_early}")
    print()

    print(f"💰 Pricing (units: {market.response_price_units}):")
    if market.yes_bid and market.yes_ask:
        spread_yes = market.yes_ask - market.yes_bid
        print(f"   YES: {market.yes_bid}¢ bid / {market.yes_ask}¢ ask (spread: {spread_yes}¢)")
        print(f"   NO:  {market.no_bid}¢ bid / {market.no_ask}¢ ask")
    else:
        print(f"   No active pricing available")

    if market.last_price:
        print(f"   Last Price: {market.last_price}¢ (${market.last_price_dollars})")
    print()

    print(f"📊 Volume & Liquidity:")
    if market.volume:
        print(f"   Total Volume: {market.volume:,}")
    if market.volume_24h:
        print(f"   Volume (24h): {market.volume_24h:,}")
    if market.liquidity:
        print(f"   Liquidity: {market.liquidity}¢ (${market.liquidity_dollars})")
    if market.open_interest:
        print(f"   Open Interest: {market.open_interest:,}")
    print()

    if market.result:
        print(f"🏆 Result: {market.result.upper()}")
        if market.settlement_value is not None:
            print(f"   Settlement Value: {market.settlement_value}¢ (${market.settlement_value_dollars})")
        print()

    # Fetch orderbook for additional detail
    print(f"Fetching orderbook...")
    try:
        orderbook_response = await client.get_market_orderbook(ticker=ticker)
        if hasattr(orderbook_response, 'orderbook'):
            orderbook = orderbook_response.orderbook
            print(f"\n📖 Orderbook:")

            if hasattr(orderbook, 'yes') and orderbook.yes:
                print(f"   YES side: {len(orderbook.yes)} order(s)")
                for i, order in enumerate(orderbook.yes[:5], 1):
                    print(f"      {i}. {order.quantity} @ {order.price}¢")
                if len(orderbook.yes) > 5:
                    print(f"      ... and {len(orderbook.yes) - 5} more")

            if hasattr(orderbook, 'no') and orderbook.no:
                print(f"   NO side: {len(orderbook.no)} order(s)")
                for i, order in enumerate(orderbook.no[:5], 1):
                    print(f"      {i}. {order.quantity} @ {order.price}¢")
                if len(orderbook.no) > 5:
                    print(f"      ... and {len(orderbook.no) - 5} more")
        else:
            print(f"   (No orderbook data available)")
    except Exception as e:
        print(f"   ⚠️  Could not fetch orderbook: {e}")


async def main_async() -> int:
    """Main async entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/fetch_entity.py <ticker>")
        print()
        print("Examples:")
        print("  python scripts/fetch_entity.py INX                    # Fetch series")
        print("  python scripts/fetch_entity.py INXM-20250101          # Fetch event")
        print("  python scripts/fetch_entity.py INXM-20250101-Y        # Fetch market")
        return 1

    ticker = sys.argv[1].strip()

    # Load config and create API clients
    config = load_config()
    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    # Classify the ticker
    classifier = EntityClassifier()
    entity_type = classifier.classify(ticker)

    logger.info("fetch_entity", ticker=ticker, entity_type=entity_type)

    # Fetch and display information based on entity type
    try:
        if entity_type == "series":
            await fetch_series_info(apis.client, ticker, rate_limiter)
        elif entity_type == "event":
            await fetch_event_info(apis.client, ticker, rate_limiter)
        elif entity_type == "market":
            await fetch_market_info(apis.client, ticker, rate_limiter)
        else:
            print(f"⚠️  Unknown entity type: {entity_type}")
            return 1

        print(f"{'=' * 80}")
        print(f"✅ Successfully fetched information for {entity_type}: {ticker}")
        print(f"{'=' * 80}")

        return 0

    except Exception as e:
        logger.error("fetch_entity_failed", ticker=ticker, error=str(e))
        print(f"\n❌ Error fetching information: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Close the client session
        await apis.client.close()


def main() -> int:
    """Synchronous entry point that runs the async main."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
