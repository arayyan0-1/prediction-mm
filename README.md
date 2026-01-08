# prediction-mm

Async Python client for Kalshi prediction markets.

## Install

```bash
pip install -e .
```

Development tools:
```bash
pip install -e ".[dev]"
```

## Setup

Copy `.env.example` to `.env` and fill in your Kalshi API credentials:

```
KALSHI_API_KEY_ID=your-key-id
KALSHI_PRIVATE_KEY_PATH=./kalshi_private_key.pem
KALSHI_ENV=demo
```

Get credentials from your Kalshi account settings.

## Basic Usage

```python
import asyncio
from prediction_mm.config import load_config
from prediction_mm.client import create_apis, RateLimiter
from prediction_mm.pagination import paginate_all

async def main():
    config = load_config()
    apis = await create_apis(config.host, config.api_key_id, str(config.private_key_path))
    rate_limiter = RateLimiter()

    try:
        markets = await paginate_all(
            apis.client.get_markets,
            "markets",
            rate_limiter=rate_limiter,
            status="open"
        )
        for m in markets:
            print(f"{m.ticker}: {m.yes_bid}¢/{m.yes_ask}¢")
    finally:
        await apis.client.close()

asyncio.run(main())
```

## Pagination

Generator (memory efficient):
```python
async for page in paginate(apis.client.get_markets, "markets", status="open"):
    await rate_limiter.wait()
    for market in page:
        print(market.ticker)
```

Fetch all (convenient):
```python
markets = await paginate_all(
    apis.client.get_markets,
    "markets",
    rate_limiter=rate_limiter,
    status="open"
)
```

## WebSocket

```python
from prediction_mm.data import KalshiFeed
from prediction_mm.auth import create_auth

config = load_config()
auth = create_auth(config.api_key_id, config.private_key_path)
feed = KalshiFeed(config, auth)

async def handle_orderbook(data):
    print(f"{data['market_ticker']}: {len(data['yes_bids'])} yes bids")

feed.on_orderbook(handle_orderbook)
await feed.connect()
await feed.subscribe_orderbook("MARKET-TICKER")
await feed.run()
```

## Scripts

Run these to test functionality:

```bash
python scripts/check_connection.py          # Verify API access
python scripts/demo_trade.py                # Place/cancel order (demo only)
python scripts/fetch_entity.py <ticker>     # Get series/event/market data
python scripts/demo_websocket.py            # Live orderbook feed
python scripts/demo_auth.py                 # Auth internals
python scripts/test_pagination.py           # Pagination test
```

Entity fetching examples:
```bash
python scripts/fetch_entity.py KXQUICKSETTLE                    # Series (0 hyphens)
python scripts/fetch_entity.py KXQUICKSETTLE-26JAN08H0850       # Event (1 hyphen)
python scripts/fetch_entity.py KXQUICKSETTLE-26JAN08H0850-3     # Market (2 hyphens)
```

## Testing

```bash
pytest                                      # Run tests
pytest --cov=src/prediction_mm             # With coverage
```

## Rate Limiting

```python
rate_limiter = RateLimiter(requests_per_second=20.0)
await rate_limiter.wait()  # Call before each request
```

## SDK Patches

This library patches `kalshi_python_async` to fix:

1. Missing status values - SDK defines 5, API returns 8 (initialized, inactive, active, closed, determined, disputed, amended, finalized)
2. Required vs optional fields - Some SDK fields marked required are actually optional
3. Orderbook types - API returns integers/None, SDK expects strings/lists

Patches apply automatically on import.

## Project Structure

```
src/prediction_mm/
  __init__.py       - Package exports
  auth.py           - RSA-PSS authentication
  client.py         - API client wrapper
  config.py         - Configuration management
  models.py         - SDK model patches
  pagination.py     - Pagination utilities
  data/feed.py      - WebSocket feed handler

scripts/            - Demo scripts
tests/              - Unit tests
```

## Requirements

- Python 3.11+
- Kalshi API credentials

Dependencies: kalshi-python-async, websockets, cryptography, python-dotenv, structlog
