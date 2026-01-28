"""Tests for orderbook state management."""

import pytest
from dashboard.backend.orderbook import OrderbookState


class TestApplySnapshot:
    """Tests for apply_snapshot method."""

    def test_basic_snapshot(self):
        """Snapshot populates yes and no books."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[40, 10], [45, 20]],
            no_levels=[[55, 15], [60, 25]],
        )

        assert ob.snapshot_received is True
        assert ob.yes[40] == 10
        assert ob.yes[45] == 20
        assert ob.no[55] == 15
        assert ob.no[60] == 25
        assert ob.last_update > 0

    def test_empty_snapshot(self):
        """Empty snapshot clears books and sets snapshot_received."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[])

        assert ob.snapshot_received is True
        assert len(ob.yes) == 0
        assert len(ob.no) == 0

    def test_zero_size_levels_filtered(self):
        """Levels with zero size are not added."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[40, 10], [45, 0], [50, 5]],
            no_levels=[[55, 0]],
        )

        assert 40 in ob.yes
        assert 45 not in ob.yes
        assert 50 in ob.yes
        assert 55 not in ob.no

    def test_snapshot_replaces_existing(self):
        """Second snapshot replaces all existing data."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[[60, 20]])
        ob.apply_snapshot(yes_levels=[[50, 5]], no_levels=[[70, 15]])

        assert 40 not in ob.yes
        assert ob.yes[50] == 5
        assert 60 not in ob.no
        assert ob.no[70] == 15


class TestApplyDelta:
    """Tests for apply_delta method."""

    def test_delta_ignored_before_snapshot(self):
        """Deltas before snapshot are ignored."""
        ob = OrderbookState()
        ob.apply_delta("yes", 40, 10)

        assert ob.snapshot_received is False
        assert 40 not in ob.yes

    def test_add_new_level(self):
        """Delta adds new price level."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[])
        ob.apply_delta("yes", 40, 10)

        assert ob.yes[40] == 10

    def test_increase_existing_level(self):
        """Delta increases existing level size."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[])
        ob.apply_delta("yes", 40, 5)

        assert ob.yes[40] == 15

    def test_decrease_existing_level(self):
        """Delta decreases existing level size."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[])
        ob.apply_delta("yes", 40, -3)

        assert ob.yes[40] == 7

    def test_remove_level_at_zero(self):
        """Level removed when delta brings size to zero."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[])
        ob.apply_delta("yes", 40, -10)

        assert 40 not in ob.yes

    def test_remove_level_below_zero(self):
        """Level removed when delta brings size below zero."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[])
        ob.apply_delta("yes", 40, -15)

        assert 40 not in ob.yes

    def test_delta_no_side(self):
        """Delta applies to NO side."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[[60, 20]])
        ob.apply_delta("no", 60, 5)

        assert ob.no[60] == 25

    def test_delta_updates_timestamp(self):
        """Delta updates last_update timestamp."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[])
        initial_ts = ob.last_update

        import time
        time.sleep(0.01)
        ob.apply_delta("yes", 40, 10)

        assert ob.last_update > initial_ts


class TestGetTopLevels:
    """Tests for get_top_levels method."""

    def test_returns_sorted_descending(self):
        """Top levels sorted by price descending (best bid first)."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[40, 10], [45, 20], [50, 5]],
            no_levels=[[55, 15], [60, 25]],
        )

        result = ob.get_top_levels(n=10)

        assert result["yes"][0] == [50, 5]  # Highest price first
        assert result["yes"][1] == [45, 20]
        assert result["yes"][2] == [40, 10]
        assert result["no"][0] == [60, 25]
        assert result["no"][1] == [55, 15]

    def test_limit_respected(self):
        """Only N levels returned."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[40, 1], [41, 2], [42, 3], [43, 4], [44, 5]],
            no_levels=[],
        )

        result = ob.get_top_levels(n=2)

        assert len(result["yes"]) == 2
        assert result["yes"][0] == [44, 5]
        assert result["yes"][1] == [43, 4]

    def test_empty_book(self):
        """Empty book returns empty lists."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[])

        result = ob.get_top_levels()

        assert result["yes"] == []
        assert result["no"] == []

    def test_includes_market_ticker(self):
        """Result includes market_ticker."""
        ob = OrderbookState()
        ob.market_ticker = "TEST-MARKET"
        ob.apply_snapshot(yes_levels=[], no_levels=[])

        result = ob.get_top_levels()

        assert result["market_ticker"] == "TEST-MARKET"


class TestGetDepthData:
    """Tests for get_depth_data method."""

    def test_yes_no_symmetry(self):
        """YES asks derived from NO bids at (100 - price)."""
        ob = OrderbookState()
        # NO bid at 40 means someone will buy NO at 40
        # That's equivalent to YES ask at 60 (100 - 40)
        ob.apply_snapshot(
            yes_levels=[[45, 10]],  # YES bid at 45
            no_levels=[[40, 20]],   # NO bid at 40 = YES ask at 60
        )

        depth = ob.get_depth_data()

        # YES side
        assert depth["yes"]["bid_prices"] == [45]
        assert depth["yes"]["ask_prices"] == [60]  # 100 - 40
        assert depth["yes"]["ask_sizes"] == [20]
        assert depth["yes"]["best_bid"] == 45
        assert depth["yes"]["best_ask"] == 60

        # NO side (inverse)
        assert depth["no"]["bid_prices"] == [40]
        assert depth["no"]["ask_prices"] == [55]  # 100 - 45
        assert depth["no"]["ask_sizes"] == [10]
        assert depth["no"]["best_bid"] == 40
        assert depth["no"]["best_ask"] == 55

    def test_cumulative_bids(self):
        """Cumulative bids computed from high to low price."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[40, 10], [45, 20], [50, 5]],
            no_levels=[],
        )

        depth = ob.get_depth_data()

        # Prices sorted ascending: [40, 45, 50]
        # Sizes: [10, 20, 5]
        # Cumulative from high: 5, then 5+20=25, then 25+10=35
        assert depth["yes"]["bid_prices"] == [40, 45, 50]
        assert depth["yes"]["bid_sizes"] == [10, 20, 5]
        assert depth["yes"]["bid_cumulative"] == [35, 25, 5]

    def test_cumulative_asks(self):
        """Cumulative asks computed from low to high price."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[],
            no_levels=[[30, 5], [40, 10], [50, 15]],
        )

        depth = ob.get_depth_data()

        # NO bids at [30, 40, 50] = YES asks at [50, 60, 70]
        # After sorting: [50, 60, 70]
        # Sizes: [15, 10, 5]
        # Cumulative from low: 15, 15+10=25, 25+5=30
        assert depth["yes"]["ask_prices"] == [50, 60, 70]
        assert depth["yes"]["ask_cumulative"] == [15, 25, 30]

    def test_mid_price_calculation(self):
        """Mid price is average of best bid and best ask."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[45, 10]],
            no_levels=[[40, 20]],  # YES ask at 60
        )

        depth = ob.get_depth_data()

        # YES: best_bid=45, best_ask=60, mid=52.5
        assert depth["yes"]["mid"] == 52.5
        # NO: best_bid=40, best_ask=55, mid=47.5
        assert depth["no"]["mid"] == 47.5

    def test_mid_none_when_no_bid(self):
        """Mid is None when no bids."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[],
            no_levels=[[40, 20]],
        )

        depth = ob.get_depth_data()

        assert depth["yes"]["best_bid"] is None
        assert depth["yes"]["mid"] is None

    def test_mid_none_when_no_ask(self):
        """Mid is None when no asks."""
        ob = OrderbookState()
        ob.apply_snapshot(
            yes_levels=[[45, 10]],
            no_levels=[],
        )

        depth = ob.get_depth_data()

        assert depth["yes"]["best_ask"] is None
        assert depth["yes"]["mid"] is None

    def test_empty_book(self):
        """Empty book has empty arrays and None values."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[], no_levels=[])

        depth = ob.get_depth_data()

        assert depth["yes"]["bid_prices"] == []
        assert depth["yes"]["ask_prices"] == []
        assert depth["yes"]["best_bid"] is None
        assert depth["yes"]["best_ask"] is None
        assert depth["yes"]["mid"] is None


class TestReset:
    """Tests for reset method."""

    def test_clears_all_state(self):
        """Reset clears all orderbook state."""
        ob = OrderbookState()
        ob.market_ticker = "TEST-MARKET"
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[[60, 20]])

        ob.reset()

        assert ob.market_ticker == ""
        assert len(ob.yes) == 0
        assert len(ob.no) == 0
        assert ob.last_update == 0.0
        assert ob.snapshot_received is False

    def test_reset_then_delta_ignored(self):
        """After reset, deltas are ignored until new snapshot."""
        ob = OrderbookState()
        ob.apply_snapshot(yes_levels=[[40, 10]], no_levels=[])
        ob.reset()

        ob.apply_delta("yes", 40, 5)

        assert 40 not in ob.yes
