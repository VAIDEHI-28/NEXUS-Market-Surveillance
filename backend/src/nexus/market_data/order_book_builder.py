
from datetime import datetime, timezone
from decimal import Decimal


class OrderBookBuilder:
    """Maintain local bid/ask levels and depth-update timing metadata."""

    def __init__(self):
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_update_id: int | None = None
        self.is_valid = False
        self.is_synchronized = False

        # Timing metadata for the last successfully applied depth event.
        self.last_event_time: datetime | None = None
        self.last_received_at: datetime | None = None

    def load_snapshot(
        self,
        last_update_id: int,
        bids: list[list[str]],
        asks: list[list[str]],
    ) -> None:
        """Load a REST snapshot and reset depth-event timing metadata."""
        self.bids = {
            Decimal(price): Decimal(quantity)
            for price, quantity in bids
            if Decimal(quantity) > 0
        }
        self.asks = {
            Decimal(price): Decimal(quantity)
            for price, quantity in asks
            if Decimal(quantity) > 0
        }

        self.last_update_id = last_update_id
        self.is_valid = True
        self.is_synchronized = False

        # A REST snapshot does not supply depth-event timing metadata here.
        self.last_event_time = None
        self.last_received_at = None

    def apply_levels(
        self,
        side: dict[Decimal, Decimal],
        updates: list[list[str]],
    ) -> None:
        """Apply price-level updates; zero quantity removes a level."""
        for price_text, quantity_text in updates:
            price = Decimal(price_text)
            quantity = Decimal(quantity_text)

            if quantity == 0:
                side.pop(price, None)
            else:
                side[price] = quantity

    def best_bid(self) -> tuple[Decimal, Decimal] | None:
        if not self.bids:
            return None
        price = max(self.bids)
        return price, self.bids[price]

    def best_ask(self) -> tuple[Decimal, Decimal] | None:
        if not self.asks:
            return None
        price = min(self.asks)
        return price, self.asks[price]

    def apply_depth_event(
        self,
        first_update_id: int,
        final_update_id: int,
        bids: list[list[str]],
        asks: list[list[str]],
        event_time: datetime | None = None,
        received_at: datetime | None = None,
    ) -> bool:
        """Apply a contiguous depth event and record its timing metadata."""
        if (
            not self.is_valid
            or not self.is_synchronized
            or self.last_update_id is None
        ):
            return False

        # Ignore events already represented by the current state.
        if final_update_id <= self.last_update_id:
            return False

        # A sequence gap invalidates the current state.
        if first_update_id > self.last_update_id + 1:
            self.is_valid = False
            self.is_synchronized = False
            return False

        # Validate supplied timestamps before mutating the book.
        for name, value in (
            ("event_time", event_time),
            ("received_at", received_at),
        ):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError(f"{name} must be timezone-aware")

        self.apply_levels(self.bids, bids)
        self.apply_levels(self.asks, asks)
        self.last_update_id = final_update_id

        # Normalize timestamps to UTC, preserving None for legacy callers.
        self.last_event_time = (
            event_time.astimezone(timezone.utc)
            if event_time is not None
            else None
        )
        self.last_received_at = (
            received_at.astimezone(timezone.utc)
            if received_at is not None
            else None
        )

        return True
