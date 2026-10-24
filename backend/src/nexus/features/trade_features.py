
from pydantic import BaseModel, ConfigDict, Field


class TradeFeatures(BaseModel):
    """Derived market features for a single trade-data window."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    trade_count: int = Field(ge=0)

    total_volume: float = Field(ge=0)
    buy_volume: float = Field(ge=0)
    sell_volume: float = Field(ge=0)

    volume_imbalance: float = Field(ge=-1, le=1)

    trade_intensity: float = Field(ge=0)
    vwap: float | None = Field(default=None, gt=0)
    price_return: float | None = None
