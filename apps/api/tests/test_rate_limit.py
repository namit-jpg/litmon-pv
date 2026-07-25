from app.core.rate_limit import SlidingWindowLimiter


def test_limiter_blocks_after_max():
    lim = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    assert lim.allow("a")
    assert lim.allow("a")
    assert lim.allow("a")
    assert not lim.allow("a")
    assert lim.allow("b")
