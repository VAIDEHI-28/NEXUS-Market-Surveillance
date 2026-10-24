
from datetime import datetime, timedelta, timezone

import pytest

from nexus.detection.anomaly_detector import (
    DetectorConfig,
    MarketAnomalyDetector,
)
from nexus.features.market_features import MarketFeatureRecord
from nexus.features.order_book_features import OrderBookFeatures
from nexus.features.trade_features import TradeFeatures


BASE_TIME = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


def make_record(
    index: int,
    *,
    trade_intensity: float = 10.0,
    total_volume: float = 5.0,
    relative_spread: float = 0.001,
    bid_depth: float = 100.0,
    ask_depth: float = 100.0,
    depth_imbalance: float = 0.0,
) -> MarketFeatureRecord:
    start = BASE_TIME + timedelta(seconds=5 * index)
    end = start + timedelta(seconds=5)

    trades = TradeFeatures(
        symbol="BTCUSDT",
        trade_count=max(0, int(trade_intensity)),
        total_volume=total_volume,
        buy_volume=total_volume * (1 + depth_imbalance) / 2,
        sell_volume=total_volume * (1 - depth_imbalance) / 2,
        volume_imbalance=depth_imbalance,
        trade_intensity=trade_intensity,
        vwap=60000.0,
        price_return=0.0,
    )

    book = OrderBookFeatures(
        symbol="BTCUSDT",
        last_update_id=index + 1,
        mid_price=60000.0,
        spread=60.0,
        relative_spread=relative_spread,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        depth_imbalance=depth_imbalance,
        depth_levels=5,
    )

    return MarketFeatureRecord.from_features(
        timestamp=end,
        trade_features=trades,
        order_book_features=book,
        trade_window_start=start,
        trade_window_end=end,
        order_book_observed_at=end,
    )


def warmed_detector() -> MarketAnomalyDetector:
    detector = MarketAnomalyDetector(
        DetectorConfig(
            baseline_windows=30,
            min_baseline_windows=10,
        )
    )

    for index in range(10):
        assert detector.process(make_record(index)) == []

    return detector


def test_warmup_does_not_emit_alerts():
    detector = MarketAnomalyDetector()

    for index in range(10):
        alerts = detector.process(make_record(index))
        assert alerts == []


def test_detects_trade_intensity_spike():
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, trade_intensity=40.0)
    )

    assert any(
        alert.anomaly_type == "trade_intensity_spike"
        for alert in alerts
    )


def test_detects_trade_volume_spike():
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, total_volume=20.0)
    )

    assert any(
        alert.anomaly_type == "trade_volume_spike"
        for alert in alerts
    )


def test_detects_spread_widening():
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, relative_spread=0.003)
    )

    assert any(
        alert.anomaly_type == "spread_widening"
        for alert in alerts
    )


@pytest.mark.parametrize(
    ("field", "expected_type"),
    [
        ("bid_depth", "bid_depth_drop"),
        ("ask_depth", "ask_depth_drop"),
    ],
)
def test_detects_depth_drop(field, expected_type):
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, **{field: 30.0})
    )

    assert any(
        alert.anomaly_type == expected_type
        for alert in alerts
    )


def test_detects_depth_imbalance_shift():
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, depth_imbalance=0.8)
    )

    assert any(
        alert.anomaly_type == "depth_imbalance_shift"
        for alert in alerts
    )


def test_alert_contains_explanation_and_measurements():
    detector = warmed_detector()

    alerts = detector.process(
        make_record(10, trade_intensity=40.0)
    )

    alert = next(
        alert
        for alert in alerts
        if alert.anomaly_type == "trade_intensity_spike"
    )

    assert alert.symbol == "BTCUSDT"
    assert alert.observed_value == 40.0
    assert alert.baseline_value == 10.0
    assert alert.score == 4.0
    assert alert.severity == "high"
    assert "rolling median baseline" in alert.evidence


def test_rejects_out_of_order_records():
    detector = MarketAnomalyDetector()

    detector.process(make_record(1))

    with pytest.raises(ValueError, match="strictly increasing"):
        detector.process(make_record(0))


def test_separate_symbols_have_independent_baselines():
    detector = MarketAnomalyDetector()

    for index in range(10):
        detector.process(make_record(index))

    other_symbol = make_record(10).model_copy(
        update={"symbol": "ETHUSDT"}
    )

    # The nested feature symbols must also match the record symbol.
    other_symbol = other_symbol.model_copy(
        update={
            "trade_features": other_symbol.trade_features.model_copy(
                update={"symbol": "ETHUSDT"}
            ),
            "order_book_features": (
                other_symbol.order_book_features.model_copy(
                    update={"symbol": "ETHUSDT"}
                )
            ),
        }
    )

    assert detector.process(other_symbol) == []
