
import pytest
from pydantic import ValidationError
from nexus.features.order_book_calculator import (
    calculate_order_book_features,
)
from nexus.market_data.order_book import (
    OrderBookLevel,
    OrderBookSnapshot,
)


def make_snapshot(
    bids=None,
    asks=None,
) -> OrderBookSnapshot:
    if bids is None:
        bids = [
            (99.0, 5.0),
            (98.0, 4.0),
            (97.0, 3.0),
            (96.0, 2.0),
            (95.0, 1.0),
            (94.0, 100.0),
        ]

    if asks is None:
        asks = [
            (101.0, 2.0),
            (102.0, 3.0),
            (103.0, 4.0),
            (104.0, 5.0),
            (105.0, 6.0),
            (106.0, 100.0),
        ]

    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=12345,
        bids=tuple(
            OrderBookLevel(price=price, quantity=quantity)
            for price, quantity in bids
        ),
        asks=tuple(
            OrderBookLevel(price=price, quantity=quantity)
            for price, quantity in asks
        ),
    )


def test_mid_price_and_spread():
    result = calculate_order_book_features(make_snapshot())

    assert result.mid_price == pytest.approx(100.0)
    assert result.spread == pytest.approx(2.0)
    assert result.relative_spread == pytest.approx(0.02)


def test_top_five_depth_excludes_sixth_level():
    result = calculate_order_book_features(
        make_snapshot(),
        depth_levels=5,
    )

    assert result.bid_depth == pytest.approx(15.0)
    assert result.ask_depth == pytest.approx(20.0)


def test_depth_imbalance():
    result = calculate_order_book_features(make_snapshot())

    assert result.depth_imbalance == pytest.approx(-5.0 / 35.0)


def test_depth_level_count_is_recorded():
    result = calculate_order_book_features(
        make_snapshot(),
        depth_levels=3,
    )

    assert result.depth_levels == 3
    assert result.bid_depth == pytest.approx(12.0)
    assert result.ask_depth == pytest.approx(9.0)


def test_rejects_zero_depth_levels():
    with pytest.raises(ValueError, match="depth_levels"):
        calculate_order_book_features(
            make_snapshot(),
            depth_levels=0,
        )


def test_rejects_empty_bid_side():
    snapshot = make_snapshot(bids=[])

    with pytest.raises(ValueError, match="both bids and asks"):
        calculate_order_book_features(snapshot)


def test_rejects_empty_ask_side():
    snapshot = make_snapshot(asks=[])

    with pytest.raises(ValueError, match="both bids and asks"):
        calculate_order_book_features(snapshot)


def test_rejects_crossed_book():
    with pytest.raises(ValidationError, match="positive spread"):
        make_snapshot(
            bids=[(102.0, 5.0)],
            asks=[(101.0, 4.0)],
        )


def test_rejects_locked_book():
    with pytest.raises(ValidationError, match="positive spread"):
        make_snapshot(
            bids=[(100.0, 5.0)],
            asks=[(100.0, 4.0)],
        )

def test_preserves_snapshot_metadata():
    result = calculate_order_book_features(make_snapshot())

    assert result.symbol == "BTCUSDT"
    assert result.last_update_id == 12345
