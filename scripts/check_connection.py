#!/usr/bin/env python3
"""Verify Kalshi API connectivity."""

import argparse
import asyncio
import sys
import structlog

from prediction_mm.config import load_config
from prediction_mm.client import create_apis, RateLimiter, generate_request_id

logger = structlog.get_logger()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Verify Kalshi API connectivity")
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Use production environment (api-prod-key/). Default is demo.",
    )
    return parser.parse_args()


async def main_async(prod: bool = False) -> int:
    config = load_config(prod=prod)
    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    try:
        # 1. Check exchange status
        req_id = generate_request_id()
        logger.info("checking_exchange_status", request_id=req_id)
        await rate_limiter.wait()
        status = await apis.client.get_exchange_status()
        logger.info(
            "exchange_status",
            request_id=req_id,
            trading_active=status.trading_active,
            exchange_active=status.exchange_active,
        )

        # 2. Fetch balance
        req_id = generate_request_id()
        logger.info("fetching_balance", request_id=req_id)
        await rate_limiter.wait()
        balance = await apis.client.get_balance()
        logger.info("balance", request_id=req_id, balance_cents=balance.balance)

        # 3. Fetch open markets and find highest volume event
        req_id = generate_request_id()
        logger.info("fetching_markets_to_find_highest_volume_event", request_id=req_id)
        await rate_limiter.wait()
        markets_response = await apis.client.get_markets(status="open", limit=100)
        markets = markets_response.markets or []
        logger.info("markets_fetched", request_id=req_id, count=len(markets))

        # Group markets by event and calculate total volume per event
        event_volumes = {}
        event_markets = {}
        for m in markets:
            event_ticker = m.event_ticker
            volume = m.volume or 0
            if event_ticker not in event_volumes:
                event_volumes[event_ticker] = 0
                event_markets[event_ticker] = []
            event_volumes[event_ticker] += volume
            event_markets[event_ticker].append(m)

        # Find event with highest volume
        if event_volumes:
            highest_volume_event = max(event_volumes.items(), key=lambda x: x[1])
            event_ticker, total_volume = highest_volume_event
            markets_in_event = event_markets[event_ticker]

            logger.info(
                "highest_volume_event",
                event_ticker=event_ticker,
                total_volume=total_volume,
                market_count=len(markets_in_event),
            )

            # Show top 5 markets from this event
            markets_in_event.sort(key=lambda m: m.volume or 0, reverse=True)
            for m in markets_in_event[:5]:
                logger.info(
                    "market",
                    ticker=m.ticker,
                    title=m.title[:50] if m.title else "",
                    yes_bid=m.yes_bid,
                    yes_ask=m.yes_ask,
                    volume=m.volume or 0,
                )

            # 4. Fetch orderbook for highest volume market in this event
            if markets_in_event:
                highest_volume_market = markets_in_event[0]
                ticker = highest_volume_market.ticker
                req_id = generate_request_id()
                logger.info("fetching_orderbook", request_id=req_id, ticker=ticker)
                await rate_limiter.wait()
                orderbook = await apis.client.get_market_orderbook(ticker=ticker)
                ob = orderbook.orderbook
                logger.info(
                    "orderbook",
                    request_id=req_id,
                    ticker=ticker,
                    yes_levels=len(ob.yes) if hasattr(ob, 'yes') and ob.yes else 0,
                    no_levels=len(ob.no) if hasattr(ob, 'no') and ob.no else 0,
                )
        else:
            logger.warning("no_markets_found")

        logger.info("connection_check_complete")
        return 0

    finally:
        await apis.client.close()


def main() -> int:
    """Synchronous entry point that runs the async main."""
    args = parse_args()
    return asyncio.run(main_async(prod=args.prod))


if __name__ == "__main__":
    sys.exit(main())
