#!/usr/bin/env python3
"""Smoke test for async pagination utilities with real Kalshi API."""

import asyncio
import sys
import structlog

from prediction_mm.config import load_config
from prediction_mm.client import create_apis, RateLimiter, generate_request_id
from prediction_mm.pagination import paginate, paginate_all

logger = structlog.get_logger()


async def main_async() -> int:
    config = load_config()
    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    try:
        print("=" * 80)
        print("Pagination Smoke Test")
        print("=" * 80)

        # Test 1: Paginate markets (generator approach)
        print("\n1. Testing paginate() with markets (generator)...")
        req_id = generate_request_id()
        logger.info("test_paginate_markets", request_id=req_id, limit=5)

        page_count = 0
        total_markets = 0

        async for page in paginate(apis.client.get_markets, "markets", limit=5, status="open"):
            page_count += 1
            total_markets += len(page)
            print(f"   Page {page_count}: {len(page)} markets")

            if page:
                print(f"     First market: {page[0].ticker}")

            if page_count >= 3:  # Limit to 3 pages for smoke test
                print(f"   (Stopping after 3 pages for smoke test)")
                break

            await rate_limiter.wait()

        print(f"   Total: {total_markets} markets across {page_count} pages")
        print("   ✓ paginate() works!")

        # Test 2: paginate_all (fetch all at once)
        print("\n2. Testing paginate_all() with events...")
        req_id = generate_request_id()
        logger.info("test_paginate_all_events", request_id=req_id, limit=10)

        all_events = await paginate_all(
            apis.client.get_events,
            "events",
            rate_limiter=rate_limiter,
            limit=10,
            status="open",
        )

        print(f"   Total events fetched: {len(all_events)}")
        if all_events:
            print(f"   First event: {all_events[0].event_ticker}")
            print(f"   Last event: {all_events[-1].event_ticker}")
        print("   ✓ paginate_all() works!")

        # Test 3: Paginate portfolio fills (might be empty)
        print("\n3. Testing paginate() with fills...")
        req_id = generate_request_id()
        logger.info("test_paginate_fills", request_id=req_id)

        fill_page_count = 0
        total_fills = 0

        async for page in paginate(apis.client.get_fills, "fills", limit=20):
            fill_page_count += 1
            total_fills += len(page)
            print(f"   Page {fill_page_count}: {len(page)} fills")

            if fill_page_count >= 2:  # Limit to 2 pages
                print(f"   (Stopping after 2 pages for smoke test)")
                break

            if not page:  # Empty page
                print("   (No fills found - this is expected if account has no trades)")
                break

            await rate_limiter.wait()

        print(f"   Total: {total_fills} fills across {fill_page_count} page(s)")
        print("   ✓ Portfolio pagination works!")

        print("\n" + "=" * 80)
        print("✅ All pagination smoke tests passed!")
        print("=" * 80)

        return 0

    finally:
        await apis.client.close()


def main() -> int:
    """Synchronous entry point that runs the async main."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
