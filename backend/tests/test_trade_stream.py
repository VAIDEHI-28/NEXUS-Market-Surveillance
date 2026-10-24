
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.trade_stream import stream_trades


@pytest.mark.asyncio
async def test_stream_trades_forwards_parsed_trade():
    event_time = datetime(
        2026, 10, 24, 10, 0, tzinfo=timezone.utc
    )

    message = json.dumps(
        {
            "e": "trade",
            "s": "BTCUSDT",
            "p": "60000.0",
            "q": "0.1",
            "t": 12345,
            "T": int(event_time.timestamp() * 1000),
            "m": False,
        }
    )

    callback = AsyncMock()

    websocket = MagicMock()
    websocket.__aiter__.return_value = [message]

    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=websocket)
    connection.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "nexus.trade_stream.connect",
            side_effect=[connection, asyncio.CancelledError()],
        ),
        patch("nexus.trade_stream.TradeStorage") as storage_class,
    ):
        storage = storage_class.return_value
        storage.write_batch.return_value = None

        with pytest.raises(asyncio.CancelledError):
            await stream_trades(on_trade=callback)

    callback.assert_awaited_once()

    trade = callback.await_args.args[0]

    assert trade.symbol == "BTCUSDT"
    assert trade.price == 60000.0
    assert trade.quantity == 0.1
    assert trade.trade_id == 12345
    assert trade.event_time == event_time

    storage.write_batch.assert_called_once()
