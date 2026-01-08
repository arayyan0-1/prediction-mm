"""Async cursor-based pagination utilities for Kalshi SDK.

The Kalshi API uses cursor-based pagination. This module provides
generic utilities to iterate through paginated endpoints asynchronously.

See: https://docs.kalshi.com/getting_started/pagination

Example:
    # Async generator approach (recommended for large datasets)
    from prediction_mm.client import create_apis, RateLimiter
    from prediction_mm.pagination import paginate
    from prediction_mm.config import load_config
    import asyncio

    async def main():
        config = load_config()
        apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
        rate_limiter = RateLimiter()

        async for page in paginate(apis.client.get_markets, "markets", status="open"):
            await rate_limiter.wait()  # Rate limit between pages
            for market in page:
                print(f"{market.ticker}: {market.yes_bid}")

        # Fetch all at once (convenience, use with caution)
        all_markets = await paginate_all(
            apis.client.get_markets,
            "markets",
            rate_limiter=rate_limiter,
            status="open"
        )

    asyncio.run(main())
"""

from typing import Any, AsyncIterator, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from prediction_mm.client import RateLimiter

__all__ = ["paginate", "paginate_all"]


async def paginate(
    fetch_fn: Callable[..., Any],
    items_field: str,
    cursor_field: str = "cursor",
    limit: int = 100,
    **kwargs: Any,
) -> AsyncIterator[list[Any]]:
    """Async generic paginator for Kalshi SDK methods.

    Yields pages of items. Caller is responsible for rate limiting between pages.

    Args:
        fetch_fn: Async SDK method to call (e.g., apis.client.get_markets)
        items_field: Attribute name on response containing the list (e.g., "markets")
        cursor_field: Attribute name for pagination cursor (default: "cursor")
        limit: Items per page (default: 100, max: 100)
        **kwargs: Additional parameters to pass to fetch_fn

    Yields:
        List of items for each page. Empty list if no items.

    Example:
        async for page in paginate(apis.client.get_markets, "markets", status="open"):
            for market in page:
                print(market.ticker)
    """
    cursor: str | None = None

    while True:
        # Build request kwargs
        request_kwargs = {**kwargs, "limit": limit}
        if cursor is not None:
            request_kwargs["cursor"] = cursor

        # Call SDK method
        response = await fetch_fn(**request_kwargs)

        # Extract items
        items = getattr(response, items_field, None) or []
        yield items

        # Get next cursor
        cursor = getattr(response, cursor_field, None)
        if not cursor:
            break


async def paginate_all(
    fetch_fn: Callable[..., Any],
    items_field: str,
    rate_limiter: "RateLimiter | None" = None,
    cursor_field: str = "cursor",
    limit: int = 100,
    **kwargs: Any,
) -> list[Any]:
    """Fetch all pages and return flat list.

    Optional rate_limiter: if provided, waits between each page fetch.

    WARNING: Can be slow and memory-intensive for large datasets.
    Prefer paginate() generator for large result sets.

    Args:
        fetch_fn: Async SDK method to call (e.g., apis.client.get_markets)
        items_field: Attribute name on response containing the list (e.g., "markets")
        rate_limiter: Optional RateLimiter instance to control request timing
        cursor_field: Attribute name for pagination cursor (default: "cursor")
        limit: Items per page (default: 100, max: 100)
        **kwargs: Additional parameters to pass to fetch_fn

    Returns:
        Flat list of all items from all pages.

    Example:
        all_markets = await paginate_all(
            apis.client.get_markets,
            "markets",
            rate_limiter=rate_limiter,
            status="open"
        )
        print(f"Total markets: {len(all_markets)}")
    """
    all_items: list[Any] = []

    async for page in paginate(fetch_fn, items_field, cursor_field, limit, **kwargs):
        if rate_limiter and all_items:  # Don't wait before first page
            await rate_limiter.wait()
        all_items.extend(page)

    return all_items
