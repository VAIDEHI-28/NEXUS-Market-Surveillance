
import pytest
from pydantic import ValidationError

from nexus.market_data.order_book import (
    OrderBookLevel,
    OrderBookSnapshot,
)


def test_valid_order_book_snapshot():
    snapshot = OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=12345,
        bids=(OrderBookLevel(price=100.0, quantity=2.0),),
        asks=(OrderBookLevel(price=101.0, quantity=3.0),),
    )

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.last_update_id == 12345
    assert len(snapshot.bids) == 1
    assert len(snapshot.asks) == 1


@pytest.mark.parametrize("price", [0, -1])
def test_order_book_rejects_non_positive_prices(price):
    with pytest.raises(ValidationError):
        OrderBookLevel(price=price, quantity=1.0)


@pytest.mark.parametrize("quantity", [-1, -0.1])
def test_order_book_rejects_negative_quantities(quantity):
    with pytest.raises(ValidationError):
        OrderBookLevel(price=100.0, quantity=quantity)


def test_order_book_allows_zero_quantity():
    level = OrderBookLevel(price=100.0, quantity=0)

    assert level.quantity == 0
