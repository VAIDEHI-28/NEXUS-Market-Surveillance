
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TradeEvent(BaseModel):
    """Validated representation of a Binance spot trade."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    trade_id: int = Field(ge=0)
    event_time: datetime
    buyer_is_maker: bool
