# prediction-mm

Market making system for Kalshi prediction markets. Includes a core async Python library and a real-time orderbook dashboard.

## Install

```bash
pip install -e ".[dev,dashboard]"
```

## Setup

### Credentials

Place your Kalshi API credentials in the project root:

```
api-demo-key/           # Demo environment
  api-key-id.txt        # Your demo API key ID
  *.pem                 # Your demo RSA private key

api-prod-key/           # Production environment
  api-key-id.txt        # Your prod API key ID
  *.pem                 # Your prod RSA private key
```

Get credentials from your Kalshi account settings.

## Dashboard

Real-time orderbook visualization with depth charts, price history, and live updates via WebSocket.

### Running

Start the backend server and frontend in two terminals:

```bash
# Terminal 1: Backend (bridges Kalshi WS feed to local clients)
python -m dashboard.backend.main

# Terminal 2: Frontend (Dash app at http://localhost:8050)
python -m dashboard.frontend.app
```

Use `--prod` to connect to production:
```bash
python -m dashboard.backend.main --prod
```

### Features

- **Depth chart** -- Cumulative bid/ask depth with YES/NO toggle
- **Price time series** -- Rolling last-trade price with bid/ask bands
- **Top-of-book display** -- Best bid/ask with spread for both sides
- **Last trade price** -- Real-time YES and NO last price
- **Market switching** -- Subscribe to any market ticker
- **Environment switching** -- Switch between demo and prod at runtime

### Architecture

```
Browser (Dash)  <──WebSocket──>  Backend Server  <──WebSocket──>  Kalshi API
  :8050                            :8765                          (+ REST snapshots)
```

The backend connects to Kalshi's WebSocket feed for orderbook deltas and ticker updates, fetches REST snapshots on subscribe, and maintains an in-memory `OrderbookState`. It broadcasts state updates to browser clients over a local WebSocket.

The frontend renders with Plotly/Dash, using `dcc.Store` for state and a 1-second `dcc.Interval` for throttled chart rendering.

## Core Library

Async Python client for the Kalshi API, used by the dashboard and available for custom strategies.

### Basic Usage

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
            print(f"{m.ticker}: {m.yes_bid}/{m.yes_ask}")
    finally:
        await apis.client.close()

asyncio.run(main())
```

### WebSocket Feed

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

### Pagination

```python
# Generator (memory efficient)
async for page in paginate(apis.client.get_markets, "markets", status="open"):
    await rate_limiter.wait()
    for market in page:
        print(market.ticker)

# Fetch all
markets = await paginate_all(apis.client.get_markets, "markets", rate_limiter=rate_limiter, status="open")
```

### Rate Limiting

```python
rate_limiter = RateLimiter(requests_per_second=20.0)
await rate_limiter.wait()  # Call before each request
```

## Scripts

All scripts default to demo environment. Use `--prod` for production.

```bash
python scripts/check_connection.py          # Verify API access
python scripts/demo_trade.py                # Place/cancel order (demo only)
python scripts/fetch_entity.py <ticker>     # Get series/event/market data
python scripts/demo_websocket.py            # Live orderbook feed (demo only)
python scripts/demo_auth.py                 # Auth internals
python scripts/test_pagination.py           # Pagination test
```

## Testing

```bash
pytest                        # Run all tests
pytest --cov                  # With coverage (src + dashboard)
pytest tests/test_orderbook.py  # Run specific test file
```

## Project Structure

```
src/prediction_mm/        Core library
  auth.py                   RSA-PSS authentication
  client.py                 API client wrapper
  config.py                 Configuration and credential discovery
  models.py                 SDK model patches
  pagination.py             Pagination utilities
  data/feed.py              WebSocket feed handler

dashboard/                Real-time orderbook dashboard
  backend/
    main.py                 WebSocket bridge server
    orderbook.py            Orderbook state with delta application
    kalshi_rest.py          REST client for snapshots
  frontend/
    app.py                  Dash/Plotly visualization

scripts/                  Demo and utility scripts
tests/                    Unit tests
```

## SDK Patches

This library patches `kalshi_python_async` to fix:

1. **Missing status values** -- SDK defines 5, API returns 8
2. **Required vs optional fields** -- Some SDK fields marked required are actually optional
3. **Orderbook types** -- API returns integers/None, SDK expects strings/lists

Patches apply automatically on import.

## Requirements

- Python 3.11+
- Kalshi API credentials

Core: kalshi-python-async, websockets, cryptography, structlog

Dashboard: dash, dash-extensions, plotly, httpx, sortedcontainers
