
import asyncio

import pytest

from nexus.market_data.binance_order_book import BinanceOrderBook


@pytest.mark.asyncio
async def test_snapshot_is_bridged_by_first_depth_event():
    book = BinanceOrderBook()

    async def fake_snapshot():
        return {
            "lastUpdateId": 100,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        }

    book.fetch_snapshot = fake_snapshot
    book.buffer.append({
        "U": 101,
        "u": 102,
        "b": [["100.0", "2.0"]],
        "a": [],
    })

    await book.synchronize()

    assert book.builder.is_valid is True
    assert book.builder.is_synchronized is True
    assert book.builder.last_update_id == 102


@pytest.mark.asyncio
async def test_snapshot_discards_obsolete_buffered_events():
    book = BinanceOrderBook()

    async def fake_snapshot():
        return {
            "lastUpdateId": 105,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        }

    book.fetch_snapshot = fake_snapshot
    book.buffer.extend([
        {"U": 101, "u": 103, "b": [["100.0", "9.0"]], "a": []},
        {"U": 106, "u": 107, "b": [["100.0", "2.0"]], "a": []},
    ])

    await book.synchronize()

    assert book.builder.is_synchronized is True
    assert book.builder.last_update_id == 107


@pytest.mark.asyncio
async def test_snapshot_bridge_applies_ask_updates():
    book = BinanceOrderBook()

    async def fake_snapshot():
        return {
            "lastUpdateId": 200,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        }

    book.fetch_snapshot = fake_snapshot
    book.buffer.append({
        "U": 201,
        "u": 201,
        "b": [],
        "a": [["101.0", "0"]],
    })

    await book.synchronize()

    assert book.builder.is_synchronized is True
    assert book.builder.best_ask() is None


@pytest.mark.asyncio
async def test_queue_overflow_invalidates_order_book():
    book = BinanceOrderBook()

    book.builder.is_valid = True
    book.builder.is_synchronized = True

    book.events = asyncio.Queue(maxsize=1)
    book.events.put_nowait({"e": "depthUpdate"})

    class FakeWebSocket:
        def __aiter__(self):
            self.messages = iter([
                '{"e":"depthUpdate","U":101,"u":102,"b":[],"a":[]}'
            ])
            return self

        async def __anext__(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise StopAsyncIteration

    await book.receive_events(FakeWebSocket())

    assert book.queue_overflowed is True
    assert book.builder.is_valid is False
    assert book.builder.is_synchronized is False


@pytest.mark.asyncio
async def test_next_event_wakes_when_queue_overflows():
    book = BinanceOrderBook()

    waiting_task = asyncio.create_task(book.next_event())
    await asyncio.sleep(0)

    book.queue_overflowed = True
    book.builder.is_valid = False
    book.builder.is_synchronized = False
    book.overflow_signal.set()

    with pytest.raises(RuntimeError, match="overflowed"):
        await asyncio.wait_for(waiting_task, timeout=1.0)


@pytest.mark.asyncio
async def test_next_event_fails_when_reader_closes():
    book = BinanceOrderBook()
    book.reader_closed.set()

    with pytest.raises(RuntimeError, match="stopped"):
        await book.next_event()


@pytest.mark.asyncio
async def test_sequence_gap_invalidates_order_book():
    book = BinanceOrderBook()

    book.builder.load_snapshot(
        last_update_id=100,
        bids=[["100.0", "1.0"]],
        asks=[["101.0", "1.0"]],
    )
    book.builder.is_synchronized = True

    book.events.put_nowait({
        "e": "depthUpdate",
        "U": 102,
        "u": 103,
        "b": [["100.0", "2.0"]],
        "a": [],
    })

    with pytest.raises(RuntimeError, match="sequence gap"):
        await book.process_events()

    assert book.builder.is_valid is False
    assert book.builder.is_synchronized is False


@pytest.mark.asyncio
async def test_synchronize_recovers_with_fresh_snapshot():
    book = BinanceOrderBook()

    snapshots = [
        {
            "lastUpdateId": 100,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        },
        {
            "lastUpdateId": 105,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        },
    ]

    async def fake_snapshot():
        if snapshots:
            return snapshots.pop(0)
        raise AssertionError("Unexpected extra snapshot request")

    book.fetch_snapshot = fake_snapshot

    book.buffer.extend([
        {"U": 103, "u": 104, "b": [], "a": []},
        {"U": 106, "u": 107, "b": [["100.0", "2.0"]], "a": []},
    ])

    await book.synchronize()

    assert book.builder.is_valid is True
    assert book.builder.is_synchronized is True
    assert book.builder.last_update_id == 107
    assert str(book.builder.best_bid()[1]) == "2.0"


@pytest.mark.asyncio
async def test_synchronize_does_not_accept_gap_after_bridge():
    book = BinanceOrderBook()

    snapshot_calls = 0

    async def fake_snapshot():
        nonlocal snapshot_calls
        snapshot_calls += 1

        if snapshot_calls > 1:
            raise AssertionError("Unexpected additional snapshot request")

        return {
            "lastUpdateId": 100,
            "bids": [["100.0", "1.0"]],
            "asks": [["101.0", "1.0"]],
        }

    book.fetch_snapshot = fake_snapshot

    book.buffer.extend([
        {
            "U": 101,
            "u": 102,
            "b": [["100.0", "2.0"]],
            "a": [],
        },
        {
            "U": 104,
            "u": 105,
            "b": [["100.0", "3.0"]],
            "a": [],
        },
    ])

    with pytest.raises(AssertionError, match="Unexpected"):
        await book.synchronize()
