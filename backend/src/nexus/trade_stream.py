
import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from websockets.asyncio.client import connect

from nexus.schemas.trade import TradeEvent
from nexus.storage.trades import TradeStorage


BINANCE_TRADE_STREAM = "wss://stream.binance.com:9443/ws/btcusdt@trade"
BATCH_SIZE = 100
FLUSH_INTERVAL_SECONDS = 5
RECONNECT_DELAY_SECONDS = 5

TradeCallback = Callable[
    [TradeEvent],
    Awaitable[None] | None,
]


async def stream_trades(
    on_trade: TradeCallback | None = None,
) -> None:
    """
    Consume Binance trades, optionally forward them to a callback,
    and persist batches to Parquet.

    The callback is invoked once for each successfully parsed trade.
    Existing callers can continue using stream_trades() without args.
    """
    storage = TradeStorage()
    batch: list[TradeEvent] = []
    loop = asyncio.get_running_loop()
    last_flush = loop.time()

    try:
        while True:
            try:
                print("Connecting to Binance BTCUSDT trade stream...")

                async with connect(BINANCE_TRADE_STREAM) as websocket:
                    print("Connected. Collecting live trades...\n")

                    async for message in websocket:
                        raw = json.loads(message)

                        trade = TradeEvent(
                            symbol=raw["s"],
                            price=float(raw["p"]),
                            quantity=float(raw["q"]),
                            trade_id=int(raw["t"]),
                            event_time=datetime.fromtimestamp(
                                raw["T"] / 1000,
                                tz=timezone.utc,
                            ),
                            buyer_is_maker=raw["m"],
                        )

                        # Forward the trade to feature processing.
                        # Do not silently swallow callback failures.
                        if on_trade is not None:
                            result = on_trade(trade)
                            if inspect.isawaitable(result):
                                await result

                        batch.append(trade)

                        now = loop.time()
                        if (
                            len(batch) >= BATCH_SIZE
                            or now - last_flush >= FLUSH_INTERVAL_SECONDS
                        ):
                            path = storage.write_batch(batch)

                            if path is not None:
                                print(
                                    f"Saved {len(batch)} trades to {path}"
                                )
                                batch.clear()
                                last_flush = now

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Stream error: {exc}")
                print(
                    f"Retrying in {RECONNECT_DELAY_SECONDS} seconds..."
                )
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    finally:
        if batch:
            path = storage.write_batch(batch)
            print(f"Flushed {len(batch)} pending trades to {path}")


if __name__ == "__main__":
    try:
        asyncio.run(stream_trades())
    except KeyboardInterrupt:
        print("\nTrade stream stopped.")
