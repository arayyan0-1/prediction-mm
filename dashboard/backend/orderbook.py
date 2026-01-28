"""Orderbook state management with delta application logic.

Maintains the canonical in-memory orderbook state and applies
incremental deltas from the Kalshi WebSocket feed.
"""

import time
from dataclasses import dataclass, field
from sortedcontainers import SortedDict
from threading import Lock


@dataclass
class OrderbookState:
    """Thread-safe orderbook state with delta application.

    Attributes:
        market_ticker: The market this orderbook is for.
        yes: SortedDict mapping price -> size for YES side.
        no: SortedDict mapping price -> size for NO side.
        last_update: Timestamp of last update in seconds.
        snapshot_received: Whether initial snapshot has been applied.
    """

    market_ticker: str = ""
    yes: SortedDict = field(default_factory=SortedDict)
    no: SortedDict = field(default_factory=SortedDict)
    last_update: float = 0.0
    snapshot_received: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def apply_snapshot(self, yes_levels: list[list[int]], no_levels: list[list[int]]) -> None:
        """Apply a full orderbook snapshot.

        This replaces the entire orderbook state. All subsequent deltas
        must be applied after this snapshot.

        Args:
            yes_levels: List of [price, size] pairs for YES side.
            no_levels: List of [price, size] pairs for NO side.
        """
        with self._lock:
            self.yes = SortedDict()
            self.no = SortedDict()

            for price, size in yes_levels:
                if size > 0:
                    self.yes[price] = size

            for price, size in no_levels:
                if size > 0:
                    self.no[price] = size

            self.last_update = time.time()
            self.snapshot_received = True

    def apply_delta(self, side: str, price: int, delta: int) -> None:
        """Apply an orderbook delta.

        Hard invariants:
        - Size never negative
        - Delete price levels at zero
        - Ignore deltas before snapshot ready

        Args:
            side: "yes" or "no"
            price: Price level (1-99 cents)
            delta: Change in size (positive or negative)
        """
        if not self.snapshot_received:
            return

        with self._lock:
            book = self.yes if side == "yes" else self.no

            current_size = book.get(price, 0)
            new_size = current_size + delta

            if new_size <= 0:
                # Remove price level
                if price in book:
                    del book[price]
            else:
                book[price] = new_size

            self.last_update = time.time()

    def get_top_levels(self, n: int = 10) -> dict:
        """Get top N price levels for each side.

        Args:
            n: Number of levels to return per side.

        Returns:
            Dict with yes/no lists of [price, size] pairs.
            YES: sorted descending by price (best bid first)
            NO: sorted descending by price (best bid first)
        """
        with self._lock:
            # YES side: highest prices first (best bids)
            yes_levels = [
                [price, self.yes[price]]
                for price in reversed(self.yes.keys())
            ][:n]

            # NO side: highest prices first (best bids)
            no_levels = [
                [price, self.no[price]]
                for price in reversed(self.no.keys())
            ][:n]

            return {
                "market_ticker": self.market_ticker,
                "timestamp": self.last_update,
                "yes": yes_levels,
                "no": no_levels,
            }

    def get_depth_data(self) -> dict:
        """Get full orderbook depth for visualization.

        In Kalshi binary markets:
        - YES ask at price P = NO bid at price (100-P)
        - NO ask at price P = YES bid at price (100-P)

        Returns separate YES and NO orderbook views with bids and asks.
        """
        with self._lock:
            # === YES ORDERBOOK ===
            # YES bids: direct from yes book (sorted ascending for chart)
            yes_bid_prices = list(self.yes.keys())
            yes_bid_sizes = [self.yes[p] for p in yes_bid_prices]

            # YES asks: derived from NO bids (100 - NO_price)
            # NO bid at 40 = YES ask at 60
            yes_ask_prices = sorted([100 - p for p in self.no.keys()])
            yes_ask_sizes = [self.no[100 - p] for p in yes_ask_prices]

            # Cumulative for YES bids (from high price down)
            yes_bid_cumulative = []
            total = 0
            for size in reversed(yes_bid_sizes):
                total += size
                yes_bid_cumulative.insert(0, total)

            # Cumulative for YES asks (from low price up)
            yes_ask_cumulative = []
            total = 0
            for size in yes_ask_sizes:
                total += size
                yes_ask_cumulative.append(total)

            # YES mid price
            yes_best_bid = max(self.yes.keys()) if self.yes else None
            yes_best_ask = min(yes_ask_prices) if yes_ask_prices else None
            yes_mid = None
            if yes_best_bid is not None and yes_best_ask is not None:
                yes_mid = (yes_best_bid + yes_best_ask) / 2

            # === NO ORDERBOOK ===
            # NO bids: direct from no book
            no_bid_prices = list(self.no.keys())
            no_bid_sizes = [self.no[p] for p in no_bid_prices]

            # NO asks: derived from YES bids (100 - YES_price)
            no_ask_prices = sorted([100 - p for p in self.yes.keys()])
            no_ask_sizes = [self.yes[100 - p] for p in no_ask_prices]

            # Cumulative for NO bids (from high price down)
            no_bid_cumulative = []
            total = 0
            for size in reversed(no_bid_sizes):
                total += size
                no_bid_cumulative.insert(0, total)

            # Cumulative for NO asks (from low price up)
            no_ask_cumulative = []
            total = 0
            for size in no_ask_sizes:
                total += size
                no_ask_cumulative.append(total)

            # NO mid price
            no_best_bid = max(self.no.keys()) if self.no else None
            no_best_ask = min(no_ask_prices) if no_ask_prices else None
            no_mid = None
            if no_best_bid is not None and no_best_ask is not None:
                no_mid = (no_best_bid + no_best_ask) / 2

            return {
                "market_ticker": self.market_ticker,
                "timestamp": self.last_update,
                "yes": {
                    "bid_prices": yes_bid_prices,
                    "bid_sizes": yes_bid_sizes,
                    "bid_cumulative": yes_bid_cumulative,
                    "ask_prices": yes_ask_prices,
                    "ask_sizes": yes_ask_sizes,
                    "ask_cumulative": yes_ask_cumulative,
                    "best_bid": yes_best_bid,
                    "best_ask": yes_best_ask,
                    "mid": yes_mid,
                },
                "no": {
                    "bid_prices": no_bid_prices,
                    "bid_sizes": no_bid_sizes,
                    "bid_cumulative": no_bid_cumulative,
                    "ask_prices": no_ask_prices,
                    "ask_sizes": no_ask_sizes,
                    "ask_cumulative": no_ask_cumulative,
                    "best_bid": no_best_bid,
                    "best_ask": no_best_ask,
                    "mid": no_mid,
                },
            }

    def reset(self) -> None:
        """Clear all orderbook state."""
        with self._lock:
            self.market_ticker = ""
            self.yes = SortedDict()
            self.no = SortedDict()
            self.last_update = 0.0
            self.snapshot_received = False
