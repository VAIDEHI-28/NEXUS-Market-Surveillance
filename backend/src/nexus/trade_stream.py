
import asyncio
import json
from datetime import datetime, timezone

from websockets.asyncio.client import connect

from nexus.schemas.trade import TradeEvent
from nexus.storage.trades import TradeStorage


BINANCE_TRADE_STREAM = "wss://stream.binance.com:9443/ws/btcusdt@trade"
BATCH_SIZE = 100
FLUSH_INTERVAL_SECONDS = 5


async def stream_trades():
    storage = TradeStorage()
    batch: list[TradeEvent] = []
    last_flush = asyncio.get_running_loop().time()

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

                        batch.append(trade)

                        now = asyncio.get_running_loop().time()

                        if (
                            len(batch) >= BATCH_SIZE
                            or now - last_flush >= FLUSH_INTERVAL_SECONDS
                        ):
                            path = storage.write_batch(batch)

                            if path is not None:
                                print(f"Saved {len(batch)} trades to {path}")
                                batch.clear()
                                last_flush = now

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Stream error: {exc}")
                print("Retrying in 5 seconds...")
                await asyncio.sleep(5)

    finally:
        if batch:
            path = storage.write_batch(batch)
            print(f"Flushed {len(batch)} pending trades to {path}")


if __name__ == "__main__":
    try:
        asyncio.run(stream_trades())
    except KeyboardInterrupt:
        print("\nTrade stream stopped.")
