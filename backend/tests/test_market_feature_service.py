
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus.features.market_feature_service import (
    build_market_feature_record,
)
from nexus.market_data.order_book_builder import OrderBookBuilder
from nexus.schemas.trade import TradeEvent


@pytest.fixture
def synchronized_order_book():
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[
            ["60000", "2.0"],
            ["59999", "3.0"],
        ],
        asks=[
            ["60001", "1.5"],
            ["60002", "2.5"],
        ],
    )
    book.is_synchronized = True

    # Fixed timestamps make freshness tests deterministic.
    book.last_event_time = datetime(
        2026, 10, 24, 10, 0, 4, tzinfo=timezone.utc
    )
    book.last_received_at = datetime(
        2026, 10, 24, 10, 0, 4, tzinfo=timezone.utc
    )

    return book


@pytest.fixture
def trade_window():
    start = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(seconds=5)

    trades = [
        TradeEvent(
            symbol="BTCUSDT",
            price=60000.0,
            quantity=0.5,
            trade_id=1,
            event_time=start + timedelta(seconds=1),
            buyer_is_maker=False,
        ),
        TradeEvent(
            symbol="BTCUSDT",
            price=60001.0,
            quantity=0.25,
            trade_id=2,
            event_time=start + timedelta(seconds=3),
            buyer_is_maker=True,
        ),
    ]

    return trades, start, end


def test_builds_market_feature_record(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window

    record = build_market_feature_record(
        trades=trades,
        window_start=start,
        window_end=end,
        order_book=synchronized_order_book,
        order_book_observed_at=end,
        now=end,
    )

    assert record.symbol == "BTCUSDT"
    assert record.timestamp == end
    assert record.trade_window_start == start
    assert record.trade_window_end == end
    assert record.order_book_observed_at == end
    assert record.trade_features.trade_count == 2
    assert record.order_book_features.last_update_id == 100
    assert record.order_book_features.mid_price == 60000.5


def test_rejects_unsynchronized_order_book(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.is_synchronized = False

    with pytest.raises(ValueError, match="valid and synchronized"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_invalid_order_book(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.is_valid = False

    with pytest.raises(ValueError, match="valid and synchronized"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_missing_update_id(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.last_update_id = None

    with pytest.raises(ValueError, match="no update ID"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_empty_order_book_side(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.bids.clear()

    with pytest.raises(ValueError, match="both bids and asks"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_mismatched_trade_symbol(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    trades[0] = trades[0].model_copy(
        update={"symbol": "ETHUSDT"}
    )

    with pytest.raises(ValueError, match="requested symbol"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_trade_symbol_different_from_requested_symbol(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window

    with pytest.raises(ValueError, match="requested symbol"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            symbol="ETHUSDT",
            now=end,
        )


def test_rejects_empty_requested_symbol(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window

    with pytest.raises(ValueError, match="must not be empty"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            symbol=" ",
            now=end,
        )


def test_rejects_crossed_order_book(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.asks[Decimal("59999")] = Decimal("1.0")

    with pytest.raises(ValueError, match="positive spread"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_non_positive_order_book_quantity(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window
    synchronized_order_book.bids[Decimal("60000")] = Decimal("0")

    with pytest.raises(ValueError, match="must be positive"):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=end,
        )


def test_rejects_stale_order_book(
    synchronized_order_book, trade_window
):
    trades, start, end = trade_window

    # The last receipt was at 10:00:04; evaluate at 10:00:10.
    evaluation_time = end + timedelta(seconds=5)

    with pytest.raises(
        ValueError,
        match="stale or lacks valid freshness metadata",
    ):
        build_market_feature_record(
            trades=trades,
            window_start=start,
            window_end=end,
            order_book=synchronized_order_book,
            order_book_observed_at=end,
            now=evaluation_time,
        )
