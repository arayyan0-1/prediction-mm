"""Tests for async pagination utilities."""

import pytest
from unittest.mock import AsyncMock, Mock

from prediction_mm.pagination import paginate, paginate_all
from prediction_mm.client import RateLimiter


@pytest.mark.asyncio
async def test_single_page():
    """Single page response - cursor is None in first response."""
    mock_response = Mock()
    mock_response.markets = [Mock(ticker="A"), Mock(ticker="B")]
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    pages = []
    async for page in paginate(mock_fn, "markets"):
        pages.append(page)

    assert len(pages) == 1
    assert len(pages[0]) == 2
    assert pages[0][0].ticker == "A"
    assert pages[0][1].ticker == "B"
    mock_fn.assert_called_once_with(limit=100)


@pytest.mark.asyncio
async def test_multi_page():
    """Multi-page response - 3 pages with cursors."""
    # Page 1
    page1 = Mock()
    page1.markets = [Mock(ticker="A"), Mock(ticker="B")]
    page1.cursor = "cursor1"

    # Page 2
    page2 = Mock()
    page2.markets = [Mock(ticker="C"), Mock(ticker="D")]
    page2.cursor = "cursor2"

    # Page 3 (final)
    page3 = Mock()
    page3.markets = [Mock(ticker="E")]
    page3.cursor = None

    mock_fn = AsyncMock(side_effect=[page1, page2, page3])

    pages = []
    async for page in paginate(mock_fn, "markets"):
        pages.append(page)

    assert len(pages) == 3
    assert len(pages[0]) == 2
    assert len(pages[1]) == 2
    assert len(pages[2]) == 1
    assert pages[2][0].ticker == "E"

    # Verify calls
    assert mock_fn.call_count == 3
    calls = mock_fn.call_args_list
    assert calls[0][1] == {"limit": 100}
    assert calls[1][1] == {"limit": 100, "cursor": "cursor1"}
    assert calls[2][1] == {"limit": 100, "cursor": "cursor2"}


@pytest.mark.asyncio
async def test_empty_first_page():
    """Empty first page - no items, no cursor."""
    mock_response = Mock()
    mock_response.markets = []
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    pages = []
    async for page in paginate(mock_fn, "markets"):
        pages.append(page)

    assert len(pages) == 1
    assert len(pages[0]) == 0
    mock_fn.assert_called_once_with(limit=100)


@pytest.mark.asyncio
async def test_items_field_is_none():
    """Items field is None - SDK returns None instead of empty list."""
    mock_response = Mock()
    mock_response.markets = None
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    pages = []
    async for page in paginate(mock_fn, "markets"):
        pages.append(page)

    assert len(pages) == 1
    assert len(pages[0]) == 0  # Should yield empty list, not None


@pytest.mark.asyncio
async def test_limit_parameter():
    """Limit parameter passed correctly."""
    mock_response = Mock()
    mock_response.events = [Mock(event_ticker="E1")]
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    async for _ in paginate(mock_fn, "events", limit=50):
        pass

    mock_fn.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_additional_kwargs():
    """Additional kwargs passed through."""
    mock_response = Mock()
    mock_response.markets = [Mock(ticker="M1")]
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    async for _ in paginate(mock_fn, "markets", status="open", series_ticker="INX"):
        pass

    mock_fn.assert_called_once_with(limit=100, status="open", series_ticker="INX")


@pytest.mark.asyncio
async def test_custom_cursor_field():
    """Custom cursor field name."""
    mock_response = Mock()
    mock_response.items = [Mock(id="1")]
    mock_response.next_page = None

    mock_fn = AsyncMock(return_value=mock_response)

    pages = []
    async for page in paginate(mock_fn, "items", cursor_field="next_page"):
        pages.append(page)

    assert len(pages) == 1
    assert len(pages[0]) == 1


@pytest.mark.asyncio
async def test_paginate_all_single_page():
    """paginate_all returns flat list - single page."""
    mock_response = Mock()
    mock_response.markets = [Mock(ticker="A"), Mock(ticker="B"), Mock(ticker="C")]
    mock_response.cursor = None

    mock_fn = AsyncMock(return_value=mock_response)

    all_items = await paginate_all(mock_fn, "markets")

    assert len(all_items) == 3
    assert all_items[0].ticker == "A"
    assert all_items[1].ticker == "B"
    assert all_items[2].ticker == "C"


@pytest.mark.asyncio
async def test_paginate_all_multi_page():
    """paginate_all returns flat list - multiple pages."""
    # Page 1
    page1 = Mock()
    page1.fills = [Mock(fill_id="1"), Mock(fill_id="2")]
    page1.cursor = "cursor1"

    # Page 2 (final)
    page2 = Mock()
    page2.fills = [Mock(fill_id="3")]
    page2.cursor = None

    mock_fn = AsyncMock(side_effect=[page1, page2])

    all_items = await paginate_all(mock_fn, "fills")

    assert len(all_items) == 3
    assert all_items[0].fill_id == "1"
    assert all_items[1].fill_id == "2"
    assert all_items[2].fill_id == "3"


@pytest.mark.asyncio
async def test_paginate_all_with_rate_limiter():
    """paginate_all with rate_limiter - verify wait() called between pages."""
    # Page 1
    page1 = Mock()
    page1.markets = [Mock(ticker="A")]
    page1.cursor = "cursor1"

    # Page 2
    page2 = Mock()
    page2.markets = [Mock(ticker="B")]
    page2.cursor = "cursor2"

    # Page 3 (final)
    page3 = Mock()
    page3.markets = [Mock(ticker="C")]
    page3.cursor = None

    mock_fn = AsyncMock(side_effect=[page1, page2, page3])
    mock_rate_limiter = Mock(spec=RateLimiter)
    mock_rate_limiter.wait = AsyncMock()

    all_items = await paginate_all(mock_fn, "markets", rate_limiter=mock_rate_limiter)

    assert len(all_items) == 3
    # Should wait between pages, but not before first page
    assert mock_rate_limiter.wait.call_count == 2


@pytest.mark.asyncio
async def test_paginate_all_no_rate_limiter():
    """paginate_all without rate_limiter works."""
    # Page 1
    page1 = Mock()
    page1.markets = [Mock(ticker="A")]
    page1.cursor = "cursor1"

    # Page 2 (final)
    page2 = Mock()
    page2.markets = [Mock(ticker="B")]
    page2.cursor = None

    mock_fn = AsyncMock(side_effect=[page1, page2])

    all_items = await paginate_all(mock_fn, "markets")

    assert len(all_items) == 2


@pytest.mark.asyncio
async def test_empty_pages_in_middle():
    """Handle empty page in the middle of pagination."""
    # Page 1
    page1 = Mock()
    page1.markets = [Mock(ticker="A")]
    page1.cursor = "cursor1"

    # Page 2 (empty but has cursor)
    page2 = Mock()
    page2.markets = []
    page2.cursor = "cursor2"

    # Page 3 (final)
    page3 = Mock()
    page3.markets = [Mock(ticker="B")]
    page3.cursor = None

    mock_fn = AsyncMock(side_effect=[page1, page2, page3])

    pages = []
    async for page in paginate(mock_fn, "markets"):
        pages.append(page)

    assert len(pages) == 3
    assert len(pages[0]) == 1
    assert len(pages[1]) == 0
    assert len(pages[2]) == 1


@pytest.mark.asyncio
async def test_different_items_fields():
    """Test with different items field names."""
    # Test with 'events'
    mock_response = Mock()
    mock_response.events = [Mock(event_ticker="E1")]
    mock_response.cursor = None
    mock_fn = AsyncMock(return_value=mock_response)

    pages = []
    async for page in paginate(mock_fn, "events"):
        pages.append(page)
    assert len(pages[0]) == 1
    assert pages[0][0].event_ticker == "E1"

    # Test with 'fills'
    mock_response2 = Mock()
    mock_response2.fills = [Mock(fill_id="F1")]
    mock_response2.cursor = None
    mock_fn2 = AsyncMock(return_value=mock_response2)

    pages2 = []
    async for page in paginate(mock_fn2, "fills"):
        pages2.append(page)
    assert len(pages2[0]) == 1
    assert pages2[0][0].fill_id == "F1"

    # Test with 'orders'
    mock_response3 = Mock()
    mock_response3.orders = [Mock(order_id="O1")]
    mock_response3.cursor = None
    mock_fn3 = AsyncMock(return_value=mock_response3)

    pages3 = []
    async for page in paginate(mock_fn3, "orders"):
        pages3.append(page)
    assert len(pages3[0]) == 1
    assert pages3[0][0].order_id == "O1"
