# Quick Start

## 1. Install

```bash
git clone <repository-url>
cd prediction-mm
pip install -e .
```

## 2. Configure

```bash
cp .env.example .env
```

Get API credentials from Kalshi account settings. Edit `.env`:

```
KALSHI_API_KEY_ID=<your-key-id>
KALSHI_PRIVATE_KEY_PATH=./kalshi_private_key.pem
KALSHI_ENV=demo
```

## 3. Test Connection

```bash
python scripts/check_connection.py
```

Should show exchange status, balance, and markets.

## 4. Try Demo Trade

Demo environment only:

```bash
python scripts/demo_trade.py
```

Places order at 1¢, then cancels it.

## 5. Fetch Market Data

```bash
python scripts/fetch_entity.py KXQUICKSETTLE-26JAN08H0850-3
```

Classification by hyphen count:
- 0 hyphens = series
- 1 hyphen = event
- 2 hyphens = market

## 6. Other Demos

```bash
python scripts/demo_websocket.py     # Live orderbook (30s)
python scripts/demo_auth.py          # Auth details
python scripts/test_pagination.py    # Pagination test
```

## Write Your Own

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

        tight_spreads = [m for m in markets if m.yes_bid and m.yes_ask and (m.yes_ask - m.yes_bid) <= 5]

        for m in tight_spreads[:10]:
            print(f"{m.ticker}: {m.yes_bid}¢/{m.yes_ask}¢")
    finally:
        await apis.client.close()

asyncio.run(main())
```

## WebSocket Example

```python
import asyncio
from prediction_mm.config import load_config
from prediction_mm.auth import create_auth
from prediction_mm.data import KalshiFeed

async def handle_orderbook(data):
    ticker = data['market_ticker']
    yes_bids = data['yes_bids']
    if yes_bids:
        best = yes_bids[0]
        print(f"{ticker}: {best[0]}¢ x {best[1]}")

async def main():
    config = load_config()
    auth = create_auth(config.api_key_id, config.private_key_path)
    feed = KalshiFeed(config, auth)

    feed.on_orderbook(handle_orderbook)
    await feed.connect()
    await feed.subscribe_orderbook("YOUR-TICKER")
    await feed.run()

asyncio.run(main())
```

## Troubleshooting

**Missing environment variable**
- Check `.env` file exists
- Check variable names match exactly

**Private key not found**
- Check path in `KALSHI_PRIVATE_KEY_PATH`
- Verify `.pem` file exists

**Connection failed**
- Verify `KALSHI_ENV` setting
- Check internet connection

**"This script only runs against demo environment"**
- Set `KALSHI_ENV=demo` in `.env`

See [README.md](README.md) for details.
