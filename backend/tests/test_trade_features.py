
from datetime import datetime, timedelta, timezone

import pytest

from nexus.features.trade_calculator import calculate_trade_features
from nexus.schemas.trade import TradeEvent


START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
END = START + timedelta(seconds=10)


def make_trade(
    *,
    price: float,
    quantity: float,
    trade_id: int,
    buyer_is_maker: bool,
    second: int,
    symbol: str = "BTCUSDT",
    event_time: datetime | None = None,
) -> TradeEvent:
    return TradeEvent(
        symbol=symbol,
        price=price,
        quantity=quantity,
        trade_id=trade_id,
        event_time=event_time or START + timedelta(seconds=second),
        buyer_is_maker=buyer_is_maker,
    )


@pytest.fixture
def sample_trades() -> list[TradeEvent]:
    return [
        make_trade(
            price=100.0, quantity=2.0, trade_id=1,
            buyer_is_maker=False, second=1,
        ),
        make_trade(
            price=110.0, quantity=1.0, trade_id=2,
            buyer_is_maker=True, second=2,
        ),
        make_trade(
            price=120.0, quantity=3.0, trade_id=3,
            buyer_is_maker=False, second=3,
        ),
    ]


def calculate(trades):
    return calculate_trade_features(trades, window_start=START, window_end=END)


def test_trade_count_and_volumes(sample_trades):
    result = calculate(sample_trades)

    assert result.trade_count == 3
    assert result.total_volume == pytest.approx(6.0)
    assert result.buy_volume == pytest.approx(5.0)
    assert result.sell_volume == pytest.approx(1.0)


def test_volume_imbalance(sample_trades):
    result = calculate(sample_trades)

    assert result.volume_imbalance == pytest.approx(4.0 / 6.0)


def test_trade_intensity(sample_trades):
    result = calculate(sample_trades)

    assert result.trade_intensity == pytest.approx(0.3)


def test_vwap(sample_trades):
    result = calculate(sample_trades)

    expected_vwap = (100.0 * 2.0 + 110.0 * 1.0 + 120.0 * 3.0) / 6.0
    assert result.vwap == pytest.approx(expected_vwap)


def test_price_return_uses_chronological_order(sample_trades):
    result = calculate(list(reversed(sample_trades)))

    assert result.price_return == pytest.approx(0.2)


def test_rejects_empty_trades():
    with pytest.raises(ValueError, match="trades"):
        calculate([])


def test_rejects_mixed_symbols(sample_trades):
    other_trade = make_trade(
        price=100.0,
        quantity=1.0,
        trade_id=4,
        buyer_is_maker=False,
        second=4,
        symbol="ETHUSDT",
    )

    with pytest.raises(ValueError, match="same symbol"):
        calculate(sample_trades + [other_trade])


def test_includes_trade_at_window_start(sample_trades):
    at_start = make_trade(
        price=90.0,
        quantity=1.0,
        trade_id=10,
        buyer_is_maker=False,
        second=0,
    )

    result = calculate([at_start])

    assert result.trade_count == 1


def test_rejects_trade_at_window_end(sample_trades):
    at_end = make_trade(
        price=90.0,
        quantity=1.0,
        trade_id=11,
        buyer_is_maker=False,
        second=10,
    )

    with pytest.raises(ValueError, match="inside the time window"):
        calculate([at_end])


def test_rejects_trade_before_window(sample_trades):
    before_start = make_trade(
        price=90.0,
        quantity=1.0,
        trade_id=12,
        buyer_is_maker=False,
        second=0,
        event_time=START - timedelta(microseconds=1),
    )

    with pytest.raises(ValueError, match="inside the time window"):
        calculate([before_start])


def test_rejects_naive_window_start(sample_trades):
    naive_start = START.replace(tzinfo=None)

    with pytest.raises(ValueError, match="window_start"):
        calculate_trade_features(
            sample_trades,
            window_start=naive_start,
            window_end=END,
        )


def test_rejects_naive_trade_timestamp():
    naive_trade = make_trade(
        price=100.0,
        quantity=1.0,
        trade_id=13,
        buyer_is_maker=False,
        second=1,
        event_time=datetime(2026, 1, 1, 0, 0, 1),
    )

    with pytest.raises(ValueError, match="trade timestamps"):
        calculate([naive_trade])


def test_rejects_invalid_window_duration(sample_trades):
    with pytest.raises(ValueError, match="after window_start"):
        calculate_trade_features(
            sample_trades,
            window_start=END,
            window_end=START,
        )


def test_accepts_equivalent_timezone():
    # UTC+05:30 window representing the same instant range as START..END.
    local_start = START.astimezone(timezone(timedelta(hours=5, minutes=30)))
    local_end = END.astimezone(timezone(timedelta(hours=5, minutes=30)))

    trade = make_trade(
        price=100.0,
        quantity=1.0,
        trade_id=14,
        buyer_is_maker=False,
        second=1,
    )

    result = calculate_trade_features(
        [trade],
        window_start=local_start,
        window_end=local_end,
    )

    assert result.trade_count == 1
    assert result.trade_intensity == pytest.approx(0.1)
