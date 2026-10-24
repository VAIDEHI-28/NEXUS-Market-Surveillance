
from decimal import Decimal
from datetime import datetime, timezone
from nexus.market_data.order_book_builder import OrderBookBuilder


def test_load_snapshot_and_find_best_prices():
    book = OrderBookBuilder()

    book.load_snapshot(
        last_update_id=100,
        bids=[["99.00", "2.0"], ["100.00", "1.5"]],
        asks=[["101.00", "3.0"], ["102.00", "4.0"]],
    )

    assert book.best_bid() == (Decimal("100.00"), Decimal("1.5"))
    assert book.best_ask() == (Decimal("101.00"), Decimal("3.0"))
    assert book.is_valid is True
    assert book.is_synchronized is False


def test_zero_quantity_removes_price_level():
    book = OrderBookBuilder()

    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.5"], ["99.00", "2.0"]],
        asks=[["101.00", "3.0"]],
    )

    book.apply_levels(book.bids, [["100.00", "0"]])

    assert Decimal("100.00") not in book.bids
    assert book.best_bid() == (Decimal("99.00"), Decimal("2.0"))


def test_update_changes_existing_quantity():
    book = OrderBookBuilder()

    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.5"]],
        asks=[["101.00", "3.0"]],
    )

    book.apply_levels(book.bids, [["100.00", "2.5"]])

    assert book.bids[Decimal("100.00")] == Decimal("2.5")


def test_applies_contiguous_depth_event():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )
    book.is_synchronized = True

    applied = book.apply_depth_event(
        first_update_id=101,
        final_update_id=102,
        bids=[["100.00", "2.0"]],
        asks=[],
    )

    assert applied is True
    assert book.last_update_id == 102
    assert book.is_valid is True
    assert book.is_synchronized is True
    assert book.bids[Decimal("100.00")] == Decimal("2.0")


def test_ignores_stale_depth_event():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )
    book.is_synchronized = True

    applied = book.apply_depth_event(
        first_update_id=98,
        final_update_id=100,
        bids=[["100.00", "5.0"]],
        asks=[],
    )

    assert applied is False
    assert book.bids[Decimal("100.00")] == Decimal("1.0")
    assert book.last_update_id == 100
    assert book.is_valid is True
    assert book.is_synchronized is True


def test_invalidates_book_on_sequence_gap():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )
    book.is_synchronized = True

    applied = book.apply_depth_event(
        first_update_id=102,
        final_update_id=103,
        bids=[["100.00", "2.0"]],
        asks=[],
    )

    assert applied is False
    assert book.is_valid is False
    assert book.is_synchronized is False
    assert book.last_update_id == 100


def test_rejects_depth_event_before_synchronization():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )

    applied = book.apply_depth_event(
        first_update_id=101,
        final_update_id=102,
        bids=[["100.00", "2.0"]],
        asks=[],
    )

    assert applied is False
    assert book.last_update_id == 100
    assert book.bids[Decimal("100.00")] == Decimal("1.0")
    assert book.is_valid is True
    assert book.is_synchronized is False

def test_tracks_timestamps_of_applied_depth_event():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )
    book.is_synchronized = True

    event_time = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    received_at = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    applied = book.apply_depth_event(
        first_update_id=101,
        final_update_id=102,
        bids=[["100.00", "2.0"]],
        asks=[],
        event_time=event_time,
        received_at=received_at,
    )

    assert applied is True
    assert book.last_event_time == event_time
    assert book.last_received_at == received_at


def test_stale_depth_event_does_not_refresh_timestamps():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["100.00", "1.0"]],
        asks=[["101.00", "1.0"]],
    )
    book.is_synchronized = True

    event_time = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    received_at = datetime(2026, 10, 24, 10, 0, 1, tzinfo=timezone.utc)

    # Apply one valid update first.
    assert book.apply_depth_event(
        first_update_id=101,
        final_update_id=101,
        bids=[["100.00", "2.0"]],
        asks=[],
        event_time=event_time,
        received_at=received_at,
    )

    # An old update must not replace the timestamps.
    applied = book.apply_depth_event(
        first_update_id=99,
        final_update_id=100,
        bids=[["100.00", "9.0"]],
        asks=[],
        event_time=datetime(2026, 10, 24, 9, 59, tzinfo=timezone.utc),
        received_at=datetime(2026, 10, 24, 10, 0, 2, tzinfo=timezone.utc),
    )

    assert applied is False
    assert book.last_event_time == event_time
    assert book.last_received_at == received_at
