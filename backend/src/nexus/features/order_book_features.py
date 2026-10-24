
from pydantic import BaseModel, ConfigDict, Field


class OrderBookFeatures(BaseModel):
    """Derived liquidity features from an order-book snapshot."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    last_update_id: int = Field(ge=0)

    mid_price: float = Field(gt=0)
    spread: float = Field(ge=0)
    relative_spread: float = Field(ge=0)

    bid_depth: float = Field(ge=0)
    ask_depth: float = Field(ge=0)
    depth_imbalance: float = Field(ge=-1, le=1)

    depth_levels: int = Field(gt=0)
