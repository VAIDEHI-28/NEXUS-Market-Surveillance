
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from nexus.detection.anomaly_detector import AnomalyAlert
import pytest

from nexus.features.live_market_pipeline import LiveMarketPipeline
from nexus.market_data.order_book_builder import OrderBookBuilder
from nexus.schemas.trade import TradeEvent


@pytest.fixture
def base_time():
    return datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


def make_trade(event_time, trade_id=1):
    return TradeEvent(
        symbol="BTCUSDT",
        price=60000.0,
        quantity=0.1,
        trade_id=trade_id,
        event_time=event_time,
        buyer_is_maker=False,
    )


def make_fresh_order_book(base_time):
    book = OrderBookBuilder()
    book.load_snapshot(
        last_update_id=100,
        bids=[["60000", "2.0"], ["59999", "3.0"]],
        asks=[["60001", "1.5"], ["60002", "2.5"]],
    )
    book.is_synchronized = True
    book.last_received_at = base_time + timedelta(seconds=4)
    book.last_event_time = base_time + timedelta(seconds=4)
    return book


@pytest.mark.asyncio
async def test_on_trade_queues_matching_symbol(base_time):
    pipeline = LiveMarketPipeline(
        order_book_collector=MagicMock(),
        trade_stream_fn=AsyncMock(),
    )

    trade = make_trade(base_time + timedelta(seconds=1))

    await pipeline.on_trade(trade)

    assert pipeline._trade_queue.qsize() == 1
    assert await pipeline._trade_queue.get() == trade


@pytest.mark.asyncio
async def test_on_trade_ignores_other_symbols(base_time):
    pipeline = LiveMarketPipeline(
        order_book_collector=MagicMock(),
        trade_stream_fn=AsyncMock(),
        symbol="BTCUSDT",
    )

    other_trade = TradeEvent(
        symbol="ETHUSDT",
        price=3000.0,
        quantity=0.2,
        trade_id=2,
        event_time=base_time + timedelta(seconds=1),
        buyer_is_maker=False,
    )

    await pipeline.on_trade(other_trade)

    assert pipeline._trade_queue.empty()


@pytest.mark.asyncio
async def test_feature_processing_skips_stale_order_book(base_time):
    book = make_fresh_order_book(base_time)
    book.last_received_at = base_time - timedelta(seconds=10)

    collector = MagicMock()
    collector.builder = book

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1))
    )

    # Use the test clock by replacing the pipeline module's datetime.
    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return base_time + timedelta(seconds=7)

    from nexus.features import live_market_pipeline

    original_datetime = live_market_pipeline.datetime
    live_market_pipeline.datetime = FixedDateTime

    task = asyncio.create_task(
        pipeline._process_completed_windows()
    )

    try:
        await asyncio.sleep(0.05)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        live_market_pipeline.datetime = original_datetime

    assert pipeline.records_emitted == 0
    assert pipeline.windows_skipped >= 1

@pytest.mark.asyncio
async def test_stop_cleans_up_pipeline_tasks():
    started = asyncio.Event()
    cleanup = {"order_book": False, "trades": False}

    class FakeOrderBook:
        builder = MagicMock()

        async def run(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup["order_book"] = True

    async def fake_trade_stream(on_trade):
        try:
            await asyncio.Event().wait()
        finally:
            cleanup["trades"] = True

    pipeline = LiveMarketPipeline(
        order_book_collector=FakeOrderBook(),
        trade_stream_fn=fake_trade_stream,
        watermark_interval_seconds=0.01,
    )

    run_task = asyncio.create_task(pipeline.run())

    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        await pipeline.stop()
        await asyncio.wait_for(run_task, timeout=1)
    finally:
        if not run_task.done():
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

    assert cleanup["order_book"] is True
    assert cleanup["trades"] is True

@pytest.mark.asyncio
async def test_completed_window_emits_market_features(base_time):
    from datetime import timedelta

    from nexus.features.market_feature_pipeline import (
        build_completed_window_features,
    )

    book = make_fresh_order_book(base_time)
    collector = MagicMock()
    collector.builder = book

    window_start = base_time
    window_end = base_time + timedelta(seconds=5)
    book.last_received_at = window_end
    book.last_event_time = window_end

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        symbol="BTCUSDT",
    )

    trade = make_trade(
        base_time + timedelta(seconds=1),
        trade_id=101,
    )

    record = build_completed_window_features(
        window=(window_start, window_end, [trade]),
        order_book=book,
        symbol="BTCUSDT",
        max_order_book_age_seconds=5.0,
        now=window_end,
    )

    await pipeline._emit_feature(record)

    assert record.symbol == "BTCUSDT"
    assert record.timestamp == window_end
    assert record.trade_window_start == window_start
    assert record.trade_window_end == window_end

@pytest.mark.asyncio
async def test_processor_emits_completed_window(base_time, monkeypatch):
    from datetime import timedelta

    import nexus.features.live_market_pipeline as live_module

    window_end = base_time + timedelta(seconds=5)
    book = make_fresh_order_book(base_time)
    book.last_received_at = window_end
    book.last_event_time = window_end

    collector = MagicMock()
    collector.builder = book

    emitted = []
    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        on_feature=emitted.append,
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1), trade_id=102)
    )

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return window_end + timedelta(
                seconds=pipeline.allowed_lateness_seconds
            )

    monkeypatch.setattr(live_module, "datetime", FixedDateTime)

    task = asyncio.create_task(pipeline._process_completed_windows())

    try:
        for _ in range(100):
            if pipeline.records_emitted or pipeline.windows_skipped:
                break
            await asyncio.sleep(0.01)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert pipeline.records_emitted == 1
    assert len(emitted) == 1
    assert emitted[0].symbol == "BTCUSDT"
    assert emitted[0].trade_window_end == window_end

@pytest.mark.asyncio
async def test_processor_passes_each_emitted_record_to_detector(
    base_time, monkeypatch
):
    import nexus.features.live_market_pipeline as live_module

    window_end = base_time + timedelta(seconds=5)
    book = make_fresh_order_book(base_time)
    book.last_received_at = window_end
    book.last_event_time = window_end

    collector = MagicMock()
    collector.builder = book

    class FakeDetector:
        def __init__(self):
            self.records = []

        def process(self, record):
            self.records.append(record)
            return []

    detector = FakeDetector()

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        anomaly_detector=detector,
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1), trade_id=201)
    )

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return window_end + timedelta(
                seconds=pipeline.allowed_lateness_seconds
            )

    monkeypatch.setattr(live_module, "datetime", FixedDateTime)

    task = asyncio.create_task(pipeline._process_completed_windows())

    try:
        for _ in range(100):
            if pipeline.records_emitted or pipeline.windows_skipped:
                break
            await asyncio.sleep(0.01)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert pipeline.records_emitted == 1
    assert len(detector.records) == 1
    assert detector.records[0].symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_processor_emits_alerts_to_sync_callback(
    base_time, monkeypatch
):
    import nexus.features.live_market_pipeline as live_module

    window_end = base_time + timedelta(seconds=5)
    book = make_fresh_order_book(base_time)
    book.last_received_at = window_end
    book.last_event_time = window_end

    collector = MagicMock()
    collector.builder = book
    received_alerts = []

    expected_alert = AnomalyAlert(
        symbol="BTCUSDT",
        timestamp=window_end,
        anomaly_type="trade_intensity_spike",
        severity="high",
        score=4.0,
        observed_value=40.0,
        baseline_value=10.0,
        evidence="Trade intensity is 4x its baseline",
    )

    class FakeDetector:
        def process(self, record):
            return [expected_alert]

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        anomaly_detector=FakeDetector(),
        on_alert=received_alerts.append,
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1), trade_id=202)
    )

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return window_end + timedelta(
                seconds=pipeline.allowed_lateness_seconds
            )

    monkeypatch.setattr(live_module, "datetime", FixedDateTime)

    task = asyncio.create_task(pipeline._process_completed_windows())

    try:
        for _ in range(100):
            if received_alerts or pipeline.windows_skipped:
                break
            await asyncio.sleep(0.01)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert received_alerts == [expected_alert]
    assert pipeline.alerts_emitted == 1


@pytest.mark.asyncio
async def test_processor_supports_async_alert_callback(
    base_time, monkeypatch
):
    import nexus.features.live_market_pipeline as live_module

    window_end = base_time + timedelta(seconds=5)
    book = make_fresh_order_book(base_time)
    book.last_received_at = window_end
    book.last_event_time = window_end

    collector = MagicMock()
    collector.builder = book
    received_alerts = []

    expected_alert = AnomalyAlert(
        symbol="BTCUSDT",
        timestamp=window_end,
        anomaly_type="spread_widening",
        severity="medium",
        score=2.5,
        observed_value=0.0025,
        baseline_value=0.001,
        evidence="Relative spread widened",
    )

    class FakeDetector:
        def process(self, record):
            return [expected_alert]

    async def on_alert(alert):
        await asyncio.sleep(0)
        received_alerts.append(alert)

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        anomaly_detector=FakeDetector(),
        on_alert=on_alert,
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1), trade_id=203)
    )

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return window_end + timedelta(
                seconds=pipeline.allowed_lateness_seconds
            )

    monkeypatch.setattr(live_module, "datetime", FixedDateTime)

    task = asyncio.create_task(pipeline._process_completed_windows())

    try:
        for _ in range(100):
            if received_alerts or pipeline.windows_skipped:
                break
            await asyncio.sleep(0.01)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert received_alerts == [expected_alert]
    assert pipeline.alerts_emitted == 1


@pytest.mark.asyncio
async def test_alert_callback_failure_does_not_crash_processing(
    base_time, monkeypatch
):
    import nexus.features.live_market_pipeline as live_module

    window_end = base_time + timedelta(seconds=5)
    book = make_fresh_order_book(base_time)
    book.last_received_at = window_end
    book.last_event_time = window_end

    collector = MagicMock()
    collector.builder = book

    alerts = [
        AnomalyAlert(
            symbol="BTCUSDT",
            timestamp=window_end,
            anomaly_type="trade_intensity_spike",
            severity="high",
            score=4.0,
            observed_value=40.0,
            baseline_value=10.0,
            evidence="Trade intensity spike",
        ),
        AnomalyAlert(
            symbol="BTCUSDT",
            timestamp=window_end,
            anomaly_type="spread_widening",
            severity="medium",
            score=2.5,
            observed_value=0.0025,
            baseline_value=0.001,
            evidence="Spread widening",
        ),
    ]

    class FakeDetector:
        def process(self, record):
            return alerts

    attempted = []

    def failing_callback(alert):
        attempted.append(alert)
        raise RuntimeError("Simulated callback failure")

    pipeline = LiveMarketPipeline(
        order_book_collector=collector,
        trade_stream_fn=AsyncMock(),
        anomaly_detector=FakeDetector(),
        on_alert=failing_callback,
        watermark_interval_seconds=0.01,
    )

    await pipeline.on_trade(
        make_trade(base_time + timedelta(seconds=1), trade_id=204)
    )

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return window_end + timedelta(
                seconds=pipeline.allowed_lateness_seconds
            )

    monkeypatch.setattr(live_module, "datetime", FixedDateTime)

    task = asyncio.create_task(pipeline._process_completed_windows())

    try:
        for _ in range(100):
            if pipeline.alert_callback_errors >= len(alerts):
                break
            await asyncio.sleep(0.01)
    finally:
        pipeline._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert attempted == alerts
    assert pipeline.alert_callback_errors == 2
    assert pipeline.records_emitted == 1
