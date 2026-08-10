import pandas as pd

from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)


def sample_ohlc(offset: float = 0.0):
    close = [
        100, 102, 105, 103, 99, 101, 106, 110,
        107, 104, 108, 113, 117, 114, 110, 112,
        118, 121, 117, 113, 109, 112, 116, 120,
        115, 111, 107, 110, 114, 119,
    ]
    close = [x + offset for x in close]
    return pd.DataFrame({
        "open": close,
        "high": [x + 1.0 for x in close],
        "low": [x - 1.0 for x in close],
        "close": close,
    })


def sample_timeframes():
    return {
        "4H": sample_ohlc(0.0),
        "1H": sample_ohlc(1.0),
        "30M": sample_ohlc(2.0),
        "15M": sample_ohlc(3.0),
        "5M": sample_ohlc(4.0),
    }


def test_runs_structure_engine_on_all_timeframes():
    engine = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 3,
            "atr_multiplier": 1.0,
            "min_move_pct": 0.001,
            "max_move_pct": 0.10,
        }
    )
    result = engine.analyze(sample_timeframes())

    assert set(result["states"]) == {"4H", "1H", "30M", "15M", "5M"}
    assert set(result["analyses"]) == {"4H", "1H", "30M", "15M", "5M"}

    for analysis in result["analyses"].values():
        assert not analysis.empty
        assert "market_structure" in analysis.columns
        assert "structure_break" in analysis.columns


def test_returns_multitimeframe_alignment():
    engine = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 3,
            "atr_multiplier": 1.0,
            "min_move_pct": 0.001,
            "max_move_pct": 0.10,
        }
    )
    result = engine.analyze(sample_timeframes())

    assert "alignment" in result
    assert "alignment" in result["alignment"]
    assert "entry_ready" in result["alignment"]


def test_missing_timeframe_raises_error():
    timeframes = sample_timeframes()
    del timeframes["5M"]

    engine = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 3,
            "atr_multiplier": 1.0,
            "min_move_pct": 0.001,
            "max_move_pct": 0.10,
        }
    )

    try:
        engine.analyze(timeframes)
    except ValueError as exc:
        assert "5M" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError por temporalidad faltante")
