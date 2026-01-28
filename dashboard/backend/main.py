"""Dashboard backend server.

Orchestrates:
- Kalshi WebSocket connection for orderbook deltas and trades
- REST API for orderbook snapshots
- Local WebSocket server for frontend clients
- Environment switching (demo/prod) at runtime
"""

import argparse
import asyncio
import json
import time
from collections import deque

import structlog
import websockets
from websockets.server import WebSocketServerProtocol

from prediction_mm.auth import create_auth
from prediction_mm.config import (
    Environment,
    load_config,
    load_config_for_env,
)

from dashboard.backend.orderbook import OrderbookState
from dashboard.backend.kalshi_rest import KalshiRestClient

logger = structlog.get_logger()


class ServerState:
    """Mutable server state for environment switching."""

    def __init__(self, config, auth):
        self.config = config
        self.auth = auth


# Global state
server_state: ServerState | None = None
orderbook = OrderbookState()
frontend_clients: set[WebSocketServerProtocol] = set()
kalshi_ws = None
kalshi_ws_task = None
current_ticker: str | None = None

# Price history for time series
MAX_PRICE_HISTORY = 500
yes_price_history: deque = deque(maxlen=MAX_PRICE_HISTORY)
no_price_history: deque = deque(maxlen=MAX_PRICE_HISTORY)

# Last trade prices
last_yes_price: int | None = None
last_no_price: int | None = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Dashboard backend server")
    parser.add_argument(
        "--env",
        choices=["demo", "prod"],
        default=None,
        help="Environment to connect to (demo or prod). Overrides KALSHI_ENV.",
    )
    return parser.parse_args()


async def broadcast_to_clients(message: dict) -> None:
    """Broadcast a message to all connected frontend clients."""
    if not frontend_clients:
        logger.debug("broadcast: no clients connected")
        return

    msg_str = json.dumps(message)
    msg_type = message.get("type", "unknown")
    logger.info(f"broadcasting {msg_type} to {len(frontend_clients)} clients, size={len(msg_str)} bytes")
    disconnected = set()

    for client in frontend_clients:
        try:
            await client.send(msg_str)
            logger.debug(f"sent {msg_type} to client {id(client)}")
        except websockets.ConnectionClosed:
            disconnected.add(client)
        except Exception as e:
            logger.error("broadcast_error", error=str(e))
            disconnected.add(client)

    for client in disconnected:
        frontend_clients.discard(client)


async def broadcast_environment_info() -> None:
    """Broadcast current environment info to all clients."""
    await broadcast_to_clients({
        "type": "environment_info",
        "environment": server_state.config.environment.value,
    })


def record_price_history(depth: dict) -> None:
    """Record current prices in history for time series."""
    ts = time.time()

    yes_data = depth.get("yes", {})
    no_data = depth.get("no", {})

    if yes_data.get("best_bid") is not None or yes_data.get("best_ask") is not None:
        yes_price_history.append({
            "timestamp": ts,
            "best_bid": yes_data.get("best_bid"),
            "best_ask": yes_data.get("best_ask"),
            "mid": yes_data.get("mid"),
            "last_price": last_yes_price,
        })

    if no_data.get("best_bid") is not None or no_data.get("best_ask") is not None:
        no_price_history.append({
            "timestamp": ts,
            "best_bid": no_data.get("best_bid"),
            "best_ask": no_data.get("best_ask"),
            "mid": no_data.get("mid"),
            "last_price": last_no_price,
        })


async def send_orderbook_update() -> None:
    """Send current orderbook state to all clients as a single message.

    Combines depth data and price history into one message to avoid
    dash_extensions WebSocket dropping rapid-fire messages.
    """
    if not orderbook.snapshot_received:
        logger.debug("send_orderbook_update: snapshot not received yet")
        return

    depth = orderbook.get_depth_data()

    # Record price history
    record_price_history(depth)

    # Send everything in ONE message
    await broadcast_to_clients({
        "type": "state_update",
        "market_ticker": depth["market_ticker"],
        "timestamp": depth["timestamp"],
        "yes": depth["yes"],
        "no": depth["no"],
        "last_yes_price": last_yes_price,
        "last_no_price": last_no_price,
        "price_history": {
            "yes": list(yes_price_history),
            "no": list(no_price_history),
        },
    })


async def handle_kalshi_message(msg: dict) -> None:
    """Handle incoming Kalshi WebSocket message."""
    msg_type = msg.get("type")

    if msg_type == "orderbook_snapshot":
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")

        if ticker == current_ticker:
            yes_levels = data.get("yes", [])
            no_levels = data.get("no", [])
            orderbook.apply_snapshot(yes_levels, no_levels)
            orderbook.market_ticker = ticker

            logger.info(
                "snapshot_applied",
                ticker=ticker,
                yes_levels=len(yes_levels),
                no_levels=len(no_levels),
            )

            await send_orderbook_update()

    elif msg_type == "orderbook_delta":
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")

        if ticker == current_ticker and orderbook.snapshot_received:
            side = data.get("side")
            price = data.get("price")
            delta = data.get("delta")

            if side and price is not None and delta is not None:
                orderbook.apply_delta(side, price, delta)
                await send_orderbook_update()

    elif msg_type == "ticker":
        # Trade/ticker update - extract last trade price
        global last_yes_price, last_no_price
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")

        if ticker == current_ticker:
            price = data.get("price")
            # "price" is the YES-side last trade price; NO = 100 - YES
            if price is not None:
                last_yes_price = price
                last_no_price = 100 - price
                logger.info("last_price_updated", yes=last_yes_price, no=last_no_price)
                await send_orderbook_update()

    elif msg_type == "subscribed":
        channels = msg.get("msg", {}).get("channel", "unknown")
        logger.info("kalshi_subscribed", channel=channels, full_msg=msg)

    elif msg_type == "error":
        logger.error("kalshi_error", msg=msg)

    else:
        logger.warning("unrecognized_message_type", msg_type=msg_type, msg=msg)


async def run_kalshi_feed(ticker: str) -> None:
    """Run Kalshi WebSocket feed for orderbook updates and trades."""
    global kalshi_ws

    path = "/trade-api/ws/v2"
    headers = server_state.auth.get_auth_headers("GET", path)

    while True:
        try:
            logger.info("kalshi_connecting", url=server_state.config.ws_url)

            async with websockets.connect(
                server_state.config.ws_url,
                additional_headers=headers,
            ) as ws:
                kalshi_ws = ws
                logger.info("kalshi_connected")

                # Subscribe to orderbook_delta for the ticker
                subscribe_ob = {
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["orderbook_delta"],
                        "market_ticker": ticker,
                    },
                }
                await ws.send(json.dumps(subscribe_ob))
                logger.info("kalshi_subscribed_orderbook", ticker=ticker)

                # Subscribe to ticker channel for trades
                subscribe_ticker = {
                    "id": 2,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["ticker"],
                        "market_ticker": ticker,
                    },
                }
                await ws.send(json.dumps(subscribe_ticker))
                logger.info("kalshi_subscribed_ticker", ticker=ticker)

                # Process messages
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        await handle_kalshi_message(msg)
                    except json.JSONDecodeError:
                        logger.warning("invalid_json", raw=str(raw_msg)[:200])
                    except Exception as e:
                        logger.error("message_error", error=str(e))

        except websockets.ConnectionClosed as e:
            logger.warning("kalshi_disconnected", code=e.code, reason=e.reason)
            kalshi_ws = None

            await broadcast_to_clients({
                "type": "status",
                "connected": False,
                "market_ticker": ticker,
                "message": "Kalshi connection lost, reconnecting...",
            })

            await asyncio.sleep(2)
            headers = server_state.auth.get_auth_headers("GET", path)

        except Exception as e:
            logger.error("kalshi_error", error=str(e))
            kalshi_ws = None
            await asyncio.sleep(5)
            headers = server_state.auth.get_auth_headers("GET", path)


async def subscribe_to_market(ticker: str) -> None:
    """Subscribe to a market's orderbook updates."""
    global current_ticker, kalshi_ws_task, last_yes_price, last_no_price

    # Cancel existing feed if any
    if kalshi_ws_task and not kalshi_ws_task.done():
        kalshi_ws_task.cancel()
        try:
            await kalshi_ws_task
        except asyncio.CancelledError:
            pass

    # Reset state
    orderbook.reset()
    yes_price_history.clear()
    no_price_history.clear()
    last_yes_price = None
    last_no_price = None
    current_ticker = ticker
    orderbook.market_ticker = ticker

    # Notify clients
    await broadcast_to_clients({
        "type": "status",
        "connected": True,
        "market_ticker": ticker,
        "message": f"Subscribing to {ticker}...",
    })

    # Fetch initial snapshot via REST
    rest_client = KalshiRestClient(server_state.config, server_state.auth)
    try:
        snapshot = await rest_client.get_orderbook(ticker)
        orderbook.apply_snapshot(snapshot["yes"], snapshot["no"])
        logger.info(
            "rest_snapshot_applied",
            ticker=ticker,
            yes_levels=len(snapshot["yes"]),
            no_levels=len(snapshot["no"]),
        )
        await send_orderbook_update()
    except Exception as e:
        logger.error("snapshot_fetch_failed", error=str(e))
        await broadcast_to_clients({
            "type": "status",
            "connected": False,
            "market_ticker": ticker,
            "message": f"Failed to fetch orderbook: {e}",
        })
    finally:
        await rest_client.close()

    # Start Kalshi WebSocket feed
    kalshi_ws_task = asyncio.create_task(run_kalshi_feed(ticker))


async def switch_environment(env_str: str) -> dict:
    """Switch to a different Kalshi environment at runtime.

    Cancels existing feeds, loads new credentials, resets all state,
    and broadcasts the new environment info to all clients.

    Args:
        env_str: "demo" or "prod"

    Returns:
        Result dict with success status and environment info.
    """
    global kalshi_ws_task, kalshi_ws, current_ticker, last_yes_price, last_no_price

    target_env = Environment.DEMO if env_str == "demo" else Environment.PROD
    current_env = server_state.config.environment

    if target_env == current_env:
        logger.info("switch_environment_noop", env=env_str)
        return {
            "success": True,
            "environment": env_str,
            "message": f"Already on {env_str}",
        }

    logger.info("switching_environment", from_env=current_env.value, to_env=env_str)

    # Cancel existing Kalshi feed
    if kalshi_ws_task and not kalshi_ws_task.done():
        kalshi_ws_task.cancel()
        try:
            await kalshi_ws_task
        except asyncio.CancelledError:
            pass
    kalshi_ws = None
    kalshi_ws_task = None

    # Reset market state
    orderbook.reset()
    yes_price_history.clear()
    no_price_history.clear()
    last_yes_price = None
    last_no_price = None
    current_ticker = None

    # Load new credentials
    try:
        new_config = load_config_for_env(target_env)
        new_auth = create_auth(new_config.api_key_id, new_config.private_key_path)
        server_state.config = new_config
        server_state.auth = new_auth

        logger.info("environment_switched", environment=env_str)

        # Broadcast new environment to all clients
        await broadcast_environment_info()

        # Notify clients that market data was reset
        await broadcast_to_clients({
            "type": "status",
            "connected": False,
            "market_ticker": None,
            "message": f"Switched to {env_str}. Subscribe to a market to begin.",
        })

        return {
            "success": True,
            "environment": env_str,
            "message": f"Switched to {env_str}",
        }

    except Exception as e:
        logger.error("environment_switch_failed", error=str(e))
        return {
            "success": False,
            "environment": current_env.value,
            "message": f"Failed to switch: {e}",
        }


async def handle_frontend_client(websocket: WebSocketServerProtocol) -> None:
    """Handle a connected frontend client."""
    frontend_clients.add(websocket)
    client_id = id(websocket)
    logger.info("frontend_connected", client_id=client_id)

    # Send environment info immediately
    await websocket.send(json.dumps({
        "type": "environment_info",
        "environment": server_state.config.environment.value,
    }))

    # Send current state if available
    if orderbook.snapshot_received:
        await websocket.send(json.dumps({
            "type": "status",
            "connected": kalshi_ws is not None,
            "market_ticker": current_ticker,
            "message": "Connected",
        }))
        await send_orderbook_update()

    try:
        async for raw_msg in websocket:
            try:
                msg = json.loads(raw_msg)
                msg_type = msg.get("type")

                if msg_type == "subscribe":
                    ticker = msg.get("market_ticker")
                    if ticker:
                        logger.info("subscribe_request", ticker=ticker)
                        await subscribe_to_market(ticker)

                elif msg_type == "unsubscribe":
                    logger.info("unsubscribe_request")
                    orderbook.reset()
                    yes_price_history.clear()
                    no_price_history.clear()
                    if kalshi_ws_task and not kalshi_ws_task.done():
                        kalshi_ws_task.cancel()

                elif msg_type == "switch_env":
                    env_str = msg.get("environment")
                    if env_str in ("demo", "prod"):
                        logger.info("switch_env_request", target=env_str)
                        result = await switch_environment(env_str)
                        await websocket.send(json.dumps({
                            "type": "switch_env_result",
                            **result,
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "switch_env_result",
                            "success": False,
                            "message": f"Invalid environment: {env_str}",
                        }))

            except json.JSONDecodeError:
                logger.warning("frontend_invalid_json")

    except websockets.ConnectionClosed:
        pass
    finally:
        frontend_clients.discard(websocket)
        logger.info("frontend_disconnected", client_id=client_id)


async def main():
    """Start the dashboard backend server."""
    global server_state

    args = parse_args()

    config = load_config(env_override=args.env)
    auth = create_auth(config.api_key_id, config.private_key_path)
    server_state = ServerState(config, auth)

    logger.info(
        "starting_dashboard_backend",
        environment=config.environment.value,
    )

    host = "localhost"
    port = 8765

    async def client_handler(websocket: WebSocketServerProtocol):
        await handle_frontend_client(websocket)

    async with websockets.serve(client_handler, host, port):
        logger.info("dashboard_backend_ready", host=host, port=port)
        print(f"\nDashboard backend running at ws://{host}:{port}")
        print(f"Environment: {config.environment.value.upper()}")
        print("Waiting for frontend connection...")

        await asyncio.Future()


if __name__ == "__main__":
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )
    asyncio.run(main())
