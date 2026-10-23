
from datetime import datetime, timezone

import pyarrow.parquet as pq

from nexus.schemas.trade import TradeEvent
from nexus.storage.trades import TradeStorage


def make_trade(trade_id: int) -> TradeEvent:
    return TradeEvent(
        symbol="BTCUSDT",
        price=81744.02,
        quantity=0.00007,
        trade_id=trade_id,
        event_time=datetime.now(timezone.utc),
        buyer_is_maker=False,
    )


def test_write_batch_creates_parquet_file(tmp_path):
    storage = TradeStorage(str(tmp_path))

    path = storage.write_batch([make_trade(1), make_trade(2)])

    assert path is not None
    assert path.exists()

    table = pq.read_table(path)
    assert table.num_rows == 2
    assert table.column_names == [
        "symbol",
        "price",
        "quantity",
        "trade_id",
        "event_time",
        "buyer_is_maker",
    ]


def test_separate_batches_create_separate_files(tmp_path):
    storage = TradeStorage(str(tmp_path))

    first = storage.write_batch([make_trade(1), make_trade(2)])
    second = storage.write_batch([make_trade(3)])

    assert first is not None
    assert second is not None
    assert first != second

    files = list(tmp_path.glob("*.parquet"))
    assert len(files) == 2

    total_rows = sum(pq.read_table(file).num_rows for file in files)
    assert total_rows == 3


def test_empty_batch_writes_nothing(tmp_path):
    storage = TradeStorage(str(tmp_path))

    result = storage.write_batch([])

    assert result is None
    assert list(tmp_path.glob("*.parquet")) == []
