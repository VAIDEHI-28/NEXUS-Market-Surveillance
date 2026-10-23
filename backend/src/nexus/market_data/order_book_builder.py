
from decimal import Decimal


class OrderBookBuilder:
    """Maintain local bid and ask price levels."""

    def __init__(self):
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_update_id: int | None = None
        self.is_valid = False
        self.is_synchronized = False

    def load_snapshot(
        self,
        last_update_id: int,
        bids: list[list[str]],
        asks: list[list[str]],
    ) -> None:
        """Load the initial REST snapshot."""
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
    ) -> bool:
        """Apply a depth event only to a synchronized order book."""

        if (
            not self.is_valid
            or not self.is_synchronized
            or self.last_update_id is None
        ):
            return False

        # Ignore events that are already covered by the current state.
        if final_update_id <= self.last_update_id:
            return False

        # A gap means one or more updates may be missing.
        if first_update_id > self.last_update_id + 1:
            self.is_valid = False
            self.is_synchronized = False
            return False

        self.apply_levels(self.bids, bids)
        self.apply_levels(self.asks, asks)
        self.last_update_id = final_update_id

        return True

