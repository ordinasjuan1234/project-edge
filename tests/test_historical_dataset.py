import pandas as pd
import pytest

from engine.data.historical_dataset import HistoricalDataset


def candles(count=96):
    open_time = pd.date_range(
        "2026-01-01T00:00:00Z",
        periods=count,
        freq="5min",
    )
    close = [100.0 + index * 0.1 for index in range(count)]
    return pd.DataFrame(
        {
            "open_time": open_time,
            "close_time": open_time + pd.Timedelta(minutes=5),
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [1.0] * count,
        }
    )


def test_builds_only_complete_aligned_timeframes():
    result = HistoricalDataset().build(candles())

    assert list(result) == ["4H", "1H", "30M", "15M", "5M"]
    assert len(result["5M"]) == 96
    assert len(result["15M"]) == 32
    assert len(result["30M"]) == 16
    assert len(result["1H"]) == 8
    assert len(result["4H"]) == 2
    assert result["4H"].iloc[0]["open"] == pytest.approx(100.0)
    assert result["4H"].iloc[0]["close"] == pytest.approx(104.7)


def test_drops_incomplete_higher_timeframe_bars():
    result = HistoricalDataset().build(candles(49))

    assert len(result["4H"]) == 1
    assert len(result["1H"]) == 4


def test_missing_columns_are_rejected():
    with pytest.raises(ValueError):
        HistoricalDataset().build(pd.DataFrame({"close": [100.0]}))
