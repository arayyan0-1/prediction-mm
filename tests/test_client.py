"""Tests for async client utilities."""

import time
import pytest
from prediction_mm.client import RateLimiter, generate_request_id


def test_generate_request_id_format():
    rid = generate_request_id()
    assert len(rid) == 12
    assert rid.isalnum()


def test_generate_request_id_unique():
    ids = [generate_request_id() for _ in range(100)]
    assert len(set(ids)) == 100


@pytest.mark.asyncio
async def test_rate_limiter_spacing():
    limiter = RateLimiter(requests_per_second=100.0)  # 10ms interval

    await limiter.wait()
    t1 = time.time()
    await limiter.wait()
    t2 = time.time()

    elapsed = t2 - t1
    assert elapsed >= 0.009  # ~10ms with some tolerance
