
import asyncio
import json
from collections import deque

import httpx
from websockets.asyncio.client import connect

from nexus.market_data.order_book_builder import OrderBookBuilder


SYMBOL = "BTCUSDT"
REST_URL = "https://api.binance.com/api/v3/depth"
WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@depth"
SNAPSHOT_LIMIT = 1000
QUEUE_SIZE = 10_000
RECONNECT_DELAY = 3


class BinanceOrderBook:
    """Maintain a local order book using Binance REST and depth updates."""

    def __init__(self):
        self.builder = OrderBookBuilder()
        self.events: asyncio.Queue[dict] = asyncio.Queue(
            maxsize=QUEUE_SIZE
        )
        self.buffer: deque[dict] = deque()

        self.queue_overflowed = False
        self.overflow_signal = asyncio.Event()
        self.reader_closed = asyncio.Event()
        self.reader_error: Exception | None = None

    def reset_connection_state(self) -> None:
        """Discard all state from the previous connection."""
        self.builder = OrderBookBuilder()
        self.events = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.buffer.clear()

        self.queue_overflowed = False
        self.overflow_signal = asyncio.Event()
        self.reader_closed = asyncio.Event()
        self.reader_error = None

    async def fetch_snapshot(self) -> dict:
        """Fetch a fresh REST snapshot of the order book."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                REST_URL,
                params={
                    "symbol": SYMBOL,
                    "limit": SNAPSHOT_LIMIT,
                },
            )
            response.raise_for_status()
            return response.json()

    async def receive_events(self, websocket) -> None:
        """Read WebSocket messages using exactly one reader task."""
        try:
            async for message in websocket:
                event = json.loads(message)

                if event.get("e") != "depthUpdate":
                    continue

                try:
                    self.events.put_nowait(event)
                except asyncio.QueueFull:
                    self.queue_overflowed = True
                    self.builder.is_valid = False
                    self.builder.is_synchronized = False
                    self.overflow_signal.set()
                    return

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.reader_error = exc
        finally:
            self.reader_closed.set()

    def ensure_connection_healthy(self) -> None:
        """Reject data from a failed or overflowing connection."""
        if self.queue_overflowed:
            raise RuntimeError(
                "Depth queue overflowed; rebuild the order book"
            )

        if self.reader_closed.is_set():
            if self.reader_error is not None:
                raise RuntimeError(
                    f"WebSocket reader failed: {self.reader_error}"
                ) from self.reader_error

            raise RuntimeError("WebSocket reader has stopped")

    async def next_event(self) -> dict:
        """Wait for an event, while remaining responsive to failures."""
        self.ensure_connection_healthy()

        get_task = asyncio.create_task(self.events.get())
        overflow_task = asyncio.create_task(
            self.overflow_signal.wait()
        )
        closed_task = asyncio.create_task(
            self.reader_closed.wait()
        )

        tasks = {get_task, overflow_task, closed_task}

        try:
            await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            self.ensure_connection_healthy()

            event = get_task.result()
            self.events.task_done()
            return event

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    def apply_buffered_event(self, event: dict) -> None:
        """Apply a depth event during initial synchronization."""
        self.builder.apply_levels(
            self.builder.bids,
            event["b"],
        )
        self.builder.apply_levels(
            self.builder.asks,
            event["a"],
        )
        self.builder.last_update_id = int(event["u"])

    async def synchronize(self) -> None:
        """
        Synchronize a REST snapshot with buffered WebSocket events.

        Retry with a fresh snapshot if the bridge is missing or a
        sequence gap is detected.
        """
        while True:
            self.ensure_connection_healthy()

            snapshot = await self.fetch_snapshot()
            snapshot_id = int(snapshot["lastUpdateId"])

            self.builder.load_snapshot(
                last_update_id=snapshot_id,
                bids=snapshot["bids"],
                asks=snapshot["asks"],
            )

            # Move queued events into the synchronization buffer.
            while True:
                self.ensure_connection_healthy()

                try:
                    event = self.events.get_nowait()
                    self.events.task_done()
                    self.buffer.append(event)
                except asyncio.QueueEmpty:
                    break

            # Discard events already represented by the snapshot.
            while (
                self.buffer
                and int(self.buffer[0]["u"]) <= snapshot_id
            ):
                self.buffer.popleft()

            # Find the event that bridges the snapshot update ID.
            retry_snapshot = False

            while True:
                self.ensure_connection_healthy()

                if not self.buffer:
                    self.buffer.append(await self.next_event())

                event = self.buffer[0]
                first_id = int(event["U"])
                final_id = int(event["u"])

                if final_id <= snapshot_id:
                    self.buffer.popleft()
                    continue

                if first_id > snapshot_id + 1:
                    # The snapshot is too old for this event.
                    # Keep the event and obtain another snapshot.
                    retry_snapshot = True
                    break

                if final_id < snapshot_id + 1:
                    self.buffer.popleft()
                    continue

                # The event bridges snapshot_id + 1.
                break

            if retry_snapshot:
                await asyncio.sleep(0)
                continue

            # Apply the bridge and all currently buffered events
            # in sequence. Leave later arrivals in the queue.
            sequence_gap = False

            while self.buffer:
                self.ensure_connection_healthy()

                event = self.buffer[0]
                first_id = int(event["U"])
                final_id = int(event["u"])
                current_id = self.builder.last_update_id

                if current_id is None:
                    sequence_gap = True
                    break

                if final_id <= current_id:
                    self.buffer.popleft()
                    continue

                if first_id > current_id + 1:
                    sequence_gap = True
                    break

                self.apply_buffered_event(event)
                self.buffer.popleft()

            if sequence_gap:
                self.builder.is_valid = False
                self.builder.is_synchronized = False
                self.buffer.clear()
                await asyncio.sleep(0)
                continue

            self.ensure_connection_healthy()

            self.builder.is_synchronized = True
            return

    async def process_events(self) -> None:
        """Process live events until a gap or connection failure."""
        while True:
            event = await self.next_event()

            applied = self.builder.apply_depth_event(
                first_update_id=int(event["U"]),
                final_update_id=int(event["u"]),
                bids=event["b"],
                asks=event["a"],
            )

            if not applied and not self.builder.is_valid:
                self.builder.is_synchronized = False
                raise RuntimeError(
                    "Depth sequence gap detected; resynchronization required"
                )

            if applied:
                print(
                    f"update_id={self.builder.last_update_id} "
                    f"best_bid={self.builder.best_bid()} "
                    f"best_ask={self.builder.best_ask()}"
                )

    async def run(self) -> None:
        """Reconnect and rebuild the order book after failures."""
        while True:
            self.reset_connection_state()

            try:
                async with connect(WS_URL) as websocket:
                    reader = asyncio.create_task(
                        self.receive_events(websocket)
                    )

                    try:
                        await self.synchronize()
                        print(
                            "Order book synchronized. "
                            f"last_update_id={self.builder.last_update_id}"
                        )

                        await self.process_events()

                    finally:
                        reader.cancel()
                        await asyncio.gather(
                            reader,
                            return_exceptions=True,
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.builder.is_valid = False
                self.builder.is_synchronized = False
                print(f"Order-book error: {exc}")

            print(
                f"Reconnecting and resynchronizing in "
                f"{RECONNECT_DELAY} seconds..."
            )
            await asyncio.sleep(RECONNECT_DELAY)


async def main():
    await BinanceOrderBook().run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOrder-book collector stopped.")
