
from datetime import datetime, timedelta, timezone

import pytest

from nexus.market_data.order_book_builder import OrderBookBuilder
from nexus.market_data.freshness import is_order_book_fresh


@pytest.fixture
def synchronized_book():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100", "2"]],
        asks=[["101", "3"]],
    )
    book.is_synchronized = True

    # Simulate a successfully applied depth update.
    book.last_event_time = datetime(
        2026, 10, 24, 10, 0, tzinfo=timezone.utc
    )
    book.last_received_at = datetime(
        2026, 10, 24, 10, 0, tzinfo=timezone.utc
    )
    return book


def test_accepts_fresh_order_book(synchronized_book):
    now = datetime(2026, 10, 24, 10, 0, 2, tzinfo=timezone.utc)

    assert is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_stale_order_book(synchronized_book):
    now = datetime(2026, 10, 24, 10, 0, 10, tzinfo=timezone.utc)

    assert not is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_invalid_order_book(synchronized_book):
    synchronized_book.is_valid = False
    now = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    assert not is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_unsynchronized_order_book(synchronized_book):
    synchronized_book.is_synchronized = False
    now = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    assert not is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_missing_receipt_timestamp(synchronized_book):
    synchronized_book.last_received_at = None
    now = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    assert not is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_future_receipt_timestamp(synchronized_book):
    now = datetime(2026, 10, 24, 9, 59, 59, tzinfo=timezone.utc)

    assert not is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )


def test_rejects_naive_current_time(synchronized_book):
    now = datetime(2026, 10, 24, 10, 0, 1)

    with pytest.raises(ValueError, match="timezone-aware"):
        is_order_book_fresh(
            synchronized_book,
            now=now,
            max_age_seconds=5,
        )


def test_rejects_non_positive_max_age(synchronized_book):
    now = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="positive"):
        is_order_book_fresh(
            synchronized_book,
            now=now,
            max_age_seconds=0,
        )


def test_accepts_receipt_timestamp_at_age_boundary(synchronized_book):
    now = datetime(2026, 10, 24, 10, 0, 5, tzinfo=timezone.utc)

    assert is_order_book_fresh(
        synchronized_book,
        now=now,
        max_age_seconds=5,
    )
