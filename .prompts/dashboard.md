PRD: Live Kalshi Orderbook Streaming & Visualization Dashboard
1. Objective

Build a local, real-time dashboard that allows a user to:

Enter a Kalshi market ticker

Fetch the initial full market state (orderbook snapshot)

Subscribe to WebSocket orderbook deltas

Incrementally update the in-memory orderbook

Visualize the evolving orderbook in real time

This system is intended for trading intuition, microstructure research, and market-making diagnostics, not execution (for now).

2. Non-Goals (Explicit)

❌ No order placement or trading controls

❌ No historical replay (future phase)

❌ No persistence to DB (RAM only)

❌ No auth hardening / prod infra

❌ No latency optimization beyond “reasonable”

3. High-Level Architecture
┌──────────────────────────────────────────┐
│              Dash Frontend               │
│  - Market input                          │
│  - Orderbook depth plot                  │
│  - Top-of-book table                     │
│  - Live updates via WebSocket            │
└──────────────────▲───────────────────────┘
                   │
                   │ WebSocket (local)
                   │
┌──────────────────┴───────────────────────┐
│               Backend Server              │
│                                          │
│  REST: Fetch initial market snapshot     │
│  WS: Subscribe to Kalshi deltas           │
│  State: Maintain live orderbook           │
│  Pub: Push updates to frontend            │
└──────────────────▲───────────────────────┘
                   │
                   │ WebSocket (external)
                   │
┌──────────────────┴───────────────────────┐
│          :contentReference[oaicite:0]{index=0} API          │
│  - REST: Market state                    │
│  - WS: Orderbook deltas                  │
└──────────────────────────────────────────┘

4. System Components
4.1 Backend (Python)

Responsibilities

Fetch full orderbook snapshot

Open and maintain Kalshi WebSocket

Apply orderbook deltas correctly

Serve a local WebSocket to frontend

Suggested Stack

asyncio

websockets

httpx

pydantic

FastAPI (optional but clean)

4.2 Frontend (Dash + Plotly)

Responsibilities

Accept market ticker input

Display current orderbook state

Update visuals in real time

Stay responsive under frequent updates

Suggested Stack

dash

plotly.graph_objects

dash_extensions (WebSocket support)

5. Data Flow (Critical)
Stage 1: Market Selection

User enters:

MARKET_TICKER = "INFLATION-2026-JAN"


Frontend sends request → Backend initializes pipeline.

Stage 2: Initial Snapshot (Authoritative State)

Backend:

Calls Kalshi REST endpoint:

GET /markets/{ticker}/orderbook


Receives full book:

{
  "yes": [[price, size], ...],
  "no":  [[price, size], ...]
}


Builds canonical in-memory state:

orderbook = {
    "yes": SortedDict(price -> size),
    "no":  SortedDict(price -> size)
}


⚠️ Invariant
All deltas must apply after this snapshot. No exceptions.

Stage 3: WebSocket Subscription (Delta Stream)

Backend opens Kalshi WS:

{
  "type": "subscribe",
  "channels": ["orderbook_delta"],
  "market": MARKET_TICKER
}


Receives messages like:

{
  "side": "yes",
  "price": 73,
  "delta": -5
}

Stage 4: Delta Application Logic (Core)

Single source of truth: backend orderbook

def apply_delta(book, side, price, delta):
    book[side][price] += delta
    if book[side][price] <= 0:
        del book[side][price]


Hard invariants

Size never negative

Delete price levels at zero

Ignore deltas before snapshot ready

Apply strictly in arrival order

Stage 5: Frontend Publishing

Backend publishes derived state, not raw deltas:

Options (MVP-friendly):

Top N levels per side

Or aggregated depth buckets

Example payload:

{
  "timestamp": 1700000000,
  "yes": [[70, 120], [71, 90], ...],
  "no":  [[29, 100], [28, 80], ...]
}

6. Frontend Visualization
6.1 Components

Inputs

Market ticker text box

Connect / Reset button

Charts

Orderbook Depth (Primary)

X: price

Y: cumulative size

Separate curves for YES / NO

Top-of-Book Table

Side	Price	Size

Update Indicator

Last update timestamp

Delta rate (optional)

6.2 Update Strategy

Frontend listens to backend WS

Updates figure data only, not full layout

Throttle redraws if needed (e.g. 50–100ms)

7. State & Failure Handling
Backend

Reconnect WS on drop

On reconnect → refetch full snapshot

Log and ignore malformed deltas

Frontend

Clear state on market change

Display “Disconnected” banner on WS failure

8. File Structure (Suggested)
kalshi-dashboard/
│
├── backend/
│   ├── main.py          # server + orchestration
│   ├── kalshi_rest.py   # snapshot fetch
│   ├── kalshi_ws.py     # delta listener
│   ├── orderbook.py    # state + logic
│   └── schemas.py
│
├── frontend/
│   ├── app.py           # Dash app
│   └── components.py
│
├── shared/
│   └── config.py
│
└── README.md

9. MVP Acceptance Criteria

 Enter market ticker → dashboard loads

 Initial orderbook visible within 1–2s

 Live updates visibly move depth

 No crashes on WS disconnect

 Reset works cleanly

10. Natural Phase-2 Extensions (Not Now)

Historical replay

Latency measurement

Spread / imbalance metrics

Multi-market view

Execution simulator overlay