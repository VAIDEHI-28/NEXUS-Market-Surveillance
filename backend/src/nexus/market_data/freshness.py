
from datetime import datetime, timezone
from math import isfinite

from nexus.market_data.order_book_builder import OrderBookBuilder


def is_order_book_fresh(
    order_book: OrderBookBuilder,
    now: datetime,
    max_age_seconds: float = 5.0,
) -> bool:
    """Return whether the order book is valid, synchronized, and fresh."""
    if not isfinite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive and finite")

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if not order_book.is_valid or not order_book.is_synchronized:
        return False

    received_at = order_book.last_received_at

    if received_at is None:
        return False

    if received_at.tzinfo is None or received_at.utcoffset() is None:
        return False

    now_utc = now.astimezone(timezone.utc)
    received_at_utc = received_at.astimezone(timezone.utc)

    age_seconds = (now_utc - received_at_utc).total_seconds()

    # Reject future timestamps rather than treating them as fresh.
    if age_seconds < 0:
        return False

    return age_seconds <= max_age_seconds
