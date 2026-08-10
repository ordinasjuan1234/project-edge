import pandas as pd

from engine.structure.break_of_structure import BreakOfStructureDetector


def test_bullish_bos():
    df = pd.DataFrame(
        {
            "close": [100.0, 105.0, 111.0],
            "structural_support": [95.0, 95.0, 95.0],
            "structural_resistance": [110.0, 110.0, 110.0],
            "market_structure": ["BULLISH", "BULLISH", "BULLISH"],
        }
    )

    result = BreakOfStructureDetector().detect(df)

    assert result.loc[2, "structure_break"] == "BOS"
    assert result.loc[2, "break_direction"] == "UP"
    assert result.loc[2, "broken_level"] == 110.0


def test_bearish_bos():
    df = pd.DataFrame(
        {
            "close": [100.0, 96.0, 94.0],
            "structural_support": [95.0, 95.0, 95.0],
            "structural_resistance": [110.0, 110.0, 110.0],
            "market_structure": ["BEARISH", "BEARISH", "BEARISH"],
        }
    )

    result = BreakOfStructureDetector().detect(df)

    assert result.loc[2, "structure_break"] == "BOS"
    assert result.loc[2, "break_direction"] == "DOWN"
    assert result.loc[2, "broken_level"] == 95.0


def test_bullish_choch():
    df = pd.DataFrame(
        {
            "close": [100.0, 97.0, 94.0],
            "structural_support": [95.0, 95.0, 95.0],
            "structural_resistance": [110.0, 110.0, 110.0],
            "market_structure": ["BULLISH", "BULLISH", "BULLISH"],
        }
    )

    result = BreakOfStructureDetector().detect(df)

    assert result.loc[2, "structure_break"] == "CHoCH"
    assert result.loc[2, "break_direction"] == "DOWN"


def test_bearish_choch():
    df = pd.DataFrame(
        {
            "close": [100.0, 105.0, 111.0],
            "structural_support": [95.0, 95.0, 95.0],
            "structural_resistance": [110.0, 110.0, 110.0],
            "market_structure": ["BEARISH", "BEARISH", "BEARISH"],
        }
    )

    result = BreakOfStructureDetector().detect(df)

    assert result.loc[2, "structure_break"] == "CHoCH"
    assert result.loc[2, "break_direction"] == "UP"


def test_no_false_break_when_close_does_not_cross_level():
    df = pd.DataFrame(
        {
            "close": [100.0, 109.0, 109.5],
            "structural_support": [95.0, 95.0, 95.0],
            "structural_resistance": [110.0, 110.0, 110.0],
            "market_structure": ["BULLISH", "BULLISH", "BULLISH"],
        }
    )

    result = BreakOfStructureDetector().detect(df)

    assert result["structure_break"].isna().all()
    assert result["break_direction"].isna().all()
    assert result["broken_level"].isna().all()
