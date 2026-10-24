
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nexus.features.order_book_features import OrderBookFeatures
from nexus.features.trade_features import TradeFeatures


class MarketFeatureRecord(BaseModel):
    """Unified market features with explicit temporal provenance."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    timestamp: datetime

    trade_window_start: datetime
    trade_window_end: datetime
    order_book_observed_at: datetime

    trade_features: TradeFeatures
    order_book_features: OrderBookFeatures

    @field_validator(
        "timestamp",
        "trade_window_start",
        "trade_window_end",
        "order_book_observed_at",
    )
    @classmethod
    def normalize_timestamp_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must be timezone-aware")

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_record_consistency(self):
        if self.trade_window_end <= self.trade_window_start:
            raise ValueError("Trade window end must be after its start")

        if self.timestamp != self.trade_window_end:
            raise ValueError("Timestamp must equal trade window end")

        if self.symbol != self.trade_features.symbol:
            raise ValueError("Record and trade symbols must match")

        if self.symbol != self.order_book_features.symbol:
            raise ValueError("Record and order-book symbols must match")

        return self

    @classmethod
    def from_features(
        cls,
        timestamp: datetime,
        trade_features: TradeFeatures,
        order_book_features: OrderBookFeatures,
        trade_window_start: datetime,
        trade_window_end: datetime,
        order_book_observed_at: datetime,
    ) -> "MarketFeatureRecord":
        if trade_features.symbol != order_book_features.symbol:
            raise ValueError("Trade and order-book symbols must match")

        return cls(
            symbol=trade_features.symbol,
            timestamp=timestamp,
            trade_window_start=trade_window_start,
            trade_window_end=trade_window_end,
            order_book_observed_at=order_book_observed_at,
            trade_features=trade_features,
            order_book_features=order_book_features,
        )
