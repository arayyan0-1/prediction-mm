"""Dash frontend for Kalshi orderbook visualization."""

import json
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback
from dash_extensions import WebSocket
import plotly.graph_objects as go

# Initialize Dash app
app = dash.Dash(
    __name__,
    title="Kalshi Orderbook Dashboard",
    update_title=None,
)

# Backend WebSocket URL
BACKEND_WS_URL = "ws://localhost:8765"

# App layout
app.layout = html.Div([

    # Header with env label and env switch controls
    html.Div(
        id="app-header",
        children=[
            html.Div([
                html.H1(
                    id="app-title",
                    children="Kalshi Orderbook Dashboard - DEMO",
                    style={"margin": "0"},
                ),
                html.P("Real-time orderbook visualization",
                       style={"margin": "5px 0", "opacity": "0.7"}),
            ]),
            html.Div([
                dcc.Dropdown(
                    id="env-dropdown",
                    options=[
                        {"label": "Demo", "value": "demo"},
                        {"label": "Production", "value": "prod"},
                    ],
                    value="demo",
                    clearable=False,
                    style={
                        "width": "150px",
                        "fontSize": "13px",
                        "color": "#333",
                    },
                ),
                html.Button(
                    "Switch",
                    id="env-switch-btn",
                    n_clicks=0,
                    style={
                        "padding": "6px 16px",
                        "marginLeft": "8px",
                        "backgroundColor": "white",
                        "color": "#333",
                        "border": "1px solid #ccc",
                        "borderRadius": "4px",
                        "cursor": "pointer",
                        "fontSize": "13px",
                        "fontWeight": "bold",
                    },
                ),
            ], style={"display": "flex", "alignItems": "center"}),
        ],
        style={
            "backgroundColor": "#1a1a2e",
            "color": "white",
            "padding": "15px 20px",
            "marginBottom": "20px",
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
        },
    ),

    # Page content wrapper (for prod border)
    html.Div(
        id="page-content-wrapper",
        children=[
            # Controls
            html.Div([
                html.Div([
                    html.Label("Market Ticker:", style={"fontWeight": "bold", "marginRight": "10px"}),
                    dcc.Input(
                        id="ticker-input",
                        type="text",
                        placeholder="e.g., KXBTC-25JAN24-55500",
                        value="",
                        style={
                            "width": "300px",
                            "padding": "10px",
                            "fontSize": "14px",
                            "marginRight": "10px",
                        },
                    ),
                    html.Button(
                        "Connect",
                        id="connect-btn",
                        n_clicks=0,
                        style={
                            "padding": "10px 20px",
                            "backgroundColor": "#4CAF50",
                            "color": "white",
                            "border": "none",
                            "cursor": "pointer",
                            "fontSize": "14px",
                            "marginRight": "10px",
                        },
                    ),
                    html.Button(
                        "Reset",
                        id="reset-btn",
                        n_clicks=0,
                        style={
                            "padding": "10px 20px",
                            "backgroundColor": "#f44336",
                            "color": "white",
                            "border": "none",
                            "cursor": "pointer",
                            "fontSize": "14px",
                        },
                    ),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "15px"}),

                # Status indicator
                html.Div([
                    html.Span("Status: ", style={"fontWeight": "bold"}),
                    html.Span(id="status-text", children="Disconnected"),
                    html.Span(" | ", style={"margin": "0 10px"}),
                    html.Span("Last Update: ", style={"fontWeight": "bold"}),
                    html.Span(id="last-update", children="--"),
                ], style={"fontSize": "14px", "opacity": "0.8"}),

            ], style={
                "backgroundColor": "#f5f5f5",
                "padding": "20px",
                "borderRadius": "8px",
                "marginBottom": "20px",
                "marginLeft": "20px",
                "marginRight": "20px",
            }),

            # Side toggle (YES / NO)
            html.Div([
                html.Label("View Side:", style={
                    "fontWeight": "bold",
                    "marginRight": "15px",
                    "fontSize": "14px",
                }),
                dcc.RadioItems(
                    id="side-toggle",
                    options=[
                        {"label": "YES", "value": "yes"},
                        {"label": "NO", "value": "no"},
                    ],
                    value="yes",
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "20px",
                        "fontWeight": "bold",
                        "fontSize": "14px",
                        "cursor": "pointer",
                    },
                ),
            ], style={
                "marginLeft": "20px",
                "marginRight": "20px",
                "marginBottom": "15px",
                "display": "flex",
                "alignItems": "center",
            }),

            # Orderbook section
            html.Div([
                html.Div([
                    html.H3(id="ob-title", children="YES Orderbook",
                            style={"marginTop": "0", "marginBottom": "5px", "color": "#1a1a2e"}),
                    html.Div(id="tob-display", style={"fontSize": "14px", "marginBottom": "10px"}),
                    dcc.Graph(
                        id="depth-chart",
                        config={"displayModeBar": False},
                        style={"height": "350px"},
                    ),
                ], style={
                    "backgroundColor": "white",
                    "padding": "20px",
                    "borderRadius": "8px",
                    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                }),
            ], style={
                "marginLeft": "20px",
                "marginRight": "20px",
                "marginBottom": "20px",
            }),

            # Price Time Series
            html.Div([
                html.H4(id="price-title", children="YES Price History",
                        style={"marginTop": "0", "marginBottom": "10px"}),
                dcc.Graph(
                    id="price-chart",
                    config={"displayModeBar": False},
                    style={"height": "250px"},
                ),
            ], style={
                "backgroundColor": "white",
                "padding": "15px 20px",
                "borderRadius": "8px",
                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                "marginLeft": "20px",
                "marginRight": "20px",
                "marginBottom": "20px",
            }),
        ],
        style={},
    ),

    # Hidden stores for state
    dcc.Store(id="depth-store", data={}),
    dcc.Store(id="price-history-store", data={"yes": [], "no": []}),
    dcc.Store(id="connection-status", data={"connected": False}),
    dcc.Store(id="env-store", data="demo"),

    # 1-second interval to throttle chart rendering
    dcc.Interval(id="chart-interval", interval=1000, n_intervals=0),

    # Confirmation dialog for switching to production
    dcc.ConfirmDialog(
        id="prod-confirm-dialog",
        message=(
            "WARNING: You are about to switch to PRODUCTION.\n\n"
            "This connects to the REAL Kalshi exchange with REAL money.\n\n"
            "Are you sure you want to proceed?"
        ),
    ),

    # WebSocket connection - auto-connects on page load
    WebSocket(id="ws", url=BACKEND_WS_URL),

], style={
    "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    "backgroundColor": "#e8e8e8",
    "minHeight": "100vh",
    "paddingBottom": "20px",
})


# ── Environment UI callbacks ──────────────────────────────────────


@callback(
    [
        Output("app-title", "children"),
        Output("app-header", "style"),
        Output("page-content-wrapper", "style"),
        Output("env-dropdown", "value"),
    ],
    Input("env-store", "data"),
)
def update_env_display(env):
    """Update all environment-dependent visual elements."""
    is_prod = env == "prod"

    title = (
        "Kalshi Orderbook Dashboard - PROD"
        if is_prod else
        "Kalshi Orderbook Dashboard - DEMO"
    )

    header_style = {
        "backgroundColor": "#3d1a1a" if is_prod else "#1a1a2e",
        "color": "white",
        "padding": "15px 20px",
        "marginBottom": "20px",
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
    }

    wrapper_style = {
        "borderLeft": "4px solid #d32f2f" if is_prod else "none",
        "borderRight": "4px solid #d32f2f" if is_prod else "none",
    }

    dropdown_val = env or "demo"

    return title, header_style, wrapper_style, dropdown_val


@callback(
    [
        Output("prod-confirm-dialog", "displayed"),
        Output("ws", "send", allow_duplicate=True),
    ],
    Input("env-switch-btn", "n_clicks"),
    State("env-dropdown", "value"),
    State("env-store", "data"),
    prevent_initial_call=True,
)
def handle_env_switch_click(n_clicks, selected_env, current_env):
    """Handle environment switch button click."""
    if not n_clicks or selected_env == current_env:
        return False, dash.no_update

    if selected_env == "prod":
        return True, dash.no_update
    else:
        msg = json.dumps({"type": "switch_env", "environment": selected_env})
        return False, msg


@callback(
    Output("ws", "send", allow_duplicate=True),
    Input("prod-confirm-dialog", "submit_n_clicks"),
    State("env-dropdown", "value"),
    prevent_initial_call=True,
)
def handle_prod_confirmation(submit_n_clicks, selected_env):
    """Send switch_env message after user confirms prod switch."""
    if not submit_n_clicks:
        return dash.no_update
    return json.dumps({"type": "switch_env", "environment": selected_env})


# ── Market controls ───────────────────────────────────────────────


@callback(
    Output("ws", "send"),
    Input("connect-btn", "n_clicks"),
    State("ticker-input", "value"),
    prevent_initial_call=True,
)
def send_subscribe(n_clicks, ticker):
    if not ticker:
        return dash.no_update
    return json.dumps({"type": "subscribe", "market_ticker": ticker.strip()})


@callback(
    Output("ws", "send", allow_duplicate=True),
    Input("reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def send_unsubscribe(n_clicks):
    return json.dumps({"type": "unsubscribe"})


@callback(
    Output("status-text", "children", allow_duplicate=True),
    Input("ws", "state"),
    prevent_initial_call=True,
)
def handle_ws_state(state):
    """Handle WebSocket connection state changes."""
    if state is None:
        return "Connecting..."
    if isinstance(state, dict):
        ready_state = state.get("readyState", -1)
        if ready_state == 0:
            return "WebSocket: Connecting..."
        elif ready_state == 1:
            return "WebSocket: Connected (waiting for subscription)"
        elif ready_state == 2:
            return "WebSocket: Closing..."
        elif ready_state == 3:
            return "WebSocket: Closed"
    return f"WebSocket state: {state}"


# ── WebSocket message handler ─────────────────────────────────────
# Stores are updated on every WS message (real-time state).
# Charts are rendered on 1s interval (throttled).


@callback(
    [
        Output("depth-store", "data"),
        Output("price-history-store", "data"),
        Output("connection-status", "data"),
        Output("status-text", "children"),
        Output("env-store", "data"),
    ],
    Input("ws", "message"),
    [
        State("depth-store", "data"),
        State("price-history-store", "data"),
        State("env-store", "data"),
    ],
    prevent_initial_call=True,
)
def handle_ws_message(message, current_depth, current_history, current_env):
    no_update_5 = (
        dash.no_update, dash.no_update, dash.no_update,
        dash.no_update, dash.no_update,
    )

    if not message:
        return no_update_5

    try:
        if isinstance(message, dict):
            raw_data = message.get("data", message)
        else:
            raw_data = message

        if isinstance(raw_data, str):
            msg = json.loads(raw_data)
        elif isinstance(raw_data, dict):
            msg = raw_data
        else:
            return no_update_5

        msg_type = msg.get("type")

        if msg_type == "state_update":
            # Combined message: depth + price history
            depth_data = {
                "market_ticker": msg.get("market_ticker"),
                "timestamp": msg.get("timestamp"),
                "yes": msg.get("yes", {}),
                "no": msg.get("no", {}),
                "last_yes_price": msg.get("last_yes_price"),
                "last_no_price": msg.get("last_no_price"),
            }
            price_history = msg.get("price_history", {"yes": [], "no": []})
            return (
                depth_data,
                price_history,
                dash.no_update,
                f"Connected to {msg.get('market_ticker', '')}",
                dash.no_update,
            )

        elif msg_type == "status":
            status_msg = msg.get("message", "")
            ticker = msg.get("market_ticker", "")
            connected = msg.get("connected", False)

            if connected and ticker:
                status_text = f"Connected to {ticker}"
            elif ticker:
                status_text = status_msg
            else:
                status_text = status_msg or "Disconnected"

            return (
                dash.no_update,
                dash.no_update,
                {"connected": connected, "ticker": ticker},
                status_text,
                dash.no_update,
            )

        elif msg_type == "environment_info":
            env = msg.get("environment", "demo")
            return (
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                env,
            )

        elif msg_type == "switch_env_result":
            success = msg.get("success", False)
            env = msg.get("environment", current_env)
            result_msg = msg.get("message", "")

            status_text = result_msg if result_msg else (
                f"Switched to {env}" if success else "Environment switch failed"
            )

            return (
                dash.no_update,
                dash.no_update,
                dash.no_update,
                status_text,
                env if success else dash.no_update,
            )

    except Exception as e:
        import traceback
        print(f"Error handling message: {e}")
        traceback.print_exc()

    return no_update_5


# ── Chart rendering (throttled to 1s interval) ────────────────────


def create_orderbook_chart(side_data: dict) -> go.Figure:
    """Create an orderbook depth chart for the full 0-100 range."""
    fig = go.Figure()

    bid_prices = side_data.get("bid_prices", [])
    bid_sizes = side_data.get("bid_sizes", [])
    bid_cumulative = side_data.get("bid_cumulative", [])
    ask_prices = side_data.get("ask_prices", [])
    ask_sizes = side_data.get("ask_sizes", [])
    ask_cumulative = side_data.get("ask_cumulative", [])
    mid = side_data.get("mid")

    if bid_prices and bid_cumulative:
        fig.add_trace(go.Bar(
            x=bid_prices,
            y=bid_cumulative,
            customdata=bid_sizes,
            name="Bids",
            marker_color="rgba(76, 175, 80, 0.8)",
            hovertemplate="Bid: %{x}¢<br>Size: %{customdata}<br>Cumulative: %{y}<extra></extra>",
        ))

    if ask_prices and ask_cumulative:
        fig.add_trace(go.Bar(
            x=ask_prices,
            y=ask_cumulative,
            customdata=ask_sizes,
            name="Asks",
            marker_color="rgba(244, 67, 54, 0.8)",
            hovertemplate="Ask: %{x}¢<br>Size: %{customdata}<br>Cumulative: %{y}<extra></extra>",
        ))

    if mid is not None:
        max_y = max(
            max(bid_cumulative) if bid_cumulative else 0,
            max(ask_cumulative) if ask_cumulative else 0,
            1,
        )
        fig.add_trace(go.Scatter(
            x=[mid, mid],
            y=[0, max_y],
            mode="lines",
            name=f"Mid: {mid:.1f}¢",
            line=dict(color="#FFC107", width=2, dash="dash"),
            hovertemplate=f"Mid: {mid:.1f}¢<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Price (cents)",
        yaxis_title="Cumulative Size",
        hovermode="x unified",
        barmode="overlay",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=10, b=40),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#e0e0e0", range=[0, 100], dtick=5, autorange=False),
        yaxis=dict(gridcolor="#e0e0e0"),
        bargap=0.05,
    )

    return fig


def create_empty_chart(message: str = "Enter a market ticker and click Connect") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        xaxis_title="Price (cents)",
        yaxis_title="Cumulative Size",
        margin=dict(l=50, r=20, t=10, b=40),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#e0e0e0", range=[0, 100], dtick=5, autorange=False),
        yaxis=dict(gridcolor="#e0e0e0"),
        annotations=[dict(
            text=message, xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray"),
        )],
    )
    return fig


def create_price_chart(history: list) -> go.Figure:
    """Create price time series chart."""
    fig = go.Figure()

    if not history:
        fig.update_layout(
            margin=dict(l=50, r=20, t=10, b=30),
            plot_bgcolor="white",
            xaxis=dict(gridcolor="#e0e0e0"),
            yaxis=dict(gridcolor="#e0e0e0"),
            annotations=[dict(
                text="Waiting for data...", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=12, color="gray"),
            )],
        )
        return fig

    timestamps = [datetime.fromtimestamp(h["timestamp"]) for h in history]
    bids = [h.get("best_bid") for h in history]
    asks = [h.get("best_ask") for h in history]
    mids = [h.get("mid") for h in history]
    last_prices = [h.get("last_price") for h in history]

    fig.add_trace(go.Scatter(
        x=timestamps, y=bids, name="Bid", mode="lines",
        line=dict(color="#4CAF50", width=1),
        hovertemplate="%{y}¢<extra>Bid</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=asks, name="Ask", mode="lines",
        line=dict(color="#f44336", width=1),
        hovertemplate="%{y}¢<extra>Ask</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=last_prices, name="Last", mode="lines",
        line=dict(color="#9C27B0", width=1.5),
        connectgaps=True,
        hovertemplate="%{y}¢<extra>Last</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=mids, name="Mid", mode="lines",
        line=dict(color="#FFC107", width=2),
        hovertemplate="%{y:.1f}¢<extra>Mid</extra>",
    ))

    fig.update_layout(
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=10, b=30),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#e0e0e0", tickformat="%H:%M:%S"),
        yaxis=dict(gridcolor="#e0e0e0", title="Price (¢)"),
    )

    return fig


def format_tob(side_data: dict, last_price: int | None = None) -> html.Div:
    best_bid = side_data.get("best_bid")
    best_ask = side_data.get("best_ask")
    mid = side_data.get("mid")

    bid_str = f"{best_bid}¢" if best_bid is not None else "--"
    ask_str = f"{best_ask}¢" if best_ask is not None else "--"
    last_str = f"{last_price}¢" if last_price is not None else "--"
    mid_str = f"{mid:.1f}¢" if mid is not None else "--"
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
    spread_str = f"{spread}¢" if spread is not None else "--"

    return html.Div([
        html.Span("Last: ", style={"fontWeight": "bold"}),
        html.Span(last_str, style={"color": "#9C27B0", "fontWeight": "bold", "marginRight": "15px"}),
        html.Span("Bid: ", style={"fontWeight": "bold"}),
        html.Span(bid_str, style={"color": "#4CAF50", "fontWeight": "bold", "marginRight": "15px"}),
        html.Span("Ask: ", style={"fontWeight": "bold"}),
        html.Span(ask_str, style={"color": "#f44336", "fontWeight": "bold", "marginRight": "15px"}),
        html.Span("Mid: ", style={"fontWeight": "bold"}),
        html.Span(mid_str, style={"color": "#FFC107", "fontWeight": "bold", "marginRight": "15px"}),
        html.Span("Spread: ", style={"fontWeight": "bold"}),
        html.Span(spread_str),
    ])


@callback(
    [
        Output("ob-title", "children"),
        Output("tob-display", "children"),
        Output("depth-chart", "figure"),
        Output("price-title", "children"),
        Output("price-chart", "figure"),
        Output("last-update", "children"),
    ],
    Input("chart-interval", "n_intervals"),
    [
        State("depth-store", "data"),
        State("price-history-store", "data"),
        State("side-toggle", "value"),
    ],
)
def render_charts(n_intervals, depth_data, history_data, side):
    """Render all charts on 1s interval, reading current store state."""
    side_upper = side.upper()

    ob_title = f"{side_upper} Orderbook"
    price_title = f"{side_upper} Price History"

    # Timestamp
    ts_str = "--"
    if depth_data:
        ts = depth_data.get("timestamp", 0)
        if ts:
            ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]

    # Orderbook chart
    if depth_data and side in depth_data:
        side_data = depth_data[side]
        last_price_key = "last_yes_price" if side == "yes" else "last_no_price"
        last_price = depth_data.get(last_price_key)
        tob = format_tob(side_data, last_price=last_price)
        ob_fig = create_orderbook_chart(side_data)
    else:
        tob = html.Div("--", style={"color": "gray"})
        ob_fig = create_empty_chart()

    # Price chart
    if history_data and side in history_data:
        price_fig = create_price_chart(history_data[side])
    else:
        price_fig = create_price_chart([])

    return ob_title, tob, ob_fig, price_title, price_fig, ts_str


if __name__ == "__main__":
    print("\nStarting Kalshi Orderbook Dashboard...")
    print("Make sure the backend server is running: python -m dashboard.backend.main")
    print("\nDashboard will be available at: http://localhost:8050\n")
    app.run(debug=True, host="0.0.0.0", port=8050)
