import pandas as pd
import pytest
from datetime import datetime, timezone

from engine.data.binance_historical_data import BinanceHistoricalData


def test_valid_project_edge_intervals():
    loader = BinanceHistoricalData()

    for interval in ["5m", "15m", "30m", "1h", "4h"]:
        assert loader._validate_interval(interval) == interval


def test_invalid_interval_is_rejected():
    with pytest.raises(ValueError):
        BinanceHistoricalData._validate_interval("2h")


def test_invalid_timeout_is_rejected():
    with pytest.raises(ValueError):
        BinanceHistoricalData(timeout=0)


def test_fetch_rejects_invalid_limit_before_network_call():
    loader = BinanceHistoricalData()

    with pytest.raises(ValueError):
        loader.fetch(
            symbol="BTCUSDT",
            interval="5m",
            limit=1001,
        )


def test_fetch_rejects_empty_symbol_before_network_call():
    loader = BinanceHistoricalData()

    with pytest.raises(ValueError):
        loader.fetch(
            symbol="",
            interval="5m",
            limit=100,
        )


def test_project_edge_timeframe_mapping(monkeypatch):
    loader = BinanceHistoricalData()
    calls = []

    def fake_fetch(symbol, interval, start_time_ms=None, end_time_ms=None, limit=1000):
        calls.append((symbol, interval, limit))
        return pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
            }
        )

    monkeypatch.setattr(loader, "fetch", fake_fetch)

    result = loader.fetch_project_edge_timeframes(
        symbol="BTCUSDT",
        limit=500,
    )

    assert set(result) == {"4H", "1H", "30M", "15M", "5M"}
    assert calls == [
        ("BTCUSDT", "4h", 500),
        ("BTCUSDT", "1h", 500),
        ("BTCUSDT", "30m", 500),
        ("BTCUSDT", "15m", 500),
        ("BTCUSDT", "5m", 500),
    ]


def test_fetch_recent_requests_only_closed_candles(monkeypatch):
    loader = BinanceHistoricalData()
    captured = {}

    def fake_fetch_range(symbol, interval, start_time_ms, end_time_ms):
        captured.update(
            symbol=symbol,
            interval=interval,
            start=start_time_ms,
            end=end_time_ms,
        )
        return pd.DataFrame()

    monkeypatch.setattr(loader, "fetch_range", fake_fetch_range)
    loader.fetch_recent(
        symbol="BTCUSDT",
        interval="5m",
        days=1,
        now=datetime(2026, 1, 1, 12, 7, tzinfo=timezone.utc),
    )

    expected_last_open = int(
        datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp()
        * 1000
    )
    assert captured["end"] == expected_last_open
    assert captured["end"] - captured["start"] == 24 * 60 * 60 * 1000


def test_fetch_recent_allows_internal_warmup_range(monkeypatch):
    loader = BinanceHistoricalData()
    monkeypatch.setattr(loader, "fetch_range", lambda **kwargs: pd.DataFrame())

    loader.fetch_recent(
        symbol="ETHUSDT",
        interval="5m",
        days=455,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="730"):
        loader.fetch_recent(
            symbol="ETHUSDT",
            interval="5m",
            days=731,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_fetch_range_rejects_inverted_times():
    with pytest.raises(ValueError):
        BinanceHistoricalData().fetch_range(
            symbol="BTCUSDT",
            interval="5m",
            start_time_ms=200,
            end_time_ms=100,
        )
