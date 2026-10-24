
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderBookLevel(BaseModel):
    """One price level in the visible order book."""

    model_config = ConfigDict(frozen=True)

    price: float = Field(gt=0)
    quantity: float = Field(ge=0)


class OrderBookSnapshot(BaseModel):
    """A validated view of the visible order book."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    last_update_id: int = Field(ge=0)
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]

    @model_validator(mode="after")
    def validate_book_structure(self):
        """Ensure levels are unique, correctly ordered, and uncrossed."""
        bid_prices = [level.price for level in self.bids]
        ask_prices = [level.price for level in self.asks]

        if len(bid_prices) != len(set(bid_prices)):
            raise ValueError("Duplicate bid prices are not allowed")

        if len(ask_prices) != len(set(ask_prices)):
            raise ValueError("Duplicate ask prices are not allowed")

        if any(
            current <= following
            for current, following in zip(bid_prices, bid_prices[1:])
        ):
            raise ValueError("Bids must be sorted from highest to lowest price")

        if any(
            current >= following
            for current, following in zip(ask_prices, ask_prices[1:])
        ):
            raise ValueError("Asks must be sorted from lowest to highest price")

        if self.bids and self.asks:
            if self.bids[0].price >= self.asks[0].price:
                raise ValueError("Order book must have a positive spread")

        return self
