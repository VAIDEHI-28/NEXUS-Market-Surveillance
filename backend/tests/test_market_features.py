
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.features.market_features import MarketFeatureRecord
from nexus.features.order_book_features import OrderBookFeatures
from nexus.features.trade_features import TradeFeatures


@pytest.fixture
def trade_features():
    return TradeFeatures(
        symbol="BTCUSDT",
        trade_count=10,
        total_volume=2.5,
        buy_volume=1.5,
        sell_volume=1.0,
        volume_imbalance=0.2,
        trade_intensity=2.0,
        vwap=60000.0,
        price_return=0.001,
    )


@pytest.fixture
def order_book_features():
    return OrderBookFeatures(
        symbol="BTCUSDT",
        last_update_id=12345,
        mid_price=60010.0,
        spread=2.0,
        relative_spread=2.0 / 60010.0,
        bid_depth=15.0,
        ask_depth=12.0,
        depth_imbalance=3.0 / 27.0,
        depth_levels=5,
    )


def test_builds_unified_market_feature_record(
    trade_features, order_book_features
):
    timestamp = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    window_start = timestamp - timedelta(seconds=5)

    record = MarketFeatureRecord.from_features(
        timestamp=timestamp,
        trade_window_start=window_start,
        trade_window_end=timestamp,
        order_book_observed_at=timestamp,
        trade_features=trade_features,
        order_book_features=order_book_features,
    )

    assert record.symbol == "BTCUSDT"
    assert record.timestamp == timestamp
    assert record.trade_window_start == window_start
    assert record.trade_window_end == timestamp
    assert record.order_book_observed_at == timestamp
    assert record.trade_features == trade_features
    assert record.order_book_features == order_book_features


def test_normalizes_timestamp_to_utc(
    trade_features, order_book_features
):
    timestamp = datetime(
        2026, 10, 24, 15, 30,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    window_start = timestamp - timedelta(seconds=5)

    record = MarketFeatureRecord.from_features(
        timestamp=timestamp,
        trade_window_start=window_start,
        trade_window_end=timestamp,
        order_book_observed_at=timestamp,
        trade_features=trade_features,
        order_book_features=order_book_features,
    )

    assert record.timestamp.hour == 10
    assert record.timestamp.minute == 0
    assert record.timestamp.utcoffset().total_seconds() == 0
    assert record.trade_window_start.utcoffset().total_seconds() == 0
    assert record.trade_window_end.utcoffset().total_seconds() == 0
    assert record.order_book_observed_at.utcoffset().total_seconds() == 0


def test_rejects_mismatched_symbols(
    trade_features, order_book_features
):
    mismatched = order_book_features.model_copy(
        update={"symbol": "ETHUSDT"}
    )
    timestamp = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="symbols must match"):
        MarketFeatureRecord.from_features(
            timestamp=timestamp,
            trade_window_start=timestamp - timedelta(seconds=5),
            trade_window_end=timestamp,
            order_book_observed_at=timestamp,
            trade_features=trade_features,
            order_book_features=mismatched,
        )


def test_rejects_naive_timestamp(
    trade_features, order_book_features
):
    timestamp = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketFeatureRecord.from_features(
            timestamp=datetime(2026, 10, 24, 10, 0),
            trade_window_start=timestamp - timedelta(seconds=5),
            trade_window_end=timestamp,
            order_book_observed_at=timestamp,
            trade_features=trade_features,
            order_book_features=order_book_features,
        )


def test_record_is_immutable(
    trade_features, order_book_features
):
    timestamp = datetime.now(timezone.utc)

    record = MarketFeatureRecord.from_features(
        timestamp=timestamp,
        trade_window_start=timestamp - timedelta(seconds=5),
        trade_window_end=timestamp,
        order_book_observed_at=timestamp,
        trade_features=trade_features,
        order_book_features=order_book_features,
    )

    with pytest.raises(ValidationError):
        record.symbol = "ETHUSDT"

def test_rejects_trade_window_end_before_start(
    trade_features, order_book_features
):
    timestamp = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="Trade window end must be after"):
        MarketFeatureRecord.from_features(
            timestamp=timestamp,
            trade_window_start=timestamp,
            trade_window_end=timestamp - timedelta(seconds=1),
            order_book_observed_at=timestamp,
            trade_features=trade_features,
            order_book_features=order_book_features,
        )


def test_rejects_timestamp_different_from_trade_window_end(
    trade_features, order_book_features
):
    window_end = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="Timestamp must equal trade window end"):
        MarketFeatureRecord.from_features(
            timestamp=window_end + timedelta(seconds=1),
            trade_window_start=window_end - timedelta(seconds=5),
            trade_window_end=window_end,
            order_book_observed_at=window_end,
            trade_features=trade_features,
            order_book_features=order_book_features,
        )


def test_rejects_naive_order_book_observation_time(
    trade_features, order_book_features
):
    window_end = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketFeatureRecord.from_features(
            timestamp=window_end,
            trade_window_start=window_end - timedelta(seconds=5),
            trade_window_end=window_end,
            order_book_observed_at=datetime(2026, 10, 24, 10, 0),
            trade_features=trade_features,
            order_book_features=order_book_features,
        )
