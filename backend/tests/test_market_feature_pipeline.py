
from datetime import datetime, timedelta, timezone

import pytest

from nexus.features.market_feature_pipeline import TradeWindowBuffer
from nexus.schemas.trade import TradeEvent
from nexus.features.market_feature_pipeline import (
    TradeWindowBuffer,
    build_completed_window_features,
)
from nexus.market_data.order_book_builder import OrderBookBuilder

@pytest.fixture
def base_time():
    return datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


def make_trade(event_time, trade_id=1):
    return TradeEvent(
        symbol="BTCUSDT",
        price=60000.0,
        quantity=0.1,
        trade_id=trade_id,
        event_time=event_time,
        buyer_is_maker=False,
    )


def test_groups_trades_into_five_second_windows(base_time):
    buffer = TradeWindowBuffer(window_seconds=5)

    assert buffer.add_trade(make_trade(base_time + timedelta(seconds=1)))
    assert buffer.add_trade(
        make_trade(base_time + timedelta(seconds=3), trade_id=2)
    )

    completed = buffer.advance_watermark(
        base_time + timedelta(seconds=5)
    )

    assert len(completed) == 1

    start, end, trades = completed[0]
    assert start == base_time
    assert end == base_time + timedelta(seconds=5)
    assert len(trades) == 2


def test_trade_at_window_boundary_belongs_to_next_window(base_time):
    buffer = TradeWindowBuffer(window_seconds=5)

    buffer.add_trade(make_trade(base_time + timedelta(seconds=5)))

    completed = buffer.advance_watermark(
        base_time + timedelta(seconds=5)
    )
    assert completed == []

    completed = buffer.advance_watermark(
        base_time + timedelta(seconds=10)
    )

    assert len(completed) == 1
    assert completed[0][0] == base_time + timedelta(seconds=5)
    assert len(completed[0][2]) == 1


def test_does_not_close_incomplete_window(base_time):
    buffer = TradeWindowBuffer(window_seconds=5)

    buffer.add_trade(make_trade(base_time + timedelta(seconds=2)))

    completed = buffer.advance_watermark(
        base_time + timedelta(seconds=4)
    )

    assert completed == []


def test_rejects_naive_trade_timestamp():
    buffer = TradeWindowBuffer()

    trade = make_trade(datetime(2026, 10, 24, 10, 0))

    with pytest.raises(ValueError, match="timezone-aware"):
        buffer.add_trade(trade)


def test_rejects_backwards_watermark(base_time):
    buffer = TradeWindowBuffer()

    buffer.advance_watermark(base_time + timedelta(seconds=10))

    with pytest.raises(ValueError, match="must not move backwards"):
        buffer.advance_watermark(base_time + timedelta(seconds=5))


def test_rejects_trade_older_than_allowed_lateness(base_time):
    buffer = TradeWindowBuffer(allowed_lateness_seconds=1)

    buffer.advance_watermark(base_time + timedelta(seconds=10))

    accepted = buffer.add_trade(
        make_trade(base_time + timedelta(seconds=8))
    )

    assert accepted is False


def test_rejects_trade_in_window_ending_at_watermark(base_time):
    buffer = TradeWindowBuffer(allowed_lateness_seconds=2)

    buffer.advance_watermark(base_time + timedelta(seconds=10))

    # The trade belongs to [5s, 10s), which is already closed.
    accepted = buffer.add_trade(
        make_trade(base_time + timedelta(seconds=9))
    )

    assert accepted is False
    assert buffer.late_trade_count == 1


def test_rejects_non_positive_window_width():
    with pytest.raises(ValueError, match="window_seconds"):
        TradeWindowBuffer(window_seconds=0)


def test_rejects_negative_allowed_lateness():
    with pytest.raises(ValueError, match="allowed_lateness_seconds"):
        TradeWindowBuffer(allowed_lateness_seconds=-1)

def test_rejects_trade_for_already_closed_window(base_time):
    buffer = TradeWindowBuffer(allowed_lateness_seconds=10)

    buffer.add_trade(make_trade(base_time + timedelta(seconds=1)))

    buffer.advance_watermark(base_time + timedelta(seconds=5))

    accepted = buffer.add_trade(
        make_trade(base_time + timedelta(seconds=2), trade_id=2)
    )

    assert accepted is False
    assert buffer.late_trade_count == 1


def test_accepts_trade_in_window_not_yet_closed(base_time):
    buffer = TradeWindowBuffer(allowed_lateness_seconds=3)

    buffer.advance_watermark(base_time + timedelta(seconds=6))

    # The trade belongs to [5s, 10s), which has not closed yet.
    accepted = buffer.add_trade(
        make_trade(base_time + timedelta(seconds=7))
    )

    assert accepted is True
    assert buffer.late_trade_count == 0


@pytest.mark.parametrize(
    "window_seconds",
    [0, -1, float("inf"), float("-inf"), float("nan")],
)
def test_rejects_invalid_window_width(window_seconds):
    with pytest.raises(ValueError, match="window_seconds"):
        TradeWindowBuffer(window_seconds=window_seconds)


@pytest.mark.parametrize(
    "allowed_lateness_seconds",
    [-1, float("inf"), float("-inf"), float("nan")],
)
def test_rejects_invalid_allowed_lateness(allowed_lateness_seconds):
    with pytest.raises(ValueError, match="allowed_lateness_seconds"):
        TradeWindowBuffer(
            allowed_lateness_seconds=allowed_lateness_seconds
        )
def test_build_completed_window_features(base_time):
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["60000", "2.0"], ["59999", "3.0"]],
        asks=[["60001", "1.5"], ["60002", "2.5"]],
    )
    book.is_synchronized = True
    book.last_received_at = base_time + timedelta(seconds=4)
    book.last_event_time = base_time + timedelta(seconds=4)

    trades = [
        make_trade(base_time + timedelta(seconds=1)),
        make_trade(
            base_time + timedelta(seconds=3),
            trade_id=2,
        ),
    ]

    window = (
        base_time,
        base_time + timedelta(seconds=5),
        trades,
    )

    record = build_completed_window_features(
        window=window,
        order_book=book,
        now=base_time + timedelta(seconds=5),
    )

    assert record.symbol == "BTCUSDT"
    assert record.timestamp == base_time + timedelta(seconds=5)
    assert record.trade_features.trade_count == 2
    assert record.order_book_features.last_update_id == 100


def test_rejects_empty_completed_window(base_time):
    book = OrderBookBuilder()

    window = (
        base_time,
        base_time + timedelta(seconds=5),
        [],
    )

    with pytest.raises(ValueError, match="empty trade window"):
        build_completed_window_features(
            window=window,
            order_book=book,
        )


def test_rejects_missing_order_book_timestamp(base_time):
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["60000", "2.0"]],
        asks=[["60001", "1.5"]],
    )
    book.is_synchronized = True

    window = (
        base_time,
        base_time + timedelta(seconds=5),
        [make_trade(base_time + timedelta(seconds=1))],
    )

    with pytest.raises(ValueError, match="no observation timestamp"):
        build_completed_window_features(
            window=window,
            order_book=book,
        )