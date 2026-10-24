
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from nexus.detection.alert_store import AlertStore
from nexus.features.live_market_pipeline import LiveMarketPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application services and clean them up on shutdown."""
    max_alerts = int(os.getenv("NEXUS_MAX_ALERTS", "1000"))
    alert_store = AlertStore(max_alerts=max_alerts)

    pipeline = LiveMarketPipeline(
        symbol=os.getenv("NEXUS_SYMBOL", "BTCUSDT"),
        on_alert=alert_store.add,
    )

    app.state.alert_store = alert_store
    app.state.pipeline = pipeline
    app.state.pipeline_error = None

    pipeline_task = asyncio.create_task(
        pipeline.run(),
        name="nexus-live-market-pipeline",
    )
    app.state.pipeline_task = pipeline_task

    def record_pipeline_result(task: asyncio.Task) -> None:
        if task.cancelled():
            app.state.pipeline_error = "Pipeline task was cancelled"
            return

        error = task.exception()
        if error is not None:
            app.state.pipeline_error = f"{type(error).__name__}: {error}"

    pipeline_task.add_done_callback(record_pipeline_result)

    try:
        yield
    finally:
        await pipeline.stop()

        try:
            await asyncio.wait_for(pipeline_task, timeout=5.0)
        except asyncio.TimeoutError:
            pipeline_task.cancel()
            await asyncio.gather(
                pipeline_task,
                return_exceptions=True,
            )
        except Exception:
            # Pipeline errors are also exposed through /status.
            pass


app = FastAPI(
    title="NEXUS Market Surveillance Engine",
    description="An explainable engine for detecting market anomalies.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Report whether the API process is responsive."""
    return {
        "status": "healthy",
        "service": "nexus-backend",
        "version": "0.1.0",
    }


@app.get("/status", tags=["Health"])
async def pipeline_status():
    """Report live pipeline state and processing counters."""
    pipeline = getattr(app.state, "pipeline", None)
    task = getattr(app.state, "pipeline_task", None)
    error = getattr(app.state, "pipeline_error", None)

    if pipeline is None or task is None:
        state = "not_started"
    elif error:
        state = "failed"
    elif task.done():
        state = "stopped"
    else:
        state = "running"

    return {
        "service": "nexus-backend",
        "pipeline": {
            "state": state,
            "symbol": pipeline.symbol if pipeline else None,
            "records_emitted": (
                pipeline.records_emitted if pipeline else 0
            ),
            "windows_skipped": (
                pipeline.windows_skipped if pipeline else 0
            ),
            "alerts_emitted": (
                pipeline.alerts_emitted if pipeline else 0
            ),
            "detection_errors": (
                pipeline.detection_errors if pipeline else 0
            ),
            "alert_callback_errors": (
                pipeline.alert_callback_errors if pipeline else 0
            ),
            "queued_trades": (
                pipeline._trade_queue.qsize() if pipeline else 0
            ),
            "error": error,
        },
    }


@app.get("/alerts", tags=["Surveillance"])
async def get_alerts(
    symbol: str | None = Query(default=None, min_length=1),
    severity: str | None = Query(default=None),
    anomaly_type: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Return recent anomaly alerts, optionally filtered."""
    store: AlertStore | None = getattr(
        app.state, "alert_store", None
    )

    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Alert store is not initialized",
        )

    if symbol is not None:
        symbol = symbol.strip().upper()
        if not symbol:
            raise HTTPException(
                status_code=422,
                detail="symbol must not be empty",
            )

    if severity is not None:
        severity = severity.strip().lower()
        if severity not in {"medium", "high", "critical"}:
            raise HTTPException(
                status_code=422,
                detail="severity must be one of: medium, high, critical",
            )

    if anomaly_type is not None:
        anomaly_type = anomaly_type.strip()
        if not anomaly_type:
            raise HTTPException(
                status_code=422,
                detail="anomaly_type must not be empty",
            )

    alerts = store.get_alerts(
        symbol=symbol,
        severity=severity,
        anomaly_type=anomaly_type,
        limit=limit,
    )

    return {
        "count": len(alerts),
        "alerts": [
            {
                "symbol": alert.symbol,
                "timestamp": alert.timestamp.isoformat(),
                "anomaly_type": alert.anomaly_type,
                "severity": alert.severity,
                "score": alert.score,
                "observed_value": alert.observed_value,
                "baseline_value": alert.baseline_value,
                "evidence": alert.evidence,
            }
            for alert in alerts
        ],
    }
