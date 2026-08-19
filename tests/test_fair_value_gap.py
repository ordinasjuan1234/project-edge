import pandas as pd
import pytest

from engine.structure.fair_value_gap import FairValueGapDetector


def test_detects_bullish_fvg():
    df = pd.DataFrame(
        {
            "high": [100.0, 103.0, 108.0],
            "low": [95.0, 99.0, 102.0],
            "close": [98.0, 102.0, 106.0],
        }
    )

    result = FairValueGapDetector().detect(df)

    assert bool(result.loc[2, "fvg_created"]) is True
    assert result.loc[2, "fvg_type"] == "BULLISH"
    assert result.loc[2, "fvg_lower"] == 100.0
    assert result.loc[2, "fvg_upper"] == 102.0
    assert result.loc[2, "active_fvg_state"] == "ACTIVE"


def test_detects_bearish_fvg():
    df = pd.DataFrame(
        {
            "high": [105.0, 102.0, 98.0],
            "low": [100.0, 97.0, 94.0],
            "close": [103.0, 99.0, 95.0],
        }
    )

    result = FairValueGapDetector().detect(df)

    assert bool(result.loc[2, "fvg_created"]) is True
    assert result.loc[2, "fvg_type"] == "BEARISH"
    assert result.loc[2, "fvg_lower"] == 98.0
    assert result.loc[2, "fvg_upper"] == 100.0


def test_bullish_fvg_becomes_partial_then_filled():
    df = pd.DataFrame(
        {
            "high": [100.0, 103.0, 108.0, 107.0, 104.0],
            "low": [95.0, 99.0, 102.0, 101.0, 99.0],
            "close": [98.0, 102.0, 106.0, 103.0, 100.0],
        }
    )

    result = FairValueGapDetector().detect(df)

    assert result.loc[2, "active_fvg_state"] == "ACTIVE"
    assert result.loc[3, "active_fvg_state"] == "PARTIAL"
    assert pd.isna(result.loc[4, "active_fvg_type"])


def test_min_gap_filter():
    df = pd.DataFrame(
        {
            "high": [100.0, 101.0, 102.0],
            "low": [99.0, 100.0, 100.1],
            "close": [99.5, 100.5, 101.0],
        }
    )

    result = FairValueGapDetector(min_gap_pct=0.01).detect(df)

    assert bool(result.loc[2, "fvg_created"]) is False


def test_missing_columns_raise_error():
    with pytest.raises(ValueError):
        FairValueGapDetector().detect(
            pd.DataFrame(
                {
                    "close": [100.0],
                }
            )
        )
