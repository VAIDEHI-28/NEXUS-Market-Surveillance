
from collections.abc import Sequence
from datetime import datetime, timezone

from nexus.features.trade_features import TradeFeatures
from nexus.schemas.trade import TradeEvent


def calculate_trade_features(
    trades: Sequence[TradeEvent],
    window_start: datetime,
    window_end: datetime,
) -> TradeFeatures:
    """Calculate trade-flow features for a UTC time window [start, end)."""
    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise ValueError("window_start must be timezone-aware")

    if window_end.tzinfo is None or window_end.utcoffset() is None:
        raise ValueError("window_end must be timezone-aware")

    window_start = window_start.astimezone(timezone.utc)
    window_end = window_end.astimezone(timezone.utc)

    window_seconds = (window_end - window_start).total_seconds()
    if window_seconds <= 0:
        raise ValueError("window_end must be after window_start")

    if not trades:
        raise ValueError("trades must not be empty")

    symbols = {trade.symbol for trade in trades}
    if len(symbols) != 1:
        raise ValueError("All trades must belong to the same symbol")

    for trade in trades:
        if trade.event_time.tzinfo is None or trade.event_time.utcoffset() is None:
            raise ValueError("All trade timestamps must be timezone-aware")

        event_time = trade.event_time.astimezone(timezone.utc)
        if not (window_start <= event_time < window_end):
            raise ValueError("All trades must fall inside the time window [start, end)")

    total_volume = sum(trade.quantity for trade in trades)

    # buyer_is_maker=True means the seller was the aggressor.
    buy_volume = sum(
        trade.quantity for trade in trades
        if not trade.buyer_is_maker
    )
    sell_volume = sum(
        trade.quantity for trade in trades
        if trade.buyer_is_maker
    )

    volume_imbalance = (
        (buy_volume - sell_volume) / total_volume
        if total_volume > 0
        else 0.0
    )

    total_notional = sum(
        trade.price * trade.quantity for trade in trades
    )
    vwap = total_notional / total_volume if total_volume > 0 else None

    first_trade = min(trades, key=lambda trade: trade.event_time)
    last_trade = max(trades, key=lambda trade: trade.event_time)

    price_return = (
        (last_trade.price - first_trade.price) / first_trade.price
        if first_trade.price > 0
        else None
    )

    return TradeFeatures(
        symbol=trades[0].symbol,
        trade_count=len(trades),
        total_volume=total_volume,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        volume_imbalance=volume_imbalance,
        trade_intensity=len(trades) / window_seconds,
        vwap=vwap,
        price_return=price_return,
    )
