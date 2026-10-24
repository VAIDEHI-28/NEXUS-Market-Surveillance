
from datetime import datetime, timezone

import pytest

from nexus.detection.alert_store import AlertStore
from nexus.detection.anomaly_detector import AnomalyAlert


@pytest.fixture
def make_alert():
    def factory(
        anomaly_type="trade_intensity_spike",
        severity="high",
        symbol="BTCUSDT",
    ):
        return AnomalyAlert(
            symbol=symbol,
            timestamp=datetime(2026, 10, 24, tzinfo=timezone.utc),
            anomaly_type=anomaly_type,
            severity=severity,
            score=4.0,
            observed_value=40.0,
            baseline_value=10.0,
            evidence="Observed value is 4x the baseline",
        )

    return factory


def test_store_adds_and_retrieves_alerts(make_alert):
    store = AlertStore()
    alert = make_alert()

    store.add(alert)

    assert store.count() == 1
    assert store.get_alerts() == [alert]


def test_newest_alerts_are_returned_first(make_alert):
    store = AlertStore()
    first = make_alert(anomaly_type="first")
    second = make_alert(anomaly_type="second")

    store.add(first)
    store.add(second)

    assert store.get_alerts() == [second, first]


def test_store_filters_by_symbol(make_alert):
    store = AlertStore()
    store.add(make_alert(symbol="BTCUSDT"))
    store.add(make_alert(symbol="ETHUSDT"))

    results = store.get_alerts(symbol="btcusdt")

    assert len(results) == 1
    assert results[0].symbol == "BTCUSDT"


def test_store_filters_by_severity(make_alert):
    store = AlertStore()
    store.add(make_alert(severity="high"))
    store.add(make_alert(severity="critical"))

    results = store.get_alerts(severity="critical")

    assert len(results) == 1
    assert results[0].severity == "critical"


def test_store_filters_by_anomaly_type(make_alert):
    store = AlertStore()
    store.add(make_alert(anomaly_type="spread_widening"))
    store.add(make_alert(anomaly_type="trade_volume_spike"))

    results = store.get_alerts(anomaly_type="spread_widening")

    assert len(results) == 1
    assert results[0].anomaly_type == "spread_widening"


def test_store_enforces_capacity(make_alert):
    store = AlertStore(max_alerts=2)
    alerts = [
        make_alert(anomaly_type="first"),
        make_alert(anomaly_type="second"),
        make_alert(anomaly_type="third"),
    ]

    for alert in alerts:
        store.add(alert)

    assert store.count() == 2
    assert store.get_alerts() == [alerts[2], alerts[1]]


@pytest.mark.parametrize("max_alerts", [0, -1, True, 1.5])
def test_store_rejects_invalid_capacity(max_alerts):
    with pytest.raises(ValueError):
        AlertStore(max_alerts=max_alerts)


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_store_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        AlertStore().get_alerts(limit=limit)
