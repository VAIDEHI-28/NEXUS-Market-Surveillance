
from pydantic import BaseModel, ConfigDict, Field


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
