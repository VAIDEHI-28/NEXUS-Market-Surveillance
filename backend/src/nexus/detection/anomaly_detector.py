
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import median

from nexus.features.market_features import MarketFeatureRecord


@dataclass(frozen=True)
class AnomalyAlert:
    """Explainable alert generated from market-feature observations."""

    symbol: str
    timestamp: datetime
    anomaly_type: str
    severity: str
    score: float
    observed_value: float
    baseline_value: float
    evidence: str


@dataclass(frozen=True)
class DetectorConfig:
    """Configuration for rolling-baseline anomaly detection."""

    baseline_windows: int = 30
    min_baseline_windows: int = 10
    spike_ratio: float = 3.0
    spread_ratio: float = 2.0
    depth_drop_ratio: float = 0.5
    imbalance_change_threshold: float = 0.6

    def __post_init__(self) -> None:
        if self.baseline_windows < 2:
            raise ValueError("baseline_windows must be at least 2")

        if not 2 <= self.min_baseline_windows <= self.baseline_windows:
            raise ValueError(
                "min_baseline_windows must be between 2 and baseline_windows"
            )

        for name in (
            "spike_ratio",
            "spread_ratio",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 1:
                raise ValueError(f"{name} must be finite and greater than 1")

        if (
            not isfinite(self.depth_drop_ratio)
            or not 0 < self.depth_drop_ratio < 1
        ):
            raise ValueError("depth_drop_ratio must be between 0 and 1")

        if (
            not isfinite(self.imbalance_change_threshold)
            or not 0 < self.imbalance_change_threshold <= 2
        ):
            raise ValueError(
                "imbalance_change_threshold must be in (0, 2]"
            )


class MarketAnomalyDetector:
    """
    Detect unusual market conditions against prior observations.

    The current record is compared with historical baseline values before
    it is added to history, avoiding contamination of its own baseline.
    """

    def __init__(
        self,
        config: DetectorConfig | None = None,
    ) -> None:
        self.config = config or DetectorConfig()

        self._history: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: {
                "trade_intensity": deque(
                    maxlen=self.config.baseline_windows
                ),
                "total_volume": deque(
                    maxlen=self.config.baseline_windows
                ),
                "relative_spread": deque(
                    maxlen=self.config.baseline_windows
                ),
                "bid_depth": deque(
                    maxlen=self.config.baseline_windows
                ),
                "ask_depth": deque(
                    maxlen=self.config.baseline_windows
                ),
                "depth_imbalance": deque(
                    maxlen=self.config.baseline_windows
                ),
            }
        )

        self._last_timestamp: dict[str, datetime] = {}

    @staticmethod
    def _severity(score: float) -> str:
        if score >= 5:
            return "critical"
        if score >= 3:
            return "high"
        return "medium"

    def _add_alert(
        self,
        alerts: list[AnomalyAlert],
        record: MarketFeatureRecord,
        anomaly_type: str,
        observed: float,
        baseline: float,
        score: float,
        evidence: str,
    ) -> None:
        alerts.append(
            AnomalyAlert(
                symbol=record.symbol,
                timestamp=record.timestamp,
                anomaly_type=anomaly_type,
                severity=self._severity(score),
                score=round(score, 3),
                observed_value=observed,
                baseline_value=baseline,
                evidence=evidence,
            )
        )

    def process(
        self,
        record: MarketFeatureRecord,
    ) -> list[AnomalyAlert]:
        """Evaluate a record and update its symbol-specific baseline."""
        previous_timestamp = self._last_timestamp.get(record.symbol)

        if (
            previous_timestamp is not None
            and record.timestamp <= previous_timestamp
        ):
            raise ValueError(
                "Records must be processed in strictly increasing timestamp order"
            )

        trades = record.trade_features
        book = record.order_book_features

        observations = {
            "trade_intensity": float(trades.trade_intensity),
            "total_volume": float(trades.total_volume),
            "relative_spread": float(book.relative_spread),
            "bid_depth": float(book.bid_depth),
            "ask_depth": float(book.ask_depth),
            "depth_imbalance": float(book.depth_imbalance),
        }

        for name, value in observations.items():
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")

        history = self._history[record.symbol]
        alerts: list[AnomalyAlert] = []

        def baseline(name: str) -> float | None:
            values = history[name]
            if len(values) < self.config.min_baseline_windows:
                return None
            return float(median(values))

        # 1. Unusual trade intensity.
        for metric_name, anomaly_name in (
            ("trade_intensity", "trade_intensity_spike"),
            ("total_volume", "trade_volume_spike"),
        ):
            observed = observations[metric_name]
            reference = baseline(metric_name)

            if reference is None or reference <= 0:
                continue

            ratio = observed / reference

            if ratio >= self.config.spike_ratio:
                self._add_alert(
                    alerts=alerts,
                    record=record,
                    anomaly_type=anomaly_name,
                    observed=observed,
                    baseline=reference,
                    score=ratio,
                    evidence=(
                        f"{metric_name} is {ratio:.2f}x its rolling "
                        f"median baseline of {reference:.6g}"
                    ),
                )

        # 2. Abnormally wide relative bid-ask spread.
        observed_spread = observations["relative_spread"]
        spread_baseline = baseline("relative_spread")

        if spread_baseline is not None and spread_baseline > 0:
            ratio = observed_spread / spread_baseline

            if ratio >= self.config.spread_ratio:
                self._add_alert(
                    alerts=alerts,
                    record=record,
                    anomaly_type="spread_widening",
                    observed=observed_spread,
                    baseline=spread_baseline,
                    score=ratio,
                    evidence=(
                        f"Relative spread is {ratio:.2f}x its rolling "
                        f"median baseline of {spread_baseline:.6g}"
                    ),
                )

        # 3. Sudden reduction in either side of displayed book depth.
        for metric_name in ("bid_depth", "ask_depth"):
            observed_depth = observations[metric_name]
            depth_baseline = baseline(metric_name)

            if depth_baseline is None or depth_baseline <= 0:
                continue

            ratio = observed_depth / depth_baseline

            if ratio <= self.config.depth_drop_ratio:
                score = depth_baseline / max(
                    observed_depth,
                    1e-12,
                )

                self._add_alert(
                    alerts=alerts,
                    record=record,
                    anomaly_type=f"{metric_name}_drop",
                    observed=observed_depth,
                    baseline=depth_baseline,
                    score=min(score, 100.0),
                    evidence=(
                        f"{metric_name} fell to {ratio:.1%} of its "
                        f"rolling median baseline of {depth_baseline:.6g}"
                    ),
                )

        # 4. Abrupt change in order-book depth imbalance.
        imbalance_baseline = baseline("depth_imbalance")

        if imbalance_baseline is not None:
            observed_imbalance = observations["depth_imbalance"]
            change = abs(observed_imbalance - imbalance_baseline)

            if change >= self.config.imbalance_change_threshold:
                score = change / self.config.imbalance_change_threshold

                self._add_alert(
                    alerts=alerts,
                    record=record,
                    anomaly_type="depth_imbalance_shift",
                    observed=observed_imbalance,
                    baseline=imbalance_baseline,
                    score=score,
                    evidence=(
                        f"Depth imbalance changed by {change:.3f} "
                        f"from rolling median {imbalance_baseline:.3f}"
                    ),
                )

        # Add the current observation only after evaluating all rules.
        for name, value in observations.items():
            history[name].append(value)

        self._last_timestamp[record.symbol] = record.timestamp

        return alerts
