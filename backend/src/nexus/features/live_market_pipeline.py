
import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from nexus.detection.anomaly_detector import (
    AnomalyAlert,
    MarketAnomalyDetector,
)
from nexus.features.market_feature_pipeline import (
    TradeWindowBuffer,
    build_completed_window_features,
)
from nexus.features.market_features import MarketFeatureRecord
from nexus.market_data.binance_order_book import BinanceOrderBook
from nexus.schemas.trade import TradeEvent
from nexus.trade_stream import stream_trades


FeatureCallback = Callable[
    [MarketFeatureRecord],
    Awaitable[None] | None,
]

AlertCallback = Callable[
    [AnomalyAlert],
    Awaitable[None] | None,
]


class LiveMarketPipeline:
    """Coordinate live trades, order-book updates, features, and alerts."""

    def __init__(
        self,
        order_book_collector: BinanceOrderBook | None = None,
        trade_stream_fn: Callable[..., Awaitable[None]] = stream_trades,
        on_feature: FeatureCallback | None = None,
        on_alert: AlertCallback | None = None,
        anomaly_detector: MarketAnomalyDetector | None = None,
        symbol: str = "BTCUSDT",
        window_seconds: float = 5.0,
        allowed_lateness_seconds: float = 2.0,
        max_order_book_age_seconds: float = 5.0,
        watermark_interval_seconds: float = 0.25,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must not be empty")

        if (
            not isinstance(watermark_interval_seconds, (int, float))
            or isinstance(watermark_interval_seconds, bool)
            or watermark_interval_seconds <= 0
            or not float(watermark_interval_seconds) < float("inf")
        ):
            raise ValueError(
                "watermark_interval_seconds must be positive and finite"
            )

        if (
            not isinstance(allowed_lateness_seconds, (int, float))
            or isinstance(allowed_lateness_seconds, bool)
            or not 0 <= allowed_lateness_seconds < float("inf")
        ):
            raise ValueError(
                "allowed_lateness_seconds must be non-negative and finite"
            )

        self.order_book_collector = (
            order_book_collector or BinanceOrderBook()
        )
        self.trade_stream_fn = trade_stream_fn
        self.on_feature = on_feature
        self.on_alert = on_alert
        self.anomaly_detector = (
            anomaly_detector or MarketAnomalyDetector()
        )
        self.symbol = symbol
        self.max_order_book_age_seconds = (
            max_order_book_age_seconds
        )
        self.watermark_interval_seconds = (
            watermark_interval_seconds
        )
        self.allowed_lateness_seconds = float(
            allowed_lateness_seconds
        )

        self.window_buffer = TradeWindowBuffer(
            window_seconds=window_seconds,
            allowed_lateness_seconds=allowed_lateness_seconds,
        )

        self._trade_queue: asyncio.Queue[TradeEvent] = asyncio.Queue()
        self._stop_event = asyncio.Event()

        self.records_emitted = 0
        self.windows_skipped = 0
        self.alerts_emitted = 0
        self.detection_errors = 0
        self.alert_callback_errors = 0

    async def on_trade(self, trade: TradeEvent) -> None:
        """Queue a matching-symbol trade for asynchronous processing."""
        if trade.symbol != self.symbol:
            return

        await self._trade_queue.put(trade)

    async def _emit_feature(
        self,
        record: MarketFeatureRecord,
    ) -> None:
        """Deliver a generated feature record to the optional consumer."""
        if self.on_feature is None:
            return

        result = self.on_feature(record)

        if inspect.isawaitable(result):
            await result

    async def _emit_alert(self, alert: AnomalyAlert) -> None:
        """Deliver an anomaly alert to the optional consumer."""
        if self.on_alert is None:
            return

        result = self.on_alert(alert)

        if inspect.isawaitable(result):
            await result

    async def _process_completed_windows(self) -> None:
        """Consume trades, emit completed features, and detect anomalies."""
        while not self._stop_event.is_set():
            try:
                trade = await asyncio.wait_for(
                    self._trade_queue.get(),
                    timeout=self.watermark_interval_seconds,
                )
            except asyncio.TimeoutError:
                trade = None

            if trade is not None:
                try:
                    self.window_buffer.add_trade(trade)
                finally:
                    self._trade_queue.task_done()

                # Process trades already queued before advancing the watermark.
                while True:
                    try:
                        queued_trade = self._trade_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        self.window_buffer.add_trade(queued_trade)
                    finally:
                        self._trade_queue.task_done()

            # Practical wall-clock grace period; assumes local and exchange
            # clocks are reasonably aligned.
            watermark = datetime.now(timezone.utc) - timedelta(
                seconds=self.allowed_lateness_seconds
            )

            try:
                completed = self.window_buffer.advance_watermark(
                    watermark
                )
            except ValueError as exc:
                print(f"Watermark error: {exc}")
                continue

            for window in completed:
                try:
                    record = build_completed_window_features(
                        window=window,
                        order_book=self.order_book_collector.builder,
                        symbol=self.symbol,
                        max_order_book_age_seconds=(
                            self.max_order_book_age_seconds
                        ),
                        now=watermark,
                    )
                except (ValueError, TypeError) as exc:
                    self.windows_skipped += 1
                    print(
                        "Skipping completed market window: "
                        f"{exc}"
                    )
                    continue

                # Preserve the existing feature callback behavior.
                try:
                    await self._emit_feature(record)
                except Exception as exc:
                    print(f"Feature callback error: {exc}")
                    continue

                self.records_emitted += 1

                # Detection errors should not terminate feature processing.
                try:
                    alerts = self.anomaly_detector.process(record)
                except Exception as exc:
                    self.detection_errors += 1
                    print(f"Anomaly detection error: {exc}")
                    continue

                # Deliver every generated alert independently so one failed
                # callback does not prevent the remaining alerts being sent.
                for alert in alerts:
                    try:
                        await self._emit_alert(alert)
                    except Exception as exc:
                        self.alert_callback_errors += 1
                        print(f"Alert callback error: {exc}")
                    else:
                        # Count alerts only when no callback error occurred.
                        # If no callback is configured, count generated alerts
                        # as emitted to the in-process pipeline.
                        self.alerts_emitted += 1

    async def run(self) -> None:
        """Run collectors until stopped or a pipeline task exits."""
        if self._stop_event.is_set():
            self._stop_event.clear()

        service_tasks = {
            asyncio.create_task(
                self.order_book_collector.run(),
                name="nexus-order-book",
            ),
            asyncio.create_task(
                self.trade_stream_fn(on_trade=self.on_trade),
                name="nexus-trade-stream",
            ),
            asyncio.create_task(
                self._process_completed_windows(),
                name="nexus-feature-processing",
            ),
        }

        stop_task = asyncio.create_task(
            self._stop_event.wait(),
            name="nexus-stop-waiter",
        )
        all_tasks = service_tasks | {stop_task}

        try:
            done, _ = await asyncio.wait(
                all_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # An explicit stop request is normal.
            if stop_task in done and self._stop_event.is_set():
                return

            # A service task exiting first is unexpected.
            for task in done:
                if task is stop_task:
                    continue

                if task.cancelled():
                    raise RuntimeError(
                        "Pipeline task was cancelled unexpectedly: "
                        f"{task.get_name()}"
                    )

                error = task.exception()
                if error is not None:
                    raise error

                raise RuntimeError(
                    "Pipeline task stopped unexpectedly: "
                    f"{task.get_name()}"
                )
        finally:
            self._stop_event.set()

            for task in all_tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *all_tasks,
                return_exceptions=True,
            )

    async def stop(self) -> None:
        """Request pipeline shutdown."""
        self._stop_event.set()
