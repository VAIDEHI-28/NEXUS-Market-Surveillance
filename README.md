# NEXUS — Explainable Market Surveillance Engine

**An intelligent system that watches the crypto market, detects unusual activity, and explains what looks suspicious.**

NEXUS is a market surveillance project built to help identify unusual trading behaviour in real time. It watches market trades and order-book changes, calculates useful measurements, and raises alerts when activity looks different from normal.

The goal is to make market monitoring faster, more understandable, and easier to investigate.

## Why NEXUS?

Imagine a busy marketplace where thousands of people buy and sell things every second.

Now imagine trying to watch every transaction and figure out whether something unusual is happening. A person cannot do this efficiently at such a large scale.

Crypto exchanges face a similar challenge. Huge numbers of trades and orders happen continuously, and unusual activity can be difficult to spot.

**NEXUS acts like an automated market watchdog.** It continuously analyses market data, looks for unusual patterns, and provides information that can help someone investigate further.

## How does it work?

NEXUS follows a simple process:

1. **Collect market data** — receives trades and order-book updates from Binance.
2. **Build the market picture** — keeps track of buy and sell orders and their prices.
3. **Calculate market measurements** — measures trading activity, trading volume, price spread, and available buy and sell quantities.
4. **Detect unusual activity** — compares current measurements with recent patterns.
5. **Generate alerts** — records unusual conditions with measurements and supporting evidence.
6. **Provide alerts through an API** — allows another application or dashboard to retrieve the alerts.

## System architecture

The following diagram shows how NEXUS collects market data, detects unusual activity, and makes alerts available through its API.

### What does each part do?

| Component | Simple explanation |
|---|---|
| Binance | The source of market data. |
| Market Data Collection | Receives trades and order-book updates. |
| Order Book Builder | Maintains the current picture of buy and sell orders. |
| Feature Engineering | Converts raw data into useful market measurements. |
| Anomaly Detector | Identifies measurements that differ significantly from recent patterns. |
| Alert Store | Keeps recent alerts available for retrieval. |
| FastAPI | Provides endpoints to check system health, view status, and retrieve alerts. |
| Dashboard or API Client | A future or external interface that can display the results. |

## What can NEXUS detect?

The current anomaly detector looks for unusual market conditions such as:

- **Trading activity spikes:** many more trades than usual.
- **Trading volume spikes:** unusually large total traded quantities.
- **Spread widening:** the difference between the best buy and sell prices increases.
- **Buy-side or sell-side depth drops:** the quantity of available orders on one side of the order book falls.
- **Order-book imbalance shifts:** the balance between buy-side and sell-side quantities changes sharply.

These signals can help identify activity worth investigating. They do **not**, by themselves, prove fraud, spoofing, or market manipulation.

## Technology stack

- **Language:** Python
- **Backend API:** FastAPI
- **Market data:** Binance WebSocket streams and REST snapshots
- **Data processing:** Custom trade and order-book feature pipelines
- **Storage:** Parquet files for collected trade data; in-memory storage for recent alerts
- **Testing:** pytest
- **Version control:** Git and GitHub

## Current implementation status

NEXUS is being built incrementally, with a focus on correctness and explainability.

- [x] Binance trade-stream processing
- [x] Order-book snapshot and update handling
- [x] Order-book sequence validation and recovery logic
- [x] Trade and order-book feature engineering
- [x] Market-data freshness validation
- [x] Rolling-baseline anomaly detection
- [x] Alert storage and filtering
- [x] FastAPI health, status, and alert endpoints
- [x] Automated backend tests
- [ ] Deterministic offline market replay
- [ ] Spoofing-specific and other manipulation-pattern detection
- [ ] Interactive surveillance dashboard
- [ ] Historical evaluation of detection quality and false alarms

**Current test status:** 143 automated tests passed in the latest run.

Live Binance connectivity has timed out in the development environment. The market-data and detection components can be tested independently, and offline replay is the next planned step to make end-to-end testing reliable without depending on a live exchange connection.

## Getting started

### Requirements

- Python 3.13 or a compatible Python environment
- Git
- The project's Python dependencies

### 1. Clone the repository

```bash
git clone https://github.com/VAIDEHI-28/NEXUS-Market-Surveillance.git
cd NEXUS-Market-Surveillance
```

### 2. Enter the backend directory

```bash
cd backend
```

Activate your project's virtual environment if you already have one configured.

### 3. Run the tests

From the `backend` directory:

```bash
PYTHONPATH=src python -m pytest -v
```

### 4. Start the API

From the same directory:

```bash
PYTHONPATH=src python -m uvicorn nexus.main:app --reload
```

Open the interactive API documentation at:

`http://127.0.0.1:8000/docs`

The API provides health and status information, as well as endpoints for retrieving alerts. Live market ingestion depends on the exchange connection being available.

## What makes NEXUS different?

NEXUS is not just a script that flags large trades. It combines market-data handling, order-book validation, feature engineering, anomaly detection, and an alert API in one system.

The emphasis is on building a reliable foundation before adding more advanced detection methods. Each alert should provide measurements that help explain why the system flagged an unusual condition.

The next stage is to replay historical or synthetic market events, evaluate detection performance, measure false alarms, and develop more specific detection methods.

## Important limitations

- An anomaly is a signal for investigation, not proof of manipulation.
- The current detector uses rolling statistical baselines; it is not yet a trained machine-learning model.
- The current alert store is in memory, so alerts are not permanently retained across restarts.
- Reliable end-to-end market surveillance still needs replay testing, performance evaluation, and more advanced detection logic.

## Project goal

Build a reliable, explainable, and testable market surveillance engine that can process market events, identify unusual patterns, and help people understand why those patterns deserve attention.

**NEXUS — See the signal. Understand the behaviour. Investigate with evidence.**

