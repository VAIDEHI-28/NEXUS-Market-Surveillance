
from datetime import datetime, timedelta, timezone
from math import isfinite

from nexus.features.market_feature_service import (
    build_market_feature_record,
)
from nexus.features.market_features import MarketFeatureRecord
from nexus.market_data.order_book_builder import OrderBookBuilder
from nexus.schemas.trade import TradeEvent


class TradeWindowBuffer:
    """Group trades into fixed-width event-time windows."""

    def __init__(
        self,
        window_seconds: float = 5.0,
        allowed_lateness_seconds: float = 0.0,
    ) -> None:
        if not isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError(
                "window_seconds must be positive and finite"
            )

        if (
            not isfinite(allowed_lateness_seconds)
            or allowed_lateness_seconds < 0
        ):
            raise ValueError(
                "allowed_lateness_seconds must be non-negative and finite"
            )

        self.window_width = timedelta(seconds=window_seconds)
        self.allowed_lateness = timedelta(
            seconds=allowed_lateness_seconds
        )

        self._windows: dict[datetime, list[TradeEvent]] = {}
        self._watermark: datetime | None = None
        self._closed_through: datetime | None = None

        self.late_trade_count = 0

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        """Convert an aware timestamp to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")

        return value.astimezone(timezone.utc)

    def _window_start(self, event_time: datetime) -> datetime:
        """Return the UTC start of the event's fixed-width window."""
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        elapsed = (event_time - epoch).total_seconds()
        window_number = int(
            elapsed / self.window_width.total_seconds()
        )

        return epoch + window_number * self.window_width

    def add_trade(self, trade: TradeEvent) -> bool:
        """
        Add a trade to its event-time window.

        Returns False and increments late_trade_count when the trade
        belongs to a window that has already closed or is too late
        under the configured watermark policy.
        """
        event_time = self._normalize_timestamp(trade.event_time)
        start = self._window_start(event_time)
        end = start + self.window_width

        # Never reopen a window already emitted.
        if (
            self._closed_through is not None
            and end <= self._closed_through
        ):
            self.late_trade_count += 1
            return False

        if self._watermark is not None:
            # The watermark closes every window ending at or before it,
            # including windows that had no trades when it advanced.
            if end <= self._watermark:
                self.late_trade_count += 1
                return False

            # Reject events outside the configured event-time lateness
            # allowance.
            if event_time < self._watermark - self.allowed_lateness:
                self.late_trade_count += 1
                return False

        self._windows.setdefault(start, []).append(trade)
        return True

    def advance_watermark(
        self,
        watermark: datetime,
    ) -> list[tuple[datetime, datetime, list[TradeEvent]]]:
        """
        Emit buffered windows ending at or before the watermark.

        Watermarks must be timezone-aware and cannot move backwards.
        """
        watermark = self._normalize_timestamp(watermark)

        if self._watermark is not None and watermark < self._watermark:
            raise ValueError("Watermark must not move backwards")

        self._watermark = watermark
        completed: list[
            tuple[datetime, datetime, list[TradeEvent]]
        ] = []

        for start in sorted(self._windows):
            end = start + self.window_width

            if end <= watermark:
                completed.append(
                    (start, end, self._windows[start])
                )

        for start, end, _ in completed:
            del self._windows[start]

            if (
                self._closed_through is None
                or end > self._closed_through
            ):
                self._closed_through = end

        return completed


def build_completed_window_features(
    window: tuple[datetime, datetime, list[TradeEvent]],
    order_book: OrderBookBuilder,
    symbol: str = "BTCUSDT",
    max_order_book_age_seconds: float = 5.0,
    now: datetime | None = None,
) -> MarketFeatureRecord:
    """
    Build a market feature record for one completed trade window.

    Combines the window's trades with the latest order-book state
    using the existing market feature service. The service validates
    order-book synchronization, freshness, and feature inputs.
    """
    window_start, window_end, trades = window

    if not trades:
        raise ValueError(
            "Cannot build features for an empty trade window"
        )

    if any(trade.symbol != symbol for trade in trades):
        raise ValueError(
            "All trades must match the requested symbol"
        )

    order_book_observed_at = order_book.last_received_at

    if order_book_observed_at is None:
        raise ValueError(
            "Order book has no observation timestamp"
        )

    return build_market_feature_record(
        trades=trades,
        window_start=window_start,
        window_end=window_end,
        order_book=order_book,
        order_book_observed_at=order_book_observed_at,
        symbol=symbol,
        max_order_book_age_seconds=max_order_book_age_seconds,
        now=now,
    )
