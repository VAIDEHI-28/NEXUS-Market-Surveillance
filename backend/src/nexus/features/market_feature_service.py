
from datetime import datetime, timezone
from math import isfinite

from nexus.features.market_features import MarketFeatureRecord
from nexus.features.order_book_calculator import (
    calculate_order_book_features,
)
from nexus.features.trade_calculator import calculate_trade_features
from nexus.market_data.freshness import is_order_book_fresh
from nexus.market_data.order_book import (
    OrderBookLevel,
    OrderBookSnapshot,
)
from nexus.market_data.order_book_builder import OrderBookBuilder
from nexus.schemas.trade import TradeEvent


def build_market_feature_record(
    trades: list[TradeEvent],
    window_start: datetime,
    window_end: datetime,
    order_book: OrderBookBuilder,
    order_book_observed_at: datetime,
    symbol: str = "BTCUSDT",
    depth_levels: int = 5,
    max_order_book_age_seconds: float = 5.0,
    now: datetime | None = None,
) -> MarketFeatureRecord:
    """Build unified market features only from fresh, valid market data."""

    # Validate basic order-book state first so callers receive
    # the most useful validation error.
    if not order_book.is_valid or not order_book.is_synchronized:
        raise ValueError(
            "Order book must be valid and synchronized"
        )

    if order_book.last_update_id is None:
        raise ValueError("Order book has no update ID")

    if not order_book.bids or not order_book.asks:
        raise ValueError("Order book must contain both bids and asks")

    if not symbol.strip():
        raise ValueError("Symbol must not be empty")

    if any(trade.symbol != symbol for trade in trades):
        raise ValueError("All trades must match the requested symbol")

    for price, quantity in (
        *order_book.bids.items(),
        *order_book.asks.items(),
    ):
        if not isfinite(float(price)) or not isfinite(float(quantity)):
            raise ValueError("Order book levels must be finite")

        if price <= 0 or quantity <= 0:
            raise ValueError(
                "Order book prices and quantities must be positive"
            )

    best_bid = max(order_book.bids)
    best_ask = min(order_book.asks)

    if best_bid >= best_ask:
        raise ValueError("Order book must have a positive spread")

    # Reject stale books before calculating or returning features.
    evaluation_time = (
        now if now is not None else datetime.now(timezone.utc)
    )

    if not is_order_book_fresh(
        order_book=order_book,
        now=evaluation_time,
        max_age_seconds=max_order_book_age_seconds,
    ):
        raise ValueError(
            "Order book is stale or lacks valid freshness metadata"
        )

    snapshot = OrderBookSnapshot(
        symbol=symbol,
        last_update_id=order_book.last_update_id,
        bids=tuple(
            OrderBookLevel(
                price=float(price),
                quantity=float(quantity),
            )
            for price, quantity in sorted(
                order_book.bids.items(),
                reverse=True,
            )
        ),
        asks=tuple(
            OrderBookLevel(
                price=float(price),
                quantity=float(quantity),
            )
            for price, quantity in sorted(order_book.asks.items())
        ),
    )

    trade_features = calculate_trade_features(
        trades=trades,
        window_start=window_start,
        window_end=window_end,
    )

    order_book_features = calculate_order_book_features(
        snapshot=snapshot,
        depth_levels=depth_levels,
    )

    return MarketFeatureRecord.from_features(
        timestamp=window_end,
        trade_window_start=window_start,
        trade_window_end=window_end,
        order_book_observed_at=order_book_observed_at,
        trade_features=trade_features,
        order_book_features=order_book_features,
    )
