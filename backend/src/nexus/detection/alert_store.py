
from collections import deque
from threading import Lock

from nexus.detection.anomaly_detector import AnomalyAlert


class AlertStore:
    """Thread-safe, bounded in-memory store for anomaly alerts."""

    def __init__(self, max_alerts: int = 1000) -> None:
        if (
            not isinstance(max_alerts, int)
            or isinstance(max_alerts, bool)
            or max_alerts < 1
        ):
            raise ValueError("max_alerts must be a positive integer")

        self._alerts: deque[AnomalyAlert] = deque(maxlen=max_alerts)
        self._lock = Lock()

    def add(self, alert: AnomalyAlert) -> None:
        """Store an alert, dropping the oldest when capacity is reached."""
        with self._lock:
            self._alerts.append(alert)

    def get_alerts(
        self,
        *,
        symbol: str | None = None,
        severity: str | None = None,
        anomaly_type: str | None = None,
        limit: int = 100,
    ) -> list[AnomalyAlert]:
        """Return newest matching alerts first."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        with self._lock:
            alerts = list(reversed(self._alerts))

        if symbol is not None:
            alerts = [a for a in alerts if a.symbol == symbol.upper()]

        if severity is not None:
            alerts = [a for a in alerts if a.severity == severity]

        if anomaly_type is not None:
            alerts = [
                a for a in alerts
                if a.anomaly_type == anomaly_type
            ]

        return alerts[:limit]

    def count(self) -> int:
        """Return the number of alerts currently retained."""
        with self._lock:
            return len(self._alerts)
