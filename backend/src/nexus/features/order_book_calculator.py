
from math import isfinite

from nexus.features.order_book_features import OrderBookFeatures
from nexus.market_data.order_book import OrderBookSnapshot


def calculate_order_book_features(
    snapshot: OrderBookSnapshot,
    depth_levels: int = 5,
) -> OrderBookFeatures:
    """Calculate liquidity features from a validated order-book snapshot."""
    if depth_levels <= 0:
        raise ValueError("depth_levels must be greater than zero")

    if not snapshot.bids or not snapshot.asks:
        raise ValueError("Order book must contain both bids and asks")

    best_bid = max(snapshot.bids, key=lambda level: level.price)
    best_ask = min(snapshot.asks, key=lambda level: level.price)

    if best_bid.price >= best_ask.price:
        raise ValueError("Order book must not be crossed or locked")

    mid_price = (best_bid.price + best_ask.price) / 2.0
    spread = best_ask.price - best_bid.price
    relative_spread = spread / mid_price

    # Sum the largest bid prices and smallest ask prices first.
    top_bids = sorted(
        snapshot.bids, key=lambda level: level.price, reverse=True
    )[:depth_levels]
    top_asks = sorted(
        snapshot.asks, key=lambda level: level.price
    )[:depth_levels]

    bid_depth = sum(level.quantity for level in top_bids)
    ask_depth = sum(level.quantity for level in top_asks)
    total_depth = bid_depth + ask_depth

    depth_imbalance = (
        (bid_depth - ask_depth) / total_depth
        if total_depth > 0
        else 0.0
    )

    values = (
        mid_price,
        spread,
        relative_spread,
        bid_depth,
        ask_depth,
        depth_imbalance,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("Order-book features must be finite")

    return OrderBookFeatures(
        symbol=snapshot.symbol,
        last_update_id=snapshot.last_update_id,
        mid_price=mid_price,
        spread=spread,
        relative_spread=relative_spread,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        depth_imbalance=depth_imbalance,
        depth_levels=depth_levels,
    )
