from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from fastapi import HTTPException


def test_google_drive_rate_limit_prunes_expired_hits(monkeypatch):
    from app.modules.google_drive import router

    times = iter((100.0, 100.0, 161.0))
    monkeypatch.setattr(router, "_rate_limit_requests", defaultdict(deque))
    monkeypatch.setattr(router, "_rate_limit_lock", Lock())
    monkeypatch.setattr(router, "_last_rate_limit_cleanup", 0.0)
    monkeypatch.setattr(router, "monotonic", lambda: next(times))

    router._consume_rate_limit("api:user", 1, "limited", "Too many requests.")
    with pytest.raises(HTTPException) as error:
        router._consume_rate_limit("api:user", 1, "limited", "Too many requests.")
    assert error.value.status_code == 429

    router._consume_rate_limit("api:user", 1, "limited", "Too many requests.")

    assert list(router._rate_limit_requests["api:user"]) == [161.0]


def test_google_drive_rate_limit_is_atomic_under_parallel_requests(monkeypatch):
    from app.modules.google_drive import router

    monkeypatch.setattr(router, "_rate_limit_requests", defaultdict(deque))
    monkeypatch.setattr(router, "_rate_limit_lock", Lock())
    monkeypatch.setattr(router, "_last_rate_limit_cleanup", 100.0)
    monkeypatch.setattr(router, "monotonic", lambda: 100.0)

    def consume_limit():
        try:
            router._consume_rate_limit(
                "api:user",
                5,
                "limited",
                "Too many requests.",
            )
        except HTTPException as error:
            return error.status_code
        return "accepted"

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: consume_limit(), range(20)))

    assert results.count("accepted") == 5
    assert results.count(429) == 15
