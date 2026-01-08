#!/usr/bin/env python3
"""Place and cancel a test order in the Kalshi sandbox."""

import asyncio
import sys
import uuid
import structlog

from prediction_mm.config import load_config
from prediction_mm.client import create_apis, RateLimiter, generate_request_id

logger = structlog.get_logger()


async def main_async() -> int:
    config = load_config()

    if "demo" not in config.host:
        logger.error("refusing_production", host=config.host)
        print("ERROR: This script only runs against demo environment.")
        return 1

    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    try:
        # 1. Find highest volume market with liquidity
        req_id = generate_request_id()
        logger.info("finding_highest_volume_liquid_market", request_id=req_id)
        await rate_limiter.wait()
        markets_response = await apis.client.get_markets(status="open", limit=1000)
        markets = markets_response.markets or []

        # Filter for markets with liquidity and sort by volume
        liquid_markets = [
            m for m in markets
            if m.yes_bid and m.yes_bid > 0 and m.yes_ask and m.yes_ask < 100
        ]

        if not liquid_markets:
            logger.error("no_liquid_market_found")
            return 1

        # Sort by volume (descending) to get highest volume market
        liquid_markets.sort(key=lambda m: m.volume or 0, reverse=True)
        target_market = liquid_markets[0]

        ticker = target_market.ticker
        logger.info(
            "selected_market",
            ticker=ticker,
            yes_bid=target_market.yes_bid,
            yes_ask=target_market.yes_ask,
            volume=target_market.volume or 0,
            event_ticker=target_market.event_ticker,
        )

        # 2. Place a limit order at 1 cent (unlikely to fill)
        client_order_id = str(uuid.uuid4())
        req_id = generate_request_id()
        logger.info(
            "placing_order",
            request_id=req_id,
            ticker=ticker,
            side="yes",
            action="buy",
            count=1,
            yes_price=1,
            client_order_id=client_order_id,
        )
        await rate_limiter.wait()
        create_response = await apis.client.create_order(
            ticker=ticker,
            side="yes",
            action="buy",
            count=1,
            type="limit",
            yes_price=1,
            client_order_id=client_order_id,
        )
        order = create_response.order
        order_id = order.order_id
        logger.info("order_placed", request_id=req_id, order_id=order_id, status=order.status)

        # 3. Verify order is resting
        if order.status != "resting":
            logger.warning("unexpected_status", status=order.status)

        # 4. Cancel the order
        req_id = generate_request_id()
        logger.info("canceling_order", request_id=req_id, order_id=order_id)
        await rate_limiter.wait()
        cancel_response = await apis.client.cancel_order(order_id=order_id)
        canceled_order = cancel_response.order
        logger.info("order_canceled", request_id=req_id, status=canceled_order.status)

        # 5. Verify cancellation
        if canceled_order.status != "canceled":
            logger.error("cancel_failed", status=canceled_order.status)
            return 1

        logger.info("demo_trade_complete")
        return 0

    finally:
        await apis.client.close()


def main() -> int:
    """Synchronous entry point that runs the async main."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
